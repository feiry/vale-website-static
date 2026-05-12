#!/usr/bin/env bash
set -euo pipefail

# Re-upload files with incorrect MIME types to S3
# S3 can't auto-detect types for extensionless files or files with UUID paths

SITE_DIR="./site/vale.com"
BUCKET="${1:-vale-indonesia-static}"
AWS_OPTS="${AWS_PROFILE:+--profile $AWS_PROFILE}"

echo ">>> Scanning for files needing MIME type fixes..."

# Find all files and check if they need a custom content-type
find "$SITE_DIR" -type f | while read -r filepath; do
  # Get the S3 key (relative path)
  key="${filepath#$SITE_DIR/}"

  # Use file command to detect actual MIME type
  detected=$(file --brief --mime-type "$filepath" 2>/dev/null)

  # Check if the file extension would give the right type
  case "$filepath" in
    *.html) expected="text/html" ;;
    *.css)  expected="text/css" ;;
    *.js)   expected="application/javascript" ;;
    *.json) expected="application/json" ;;
    *.xml)  expected="application/xml" ;;
    *.svg)  expected="image/svg+xml" ;;
    *.png)  expected="image/png" ;;
    *.jpg|*.jpeg) expected="image/jpeg" ;;
    *.gif)  expected="image/gif" ;;
    *.webp) expected="image/webp" ;;
    *.pdf)  expected="application/pdf" ;;
    *.woff) expected="font/woff" ;;
    *.woff2) expected="font/woff2" ;;
    *.ttf)  expected="font/ttf" ;;
    *.eot)  expected="application/vnd.ms-fontobject" ;;
    *.ico)  expected="image/x-icon" ;;
    *)      expected="" ;;  # No extension match
  esac

  # If no extension match, or if the path contains UUIDs (documents/44618/...)
  # use the detected type
  if [[ -z "$expected" ]] || echo "$key" | grep -qE '/[0-9a-f]{8}-[0-9a-f]{4}'; then
    # Use detected MIME type, but fix common misdetections
    case "$detected" in
      image/svg+xml|image/png|image/jpeg|image/gif|image/webp)
        expected="$detected" ;;
      application/pdf)
        expected="$detected" ;;
      text/html|text/xml)
        expected="$detected" ;;
      application/gzip)
        expected="$detected" ;;
      text/plain)
        # text/plain could be CSS, JS, etc — check parent path
        if echo "$key" | grep -q '\.css'; then
          expected="text/css"
        elif echo "$key" | grep -q '\.js'; then
          expected="application/javascript"
        else
          expected="$detected"
        fi
        ;;
      application/octet-stream)
        # Last resort: check parent directory name for type hint
        parent_dir=$(dirname "$key")
        case "$parent_dir" in
          *.png*) expected="image/png" ;;
          *.jpg*|*.jpeg*) expected="image/jpeg" ;;
          *.svg*) expected="image/svg+xml" ;;
          *.pdf*) expected="application/pdf" ;;
          *) expected="$detected" ;;
        esac
        ;;
      *)
        expected="${detected:-application/octet-stream}" ;;
    esac

    # Only re-upload if we have a meaningful type
    if [[ "$expected" != "application/octet-stream" && "$expected" != "binary/octet-stream" ]]; then
      echo "  FIX: $key → $expected"
      aws s3 cp "s3://$BUCKET/$key" "s3://$BUCKET/$key" \
        $AWS_OPTS \
        --content-type "$expected" \
        --cache-control "public, max-age=300" \
        --metadata-directive REPLACE \
        --no-progress 2>/dev/null || echo "    WARN: failed to fix $key"
    fi
  fi
done

echo ">>> MIME type fixes complete."
