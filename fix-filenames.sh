#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="./site/vale.com"

echo "=== Step 1: Rename '+' to spaces in filenames ==="
# Process deepest files first to avoid path conflicts
find "$SITE_DIR" -depth -name '*+*' | while read -r filepath; do
  dir=$(dirname "$filepath")
  base=$(basename "$filepath")
  newbase="${base//+/ }"
  if [[ "$base" != "$newbase" ]]; then
    mv "$filepath" "$dir/$newbase"
  fi
done
echo "    Done renaming + to spaces."

echo "=== Step 2: Add extensions to extensionless files ==="
# Only process files in documents/d/ which are the extensionless Liferay files
EXT_MAP_FILE=$(mktemp)
find "$SITE_DIR/documents/d" -type f ! -name '*.*' 2>/dev/null | while read -r filepath; do
  mime=$(file --brief --mime-type "$filepath" 2>/dev/null)
  ext=""
  case "$mime" in
    image/png) ext=".png" ;;
    image/jpeg) ext=".jpg" ;;
    image/gif) ext=".gif" ;;
    image/svg+xml) ext=".svg" ;;
    image/webp) ext=".webp" ;;
    application/pdf) ext=".pdf" ;;
    application/javascript|text/javascript) ext=".js" ;;
    text/css) ext=".css" ;;
    text/html|text/xml) ext=".html" ;;
    font/woff|application/font-woff) ext=".woff" ;;
    font/woff2) ext=".woff2" ;;
    font/ttf|application/x-font-ttf) ext=".ttf" ;;
    application/vnd.openxmlformats-officedocument.*) ext=".docx" ;;
    application/vnd.ms-excel) ext=".xls" ;;
    application/zip) ext=".zip" ;;
    application/gzip) ext=".gz" ;;
    application/octet-stream)
      # Try to detect from file content more carefully
      header=$(xxd -l 4 -p "$filepath" 2>/dev/null)
      case "$header" in
        89504e47) ext=".png" ;;
        ffd8ff*) ext=".jpg" ;;
        47494638) ext=".gif" ;;
        25504446) ext=".pdf" ;;
        504b0304) ext=".zip" ;;
        *) ext="" ;; # Can't determine, leave as-is
      esac
      ;;
    *) ext="" ;;
  esac

  if [[ -n "$ext" ]]; then
    newpath="${filepath}${ext}"
    mv "$filepath" "$newpath"
    # Record the mapping for HTML fixup: old_relative_path → new_relative_path
    old_rel="${filepath#$SITE_DIR}"
    new_rel="${newpath#$SITE_DIR}"
    echo "${old_rel}|${new_rel}" >> "$EXT_MAP_FILE"
  fi
done

ext_count=$(wc -l < "$EXT_MAP_FILE" | tr -d ' ')
echo "    Added extensions to $ext_count files."

echo "=== Step 3: Update HTML references for renamed files ==="
# Find all HTML files
HTML_FILES=()
while IFS= read -r -d '' f; do
  HTML_FILES+=("$f")
done < <(find "$SITE_DIR" -name '*.html' -print0)

echo "    Processing ${#HTML_FILES[@]} HTML files..."

# Build a sed script from the extension map
if [[ -s "$EXT_MAP_FILE" ]]; then
  SED_SCRIPT=$(mktemp)
  while IFS='|' read -r old_path new_path; do
    # Escape special chars for sed
    old_esc=$(printf '%s' "$old_path" | sed 's/[&/\]/\\&/g')
    new_esc=$(printf '%s' "$new_path" | sed 's/[&/\]/\\&/g')
    echo "s|\"${old_esc}\"|\"${new_esc}\"|g" >> "$SED_SCRIPT"
    # Also handle URL-encoded quotes and paths without leading /
    echo "s|'${old_esc}'|'${new_esc}'|g" >> "$SED_SCRIPT"
    # Handle url() references
    echo "s|url(${old_esc})|url(${new_esc})|g" >> "$SED_SCRIPT"
  done < "$EXT_MAP_FILE"

  for f in "${HTML_FILES[@]}"; do
    sed -i '' -f "$SED_SCRIPT" "$f"
  done
  rm -f "$SED_SCRIPT"
fi

rm -f "$EXT_MAP_FILE"

echo "=== Step 4: Fix @download=true suffixes ==="
# Files like "intro-imagem-1-png@download=true" should be renamed
find "$SITE_DIR/documents" -type f -name '*@download=true' 2>/dev/null | while read -r filepath; do
  newpath="${filepath/@download=true/}"
  if [[ "$filepath" != "$newpath" && ! -f "$newpath" ]]; then
    mv "$filepath" "$newpath"
    # Update HTML references
    old_rel="${filepath#$SITE_DIR}"
    new_rel="${newpath#$SITE_DIR}"
    old_esc=$(printf '%s' "$old_rel" | sed 's/[&/\]/\\&/g; s/@/\\@/g')
    new_esc=$(printf '%s' "$new_rel" | sed 's/[&/\]/\\&/g')
    for f in "${HTML_FILES[@]}"; do
      sed -i '' "s|${old_esc}|${new_esc}|g" "$f"
    done
  fi
done

echo "=== Complete ==="
echo "Now run: make deploy  (with AWS_PROFILE=vale-id)"
