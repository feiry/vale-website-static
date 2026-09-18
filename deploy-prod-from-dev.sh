#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# deploy-prod-from-dev.sh
#
# Server-side copy of the QA'd dev static-site content into the empty prod
# ZRS storage account, using azcopy with AAD auth. No re-clone, no laptop
# re-upload, content-types preserved.
#
#   DEV  (source): stidstaticsite002 / $web   (LRS, QA'd golden copy)
#   PROD (dest)  : stidstaticsiteprod / $web   (ZRS, empty)
#
# Prereqs:
#   - Prod PIM roles ACTIVATED (CUST-StaticWeb-Admin-Prod + Storage Blob Data
#     Contributor) — see project_azure_prod.md
#   - azcopy logged in:  azcopy login --tenant-id <TENANT>
#
# Usage:
#   ./deploy-prod-from-dev.sh            # dry-run only (default, safe)
#   ./deploy-prod-from-dev.sh --run      # real copy + verification
#   ./deploy-prod-from-dev.sh --verify   # verification only (post-copy)
# ---------------------------------------------------------------------------

TENANT="912d7f41-ade5-406f-906e-5f7e2b39a4d7"
DEV_ACCT="stidstaticsite002"
PROD_ACCT="stidstaticsiteprod"
DEV_SUB="69af2884-d660-4bff-aa72-9ec4a8996aea"
PROD_SUB="34e3dbac-c2c3-4d5b-8c39-f40d69c6f0fe"

# %24web == URL-encoded "$web"
SRC="https://${DEV_ACCT}.blob.core.windows.net/%24web/*"
DST="https://${PROD_ACCT}.blob.core.windows.net/%24web/"

MODE="${1:---dry-run}"

# --- helpers ---------------------------------------------------------------
strip_az_noise() { grep -v "pkg_resources\|deprecated\|UserWarning\|__import__\|WARNING: 2!"; }

check_azcopy_login() {
  if ! azcopy login status 2>&1 | grep -qi "you have successfully"; then
    echo ">>> azcopy is not logged in. Run this first (interactive):"
    echo "      azcopy login --tenant-id ${TENANT}"
    exit 1
  fi
}

dev_blob_count() {
  az storage blob list --account-name "$DEV_ACCT" --container-name '$web' \
    --auth-mode login --subscription "$DEV_SUB" --num-results 100000 \
    --query "length(@)" 2>&1 | strip_az_noise | tail -1
}

prod_blob_count() {
  az storage blob list --account-name "$PROD_ACCT" --container-name '$web' \
    --auth-mode login --subscription "$PROD_SUB" --num-results 100000 \
    --query "length(@)" 2>&1 | strip_az_noise | tail -1
}

# --- dry-run ---------------------------------------------------------------
do_dryrun() {
  echo ">>> DRY RUN — no data will be copied"
  echo ">>> Source: $SRC"
  echo ">>> Dest  : $DST"
  echo ">>> Dev blob count: $(dev_blob_count)"
  echo ">>> Prod blob count (should be 0): $(prod_blob_count)"
  echo
  azcopy copy "$SRC" "$DST" \
    --recursive \
    --s2s-preserve-properties \
    --s2s-preserve-access-tier=false \
    --dry-run
  echo
  echo ">>> Dry run complete. Re-run with --run to execute the real copy."
}

# --- real copy -------------------------------------------------------------
do_copy() {
  echo ">>> REAL COPY starting (server-side dev -> prod)"
  echo ">>> Prod blob count BEFORE: $(prod_blob_count)"
  azcopy copy "$SRC" "$DST" \
    --recursive \
    --s2s-preserve-properties \
    --s2s-preserve-access-tier=false
  echo ">>> Copy finished."
  do_verify
}

# --- verification ----------------------------------------------------------
do_verify() {
  echo
  echo ">>> VERIFICATION"
  local devc prodc
  devc="$(dev_blob_count)"
  prodc="$(prod_blob_count)"
  echo "    Dev  blobs: $devc"
  echo "    Prod blobs: $prodc"
  if [[ "$devc" == "$prodc" ]]; then
    echo "    OK: blob counts match."
  else
    echo "    WARNING: blob count mismatch ($devc dev vs $prodc prod) — investigate."
  fi

  echo
  echo ">>> Content-type canaries on PROD (blob properties):"
  for probe in \
      "documents/d/global/jqueryjs|application/javascript" \
      "documents/d/guest/fundo-logo-svg-1@download=true|image/svg+xml" \
      "index.html|text/html" ; do
    key="${probe%%|*}"; want="${probe##*|}"
    got=$(az storage blob show --account-name "$PROD_ACCT" --container-name '$web' \
            --name "$key" --auth-mode login --subscription "$PROD_SUB" \
            --query "properties.contentSettings.contentType" -o tsv 2>&1 | strip_az_noise | tail -1)
    if [[ "$got" == "$want" ]]; then echo "    OK  $key -> $got"
    else echo "    BAD $key -> got '$got', want '$want'"; fi
  done

  echo
  echo ">>> Live smoke test on PROD private endpoint:"
  local base="https://${PROD_ACCT}.z45.web.core.windows.net"
  for url in "/" "/indonesia.html" "/board-of-directors.html" "/nonexistent-xyz"; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "${base}${url}")
    echo "    $url -> HTTP $code"
  done
  echo "    (root / and /indonesia.html expect 200; missing page expects 404 serving 404.html)"
}

# --- main ------------------------------------------------------------------
case "$MODE" in
  --dry-run) check_azcopy_login; do_dryrun ;;
  --run)     check_azcopy_login; do_copy ;;
  --verify)  do_verify ;;
  *) echo "Usage: $0 [--dry-run | --run | --verify]"; exit 1 ;;
esac
