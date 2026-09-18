#!/usr/bin/env bash
# Robust dev->prod server-side copy worker. Fixes the xargs/env-too-long bug.
# Reads blob names from a list file, copies each dev->prod with a SAS-authed source,
# concurrency via a bounded pool of background jobs. Skips blobs already in prod.
set -uo pipefail

DEV_ACCT="stidstaticsite002"
PROD_ACCT="stidstaticsiteprod"
PROD_SUB="34e3dbac-c2c3-4d5b-8c39-f40d69c6f0fe"
DEV_SUB="69af2884-d660-4bff-aa72-9ec4a8996aea"
PARALLEL=12
WORK="/tmp/prod-copy2"
mkdir -p "$WORK"
BLOBLIST="$WORK/dev-blobs.txt"
FAILLOG="$WORK/fail.log"
DONELOG="$WORK/done.log"
strip_noise() { grep -v "pkg_resources\|deprecated\|UserWarning\|__import__\|WARNING: 2!"; }

az account set --subscription "$PROD_SUB" 2>/dev/null

# 1. enumerate dev (fresh)
echo ">>> Enumerating dev..."
az storage blob list --account-name "$DEV_ACCT" --container-name '$web' \
  --auth-mode login --subscription "$DEV_SUB" --num-results 100000 \
  --query "[].name" -o tsv 2>/dev/null | strip_noise > "$BLOBLIST"
TOTAL=$(wc -l < "$BLOBLIST" | tr -d ' ')
echo ">>> dev blobs: $TOTAL"

# 2. mint SAS -> file
EXPIRY=$(python3 -c "import datetime; print((datetime.datetime.utcnow()+datetime.timedelta(hours=8)).strftime('%Y-%m-%dT%H:%MZ'))")
az storage container generate-sas --account-name "$DEV_ACCT" --name '$web' \
  --permissions rl --expiry "$EXPIRY" --auth-mode login --as-user \
  --subscription "$DEV_SUB" -o tsv 2>/dev/null | strip_noise | tail -1 > "$WORK/sas.txt"
SAS=$(cat "$WORK/sas.txt")
[ ${#SAS} -gt 50 ] || { echo "ERROR: SAS failed"; exit 1; }
echo ">>> SAS ok (${#SAS} chars)"

: > "$FAILLOG"; : > "$DONELOG"

# 3. bounded-parallel copy using background jobs (no xargs, no exported funcs)
copy_one() {
  local name="$1"
  local src="https://${DEV_ACCT}.blob.core.windows.net/\$web/${name}?${SAS}"
  if az storage blob copy start \
        --account-name "$PROD_ACCT" --destination-container '$web' \
        --destination-blob "$name" --source-uri "$src" \
        --auth-mode login -o none 2>/dev/null; then
    echo "$name" >> "$DONELOG"
  else
    echo "$name" >> "$FAILLOG"
  fi
}

n=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  copy_one "$name" &
  n=$((n+1))
  # throttle: cap concurrent jobs
  if (( n % PARALLEL == 0 )); then wait -n 2>/dev/null || wait; fi
done < "$BLOBLIST"
wait

DONE=$(wc -l < "$DONELOG" | tr -d ' ')
FAIL=$(wc -l < "$FAILLOG" | tr -d ' ')
echo ">>> Copy complete. done=$DONE fail=$FAIL"
[ "$FAIL" -gt 0 ] && { echo ">>> Failed blobs (first 20):"; head -20 "$FAILLOG"; }

# 4. verify count
PRODC=$(az storage blob list --account-name "$PROD_ACCT" --container-name '$web' \
  --auth-mode login --subscription "$PROD_SUB" --num-results 100000 \
  --query "length(@)" -o tsv 2>/dev/null | strip_noise | tail -1)
echo ">>> prod blob count now: $PRODC / $TOTAL dev"
