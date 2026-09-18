#!/usr/bin/env bash
# Retry the 52 failed blobs with PROPER URL-encoding of the blob name in the source URI.
# The failures had &, +, %, ;, @ in names which broke the --source-uri (esp. & truncating the SAS).
set -uo pipefail

DEV_ACCT="stidstaticsite002"
PROD_ACCT="stidstaticsiteprod"
PROD_SUB="34e3dbac-c2c3-4d5b-8c39-f40d69c6f0fe"
DEV_SUB="69af2884-d660-4bff-aa72-9ec4a8996aea"
FAILIN="${1:?usage: retry-failed-copies.sh <fail-list-file>}"
WORK="/tmp/prod-copy2"
strip_noise() { grep -v "pkg_resources\|deprecated\|UserWarning\|__import__\|WARNING: 2!"; }

az account set --subscription "$PROD_SUB" 2>/dev/null

# fresh SAS
EXPIRY=$(python3 -c "import datetime; print((datetime.datetime.utcnow()+datetime.timedelta(hours=4)).strftime('%Y-%m-%dT%H:%MZ'))")
SAS=$(az storage container generate-sas --account-name "$DEV_ACCT" --name '$web' \
  --permissions rl --expiry "$EXPIRY" --auth-mode login --as-user \
  --subscription "$DEV_SUB" -o tsv 2>/dev/null | strip_noise | tail -1)
[ ${#SAS} -gt 50 ] || { echo "ERROR: SAS failed"; exit 1; }
echo ">>> SAS ok (${#SAS} chars)"

: > "$WORK/retry-fail.log"; ok=0; bad=0
while IFS= read -r name; do
  [ -n "$name" ] || continue
  # URL-encode the blob name path (encode everything except / )
  enc=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe='/'))" "$name")
  src="https://${DEV_ACCT}.blob.core.windows.net/\$web/${enc}?${SAS}"
  if az storage blob copy start \
        --account-name "$PROD_ACCT" --destination-container '$web' \
        --destination-blob "$name" --source-uri "$src" \
        --auth-mode login -o none 2>>"$WORK/retry-fail.log"; then
    ok=$((ok+1))
  else
    bad=$((bad+1)); echo "STILL-FAIL: $name" >> "$WORK/retry-fail.log"
  fi
done < "$FAILIN"

echo ">>> retry done: ok=$ok still-fail=$bad"
[ "$bad" -gt 0 ] && { echo "--- still failing ---"; grep STILL-FAIL "$WORK/retry-fail.log"; }
