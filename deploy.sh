#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$SCRIPT_DIR/site/vale.com"
BUCKET="${1:-vale-indonesia-static}"
DIST_ID="${2:-$(cd infra && terraform output -raw cloudfront_distribution_id 2>/dev/null || echo '')}"
export AWS_PROFILE="${AWS_PROFILE:-vale-id}"

if [[ -z "$DIST_ID" ]]; then
  echo "ERROR: Could not determine CloudFront distribution ID"
  echo "Usage: ./deploy.sh [bucket] [distribution-id]"
  exit 1
fi

echo ">>> Deploying to s3://$BUCKET (profile: $AWS_PROFILE)"

# Step 1: Sync all files (S3 auto-detects MIME type for files with extensions)
echo ">>> Syncing files..."
aws s3 sync "$SITE_DIR" "s3://$BUCKET" \
  --delete \
  --cache-control "public, max-age=300" \
  --no-progress

# Step 1b: Fix MIME types for CSS/JS files misdetected by S3
#   Filenames with @ or _ prefixes confuse S3's auto-detection (e.g. text/x-asm)
echo ">>> Fixing MIME types for CSS/JS files..."
find "$SITE_DIR" -name '*.css' -o -name '*.js' | while read -r filepath; do
  key="${filepath#$SITE_DIR/}"
  case "$filepath" in
    *.css) correct_mime="text/css" ;;
    *.js)  correct_mime="application/javascript" ;;
  esac
  current_mime=$(aws s3api head-object --bucket "$BUCKET" --key "$key" --query 'ContentType' --output text 2>/dev/null || echo "")
  if [[ "$current_mime" != "$correct_mime" ]]; then
    echo "  Fix: $key ($current_mime → $correct_mime)"
    aws s3 cp "s3://$BUCKET/$key" "s3://$BUCKET/$key" \
      --content-type "$correct_mime" \
      --cache-control "public, max-age=300" \
      --metadata-directive REPLACE \
      --no-progress 2>/dev/null || echo "  WARN: failed to fix $key"
  fi
done

# Step 2: Fix MIME types for extensionless files in documents/d/
#   Only needed on first deploy or when documents/d/ content changes.
#   Pass --fix-mime to run this step, otherwise skip.
if [[ "${3:-}" == "--fix-mime" ]]; then
  echo ">>> Fixing MIME types for extensionless document files..."
  find "$SITE_DIR/documents/d" -type f ! -name '*.*' 2>/dev/null | while read -r filepath; do
    key="${filepath#$SITE_DIR/}"

    # Detect MIME type
    mime=$(file --brief --mime-type "$filepath" 2>/dev/null || echo "application/octet-stream")

    # Fix common misdetections
    case "$mime" in
      text/plain)
        case "$filepath" in
          *.css) mime="text/css" ;;
          *.js)  mime="application/javascript" ;;
        esac
        ;;
      application/octet-stream)
        # Try magic bytes
        header=$(xxd -l 4 -p "$filepath" 2>/dev/null || echo "")
        case "$header" in
          89504e47) mime="image/png" ;;
          ffd8ff*)  mime="image/jpeg" ;;
          47494638) mime="image/gif" ;;
          25504446) mime="application/pdf" ;;
        esac
        ;;
    esac

    # Only re-upload if we have a meaningful type
    if [[ "$mime" != "application/octet-stream" && "$mime" != "binary/octet-stream" ]]; then
      aws s3 cp "s3://$BUCKET/$key" "s3://$BUCKET/$key" \
        --content-type "$mime" \
        --cache-control "public, max-age=300" \
        --metadata-directive REPLACE \
        --no-progress 2>/dev/null || echo "WARN: failed to fix $key"
    fi
  done
else
  echo ">>> Skipping MIME fix (pass --fix-mime as 3rd arg to run)"
fi

# Step 3: Invalidate CloudFront cache
echo ">>> Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/*" \
  --no-cli-pager

echo ">>> Deploy complete!"
echo "    Site: https://$(aws cloudfront get-distribution --id "$DIST_ID" --query 'Distribution.DomainName' --output text --no-cli-pager 2>/dev/null || echo "$DIST_ID.cloudfront.net")"
