#!/usr/bin/env bash
# Server-side copy dev -> prod using az CLI (azcopy is blocked by tenant Conditional Access).
# Enumerate dev $web (authenticated), mint a user-delegation SAS on dev, then
# `az storage blob copy start` each blob dev->prod (server-side; bytes never touch the laptop).
# Content-Types are preserved by the server-side copy.
#
#   DEV  (source): stidstaticsite002 / $web   (dev, permanent role)
#   PROD (dest)  : stidstaticsiteprod / $web   (PROD, PIM must be active + fresh az login)
#
# Usage:
#   ./deploy-prod-from-dev-azcli.sh --list     # just enumerate dev + count (no writes)
#   ./deploy-prod-from-dev-azcli.sh --run      # real copy + verification
#   ./deploy-prod-from-dev-azcli.sh --verify   # verification only
set -uo pipefail

DEV_ACCT="stidstaticsite002"
PROD_ACCT="stidstaticsiteprod"
DEV_SUB="69af2884-d660-4bff-aa72-9ec4a8996aea"
PROD_SUB="34e3dbac-c2c3-4d5b-8c39-f40d69c6f0fe"
PARALLEL=16
WORK="${TMPDIR:-/tmp}/prod-copy"
mkdir -p "$WORK"
BLOBLIST="$WORK/dev-blobs.txt"

strip_noise() { grep -v "pkg_resources\|deprecated\|UserWarning\|__import__\|WARNING: 2!"; }

enumerate_dev() {
  echo ">>> Enumerating dev \$web blobs (authenticated)..."
  az storage blob list --account-name "$DEV_ACCT" --container-name '$web' \
    --auth-mode login --subscription "$DEV_SUB" --num-results 100000 \
    --query "[].name" -o tsv 2>/dev/null | strip_noise > "$BLOBLIST"
  echo ">>> dev blob count: $(wc -l < "$BLOBLIST")"
}

mint_sas() {
  local expiry
  expiry=$(python3 -c "import datetime; print((datetime.datetime.utcnow()+datetime.timedelta(hours=6)).strftime('%Y-%m-%dT%H:%MZ'))")
  az storage container generate-sas --account-name "$DEV_ACCT" --name '$web' \
    --permissions rl --expiry "$expiry" --auth-mode login --as-user \
    --subscription "$DEV_SUB" -o tsv 2>/dev/null | strip_noise | tail -1
}

prod_count() {
  az storage blob list --account-name "$PROD_ACCT" --container-name '$web' \
    --auth-mode login --subscription "$PROD_SUB" --num-results 100000 \
    --query "length(@)" -o tsv 2>/dev/null | strip_noise | tail -1
}

do_copy() {
  enumerate_dev
  local total; total=$(wc -l < "$BLOBLIST" | tr -d ' ')
  echo ">>> Minting dev SAS (6h)..."
  local SAS; SAS=$(mint_sas)
  [ ${#SAS} -gt 50 ] || { echo "ERROR: SAS generation failed"; exit 1; }
  echo ">>> SAS ok (${#SAS} chars). Starting server-side copy of $total blobs (parallel=$PARALLEL)..."

  az account set --subscription "$PROD_SUB" 2>/dev/null
  export PROD_ACCT SAS DEV_ACCT
  : > "$WORK/copy-fail.log"

  copy_one() {
    local name="$1"
    # URL-encode is not needed for the source path if we pass the raw name; az handles it.
    local src="https://${DEV_ACCT}.blob.core.windows.net/\$web/${name}?${SAS}"
    local out
    out=$(az storage blob copy start \
      --account-name "$PROD_ACCT" --destination-container '$web' \
      --destination-blob "$name" --source-uri "$src" \
      --auth-mode login -o none 2>&1)
    if [ $? -ne 0 ]; then echo "FAIL: $name :: $(echo "$out" | tail -1)" >> "$WORK/copy-fail.log"; fi
  }
  export -f copy_one strip_noise

  # drive parallel copies
  cat "$BLOBLIST" | xargs -P "$PARALLEL" -I {} bash -c 'copy_one "$@"' _ {}

  echo ">>> Copy dispatch complete."
  local fails; fails=$(wc -l < "$WORK/copy-fail.log" | tr -d ' ')
  echo ">>> Failures: $fails (see $WORK/copy-fail.log)"
  do_verify
}

do_verify() {
  echo
  echo ">>> VERIFICATION"
  az account set --subscription "$PROD_SUB" 2>/dev/null
  local devc prodc
  devc=$(wc -l < "$BLOBLIST" 2>/dev/null | tr -d ' ')
  prodc=$(prod_count)
  echo "    dev blobs (from list): $devc"
  echo "    prod blobs:            $prodc"
  [ "$devc" = "$prodc" ] && echo "    OK: counts match." || echo "    WARNING: mismatch — investigate."

  echo ">>> Content-type canaries on PROD:"
  for probe in \
      "documents/d/global/jqueryjs|application/javascript" \
      "documents/d/guest/fundo-logo-svg-1@download=true|image/svg+xml" \
      "index.html|text/html" ; do
    key="${probe%%|*}"; want="${probe##*|}"
    got=$(az storage blob show --account-name "$PROD_ACCT" --container-name '$web' \
            --name "$key" --auth-mode login --subscription "$PROD_SUB" \
            --query "properties.contentSettings.contentType" -o tsv 2>/dev/null | strip_noise | tail -1)
    [ "$got" = "$want" ] && echo "    OK  $key -> $got" || echo "    BAD $key -> got '$got' want '$want'"
  done

  echo ">>> Live smoke test (prod private endpoint):"
  local base="https://${PROD_ACCT}.z45.web.core.windows.net"
  for url in "/" "/indonesia.html" "/board-of-directors.html" "/nonexistent-xyz"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "${base}${url}")
    echo "    $url -> HTTP $code"
  done
}

case "${1:---list}" in
  --list)   enumerate_dev ;;
  --run)    do_copy ;;
  --verify) do_verify ;;
  *) echo "Usage: $0 [--list|--run|--verify]"; exit 1 ;;
esac
