#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$SCRIPT_DIR/site/vale.com"
CONTAINER='$web'

ACCOUNT="stidstaticsite002"
FIX_MIME=0
DELETE_ORPHANS=0
SKIP_UPLOAD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix-mime)       FIX_MIME=1; shift ;;
    --delete-orphans) DELETE_ORPHANS=1; shift ;;
    --skip-upload)    SKIP_UPLOAD=1; shift ;;
    -h|--help)
      echo "Usage: $0 [account] [--fix-mime] [--delete-orphans] [--skip-upload]"
      echo "  account           Azure storage account name (default: stidstaticsite002)"
      echo "  --fix-mime        Re-upload extensionless documents/d/ files with detected MIME type"
      echo "  --delete-orphans  Delete blobs in \$web that don't exist locally (sync-style)"
      echo "  --skip-upload     Skip the bulk upload step (run only the post-passes)"
      exit 0
      ;;
    *) ACCOUNT="$1"; shift ;;
  esac
done

if [[ ! -d "$SITE_DIR" ]]; then
  echo "ERROR: $SITE_DIR not found. Rebuild site/ from site-backup/ first."
  exit 1
fi

# Build static news pages before upload — failure aborts deploy
echo ">>> Building static news pages (build-news.py)..."
if ! python3 "$SCRIPT_DIR/build-news.py"; then
  echo "ERROR: build-news.py failed. Aborting deploy." >&2
  exit 1
fi

# Build static Document Library pages before upload — failure aborts deploy
echo ">>> Building static Document Library pages (build-doc-library.py)..."
if ! python3 "$SCRIPT_DIR/build-doc-library.py"; then
  echo "ERROR: build-doc-library.py failed. Aborting deploy." >&2
  exit 1
fi

echo ">>> Azure account check"
az account show --query "{tenant:tenantDefaultDomain, subscription:name, user:user.name}" -o table

echo ">>> Verifying access to storage account: $ACCOUNT"
az storage blob list --account-name "$ACCOUNT" --container-name "$CONTAINER" --auth-mode login --num-results 1 -o none

if [[ "$SKIP_UPLOAD" == "1" ]]; then
  echo ">>> Skipping bulk upload (--skip-upload)"
else
  echo ">>> Uploading $SITE_DIR to $ACCOUNT/$CONTAINER (this may take 30-60 minutes for ~1.3GB / 2k files)"
  az storage blob upload-batch \
    --account-name "$ACCOUNT" \
    --auth-mode login \
    --destination "$CONTAINER" \
    --source "$SITE_DIR" \
    --content-cache "public, max-age=300" \
    --overwrite \
    --no-progress
fi

echo ">>> Fixing MIME types for CSS/JS files"
find "$SITE_DIR" \( -name '*.css' -o -name '*.js' \) | while read -r filepath; do
  key="${filepath#$SITE_DIR/}"
  case "$filepath" in
    *.css) correct_mime="text/css" ;;
    *.js)  correct_mime="application/javascript" ;;
  esac
  current_mime=$(az storage blob show \
    --account-name "$ACCOUNT" --container-name "$CONTAINER" --name "$key" --auth-mode login \
    --query "properties.contentSettings.contentType" -o tsv 2>/dev/null || echo "")
  if [[ "$current_mime" != "$correct_mime" ]]; then
    echo "  Fix: $key ($current_mime -> $correct_mime)"
    az storage blob upload \
      --account-name "$ACCOUNT" --container-name "$CONTAINER" --name "$key" \
      --file "$filepath" --auth-mode login --overwrite \
      --content-cache "public, max-age=300" \
      --content-type "$correct_mime" \
      -o none 2>/dev/null || echo "  WARN: failed to fix $key"
  fi
done

if [[ "$FIX_MIME" == "1" ]]; then
  echo ">>> Fixing MIME types for extensionless document files"
  find "$SITE_DIR/documents/d" -type f ! -name '*.*' 2>/dev/null | while read -r filepath; do
    key="${filepath#$SITE_DIR/}"

    mime=$(file --brief --mime-type "$filepath" 2>/dev/null || echo "application/octet-stream")

    case "$mime" in
      text/plain)
        case "$filepath" in
          *.css) mime="text/css" ;;
          *.js)  mime="application/javascript" ;;
        esac
        ;;
      application/octet-stream)
        header=$(xxd -l 4 -p "$filepath" 2>/dev/null || echo "")
        case "$header" in
          89504e47) mime="image/png" ;;
          ffd8ff*)  mime="image/jpeg" ;;
          47494638) mime="image/gif" ;;
          25504446) mime="application/pdf" ;;
        esac
        ;;
    esac

    if [[ "$mime" != "application/octet-stream" && "$mime" != "binary/octet-stream" ]]; then
      az storage blob upload \
        --account-name "$ACCOUNT" --container-name "$CONTAINER" --name "$key" \
        --file "$filepath" --auth-mode login --overwrite \
        --content-cache "public, max-age=300" \
        --content-type "$mime" \
        -o none 2>/dev/null || echo "  WARN: failed to fix $key"
    fi
  done
else
  echo ">>> Skipping extensionless MIME fix (pass --fix-mime to run)"
fi

if [[ "$DELETE_ORPHANS" == "1" ]]; then
  echo ">>> Deleting orphan blobs (in \$web but not in local site/)"
  LOCAL_KEYS=$(mktemp); REMOTE_KEYS=$(mktemp); ORPHANS=$(mktemp)
  trap 'rm -f "$LOCAL_KEYS" "$REMOTE_KEYS" "$ORPHANS"' EXIT

  ( cd "$SITE_DIR" && find . -type f | sed 's|^\./||' ) | sort > "$LOCAL_KEYS"
  az storage blob list \
    --account-name "$ACCOUNT" --container-name "$CONTAINER" --auth-mode login \
    --query "[].name" -o tsv | sort > "$REMOTE_KEYS"
  comm -23 "$REMOTE_KEYS" "$LOCAL_KEYS" > "$ORPHANS"

  count=$(wc -l < "$ORPHANS" | tr -d ' ')
  echo "    Found $count orphan blob(s)"
  if [[ "$count" -gt 0 ]]; then
    while IFS= read -r key; do
      [[ -z "$key" ]] && continue
      echo "  Delete: $key"
      az storage blob delete \
        --account-name "$ACCOUNT" --container-name "$CONTAINER" --name "$key" --auth-mode login \
        -o none 2>/dev/null || echo "  WARN: failed to delete $key"
    done < "$ORPHANS"
  fi
else
  echo ">>> Skipping orphan deletion (pass --delete-orphans to run)"
fi

echo ">>> Deploy complete"
echo "    Site: https://${ACCOUNT}.z45.web.core.windows.net/"
