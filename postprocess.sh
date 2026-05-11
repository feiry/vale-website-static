#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="./site/vale.com"
MIGRATION_NOTES="./MIGRATION_NOTES.md"

if [[ ! -d "$SITE_DIR" ]]; then
  echo "ERROR: $SITE_DIR not found. Run crawl.sh first."
  exit 1
fi

# Detect sed flavor (macOS vs GNU)
if sed --version 2>/dev/null | grep -q GNU; then
  SED_INPLACE=(sed -i)
else
  SED_INPLACE=(sed -i '')
fi

echo ">>> Post-processing HTML files..."

# Find all HTML files
HTML_FILES=()
while IFS= read -r -d '' f; do
  HTML_FILES+=("$f")
done < <(find "$SITE_DIR" -name '*.html' -print0)

echo "    Found ${#HTML_FILES[@]} HTML files"

# 1. Strip Liferay class names from alt attributes
#    Pattern: com.liferay.portal.kernel.util.DateUtil_IW@<hex>
echo ">>> Stripping Liferay class names from alt attributes..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's/alt="com\.liferay\.[^"]*"/alt=""/g' "$f"
done

# 2. Rewrite absolute vale.com URLs to root-relative
echo ">>> Rewriting absolute URLs to root-relative..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|https?://vale\.com/|/|g' "$f"
  "${SED_INPLACE[@]}" -E 's|https?://www\.vale\.com/|/|g' "$f"
done

# 3. Remove Google Tag Manager noscript iframe
echo ">>> Removing GTM noscript iframe..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" '/<noscript>.*googletagmanager\.com.*<\/noscript>/d' "$f"
  # Multi-line GTM removal (noscript block)
  "${SED_INPLACE[@]}" '/<noscript><iframe src="https:\/\/www\.googletagmanager\.com/,/<\/noscript>/d' "$f"
done

# 4. Remove GTM script tags
echo ">>> Removing GTM script tags..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" '/googletagmanager\.com\/gtm\.js/d' "$f"
  "${SED_INPLACE[@]}" "/GTM-TXBLVPM/d" "$f"
done

# 5. Neutralize cookie preference links pointing to Liferay endpoints
echo ">>> Neutralizing cookie preference links..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|href="[^"]*cookie[^"]*preferences[^"]*"|href="#" data-disabled="cookie-preferences"|gi' "$f"
done

# 6. Remove <source> tags pointing to /o/adaptive-media/ (Liferay image resizer)
#    Browsers will fall back to the <img> tag which has working /documents/ paths
#    Use substitution (not line deletion) since <picture><source><img> may be on one line
echo ">>> Removing adaptive-media source tags..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|<source[^>]*adaptive-media[^>]*/?>||g' "$f"
done

# 7. Fix submenu images that got incorrectly rewritten to "indonesia.html"
echo ">>> Fixing broken submenu image references..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|src="/indonesia\.html"|src="" style="display:none"|g' "$f"
  "${SED_INPLACE[@]}" -E 's|src="indonesia\.html"|src="" style="display:none"|g' "$f"
done

# 8. Rewrite relative asset paths to root-absolute
#    wget --convert-links produces relative paths like "o/..." or "../o/..."
#    which break depending on directory depth. Convert to absolute "/o/...", "/documents/..."
echo ">>> Rewriting relative asset paths to root-absolute..."
for f in "${HTML_FILES[@]}"; do
  # href="o/..." → href="/o/..."
  "${SED_INPLACE[@]}" -E 's|(href=")(\.\./)*o/|\1/o/|g' "$f"
  # src="o/..." → src="/o/..."
  "${SED_INPLACE[@]}" -E 's|(src=")(\.\./)*o/|\1/o/|g' "$f"
  # href="documents/..." → href="/documents/..."
  "${SED_INPLACE[@]}" -E 's|(href=")(\.\./)*documents/|\1/documents/|g' "$f"
  # src="documents/..." → src="/documents/..."
  "${SED_INPLACE[@]}" -E 's|(src=")(\.\./)*documents/|\1/documents/|g' "$f"
  # href="indonesia..." → href="/indonesia..."  (nav links)
  "${SED_INPLACE[@]}" -E 's|(href=")(\.\./)*indonesia|\1/indonesia|g' "$f"
  # url(...) in inline styles
  "${SED_INPLACE[@]}" -E 's|(url\()(\.\./)*documents/|\1/documents/|g' "$f"
  "${SED_INPLACE[@]}" -E 's|(url\()(\.\./)*o/|\1/o/|g' "$f"
done

# 7. Fix directory index: indonesia.html → indonesia/index.html
echo ">>> Fixing directory index files..."
if [[ -f "$SITE_DIR/indonesia.html" && -d "$SITE_DIR/indonesia" ]]; then
  cp "$SITE_DIR/indonesia.html" "$SITE_DIR/indonesia/index.html"
  echo "    Copied indonesia.html → indonesia/index.html"
fi

# 7. Create 404 page
echo ">>> Creating 404 page..."
cat > "$SITE_DIR/404.html" << 'EOF404'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Page Not Found — PT Vale Indonesia</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; background: #f5f5f5; color: #333; }
    .container { text-align: center; max-width: 480px; padding: 2rem; }
    h1 { font-size: 3rem; color: #008542; margin-bottom: 0.5rem; }
    p { font-size: 1.1rem; line-height: 1.6; }
    a { color: #008542; text-decoration: none; font-weight: 600; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <h1>404</h1>
    <p>The page you're looking for doesn't exist.</p>
    <p><a href="/indonesia/">Back to PT Vale Indonesia</a></p>
  </div>
</body>
</html>
EOF404

# 8. Generate migration notes — scan for forms, API calls, dynamic features
echo ">>> Generating migration notes..."
cat > "$MIGRATION_NOTES" << 'HEADER'
# Migration Notes — Vale Indonesia Static Mirror

Generated by `postprocess.sh`. Lists dynamic features dropped or redirected
during the static mirror process.

## External Form Actions
HEADER

# Find form actions
echo "" >> "$MIGRATION_NOTES"
{ grep -roh 'action="[^"]*"' "$SITE_DIR" --include='*.html' || true; } | sort -u | while read -r action; do
  echo "- \`$action\`" >> "$MIGRATION_NOTES"
done

cat >> "$MIGRATION_NOTES" << 'SECTION'

## External API / AJAX Calls
SECTION

# Find fetch/XMLHttpRequest/ajax patterns
echo "" >> "$MIGRATION_NOTES"
{ grep -roh "fetch(['\"][^'\"]*['\"]" "$SITE_DIR" --include='*.html' || true; } | sort -u | while read -r call; do
  echo "- \`$call\`" >> "$MIGRATION_NOTES"
done
{ grep -roh "\.ajax({[^}]*url:[^}]*}" "$SITE_DIR" --include='*.html' || true; } | sort -u | while read -r call; do
  echo "- \`$call\`" >> "$MIGRATION_NOTES"
done

cat >> "$MIGRATION_NOTES" << 'SECTION'

## External Links (kept intact)
SECTION

echo "" >> "$MIGRATION_NOTES"
{ grep -roh 'href="https://eproc\.valeindonesia[^"]*"' "$SITE_DIR" --include='*.html' || true; } | sort -u | while read -r link; do
  echo "- Supplier portal: \`$link\`" >> "$MIGRATION_NOTES"
done
{ grep -roh 'href="[^"]*deloitte[^"]*"' "$SITE_DIR" --include='*.html' || true; } | sort -u | while read -r link; do
  echo "- Whistleblower: \`$link\`" >> "$MIGRATION_NOTES"
done

cat >> "$MIGRATION_NOTES" << 'SECTION'

## Dropped Features

- **Site search**: Replaced by Pagefind static search
- **Language selector**: 14-language selector removed (static mirror is English/Indonesian only)
- **Senna.js SPA navigation**: Removed (static pages load normally)
- **Cookie consent banner**: Neutralized (will add own analytics later)
- **Google Tag Manager**: Removed (GTM-TXBLVPM)

## Pagination / Dynamic Listings

- **News listing** (`/indonesia/all-news`): May be paginated dynamically via Liferay.
  Only pages reachable by static links are mirrored. Manual review needed.

## TODO

- [ ] Decide: add own analytics (GA4 / Plausible / etc.)
- [ ] Decide: implement contact forms or keep external links
- [ ] Review news pagination — may need custom crawl logic
SECTION

echo ">>> Migration notes written to $MIGRATION_NOTES"
echo ">>> Post-processing complete."
