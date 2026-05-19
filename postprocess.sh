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

# 2b. Strip language prefix from /en/indonesia/ links (mirror is single-language)
echo ">>> Stripping language prefix from internal links..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|"/[a-z]{2}/indonesia/|"/indonesia/|g' "$f"
  "${SED_INPLACE[@]}" -E "s|'/[a-z]{2}/indonesia/|'/indonesia/|g" "$f"
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

# 6b. Remove loading="lazy" from hero/above-the-fold images
#     Lazy loading on hero images prevents them from loading in static context
echo ">>> Removing loading=lazy from all images (static site doesn't need it)..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's| loading="lazy"||g' "$f"
done

# 6c. Fix zero-width images left after adaptive-media source removal
#     Liferay sets <img class="w-0"> as fallback; without <source> tags it needs to be visible
echo ">>> Fixing zero-width fallback images..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|class="w-0"|class="w-100"|g' "$f"
done

# 6d. Style "Learn more" modal buttons and inject static site CSS fixes
echo ">>> Injecting static site CSS fixes..."
STATIC_CSS='<style>.vale-fragmento-link-para-modal>button.btn-unstyled{background-color:var(--amarelo-vale,#D4A843);color:#fff;padding:.75rem 2rem;border-radius:0;text-align:center;display:inline-flex!important;width:auto!important;cursor:pointer;border:none;margin-top:1rem}.vale-fragmento-link-para-modal>button.btn-unstyled:hover{opacity:.85}.vale-fragmento-link-para-modal>button.btn-unstyled p{margin:0;color:#fff;font-weight:600}</style>'
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" "s|</head>|${STATIC_CSS}</head>|" "$f"
done

# 6e. Inject Liferay event system polyfill and Analytics stub
#     The static mirror is missing AUI JS modules that provide Liferay.fire/on/detach.
#     Without these, the burger menu and other event-driven UI breaks.
#     Also stub Analytics.track() to prevent ReferenceErrors in tracking code.
echo ">>> Injecting Liferay event polyfill and Analytics stub..."
for f in "${HTML_FILES[@]}"; do
  perl -pi -e 's{</head>}{<script>!function(){if(!window.Liferay)return;var e={};Liferay.on=function(t,c){e[t]||(e[t]=[]);e[t].push(c)};Liferay.fire=function(t,d){(e[t]||[]).forEach(function(c){c(d||{})})};Liferay.detach=function(t,c){if(e[t]){if(c){e[t]=e[t].filter(function(f){return f!==c})}else{e[t]=[]}}};Liferay.publish=function(){};window.Analytics=window.Analytics||{track:function(){},send:function(){}}}();</script></head>}' "$f"
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

# 9. Fix query params in /documents/ URLs to match wget's filename mangling
#    wget --restrict-file-names=windows converts ? to @, so URLs with ?version=
#    need to use @version= to match the files on disk
echo ">>> Fixing document URL query params to match wget filenames..."
for f in "${HTML_FILES[@]}"; do
  # In src/href attributes pointing to /documents/, replace ? with @
  "${SED_INPLACE[@]}" -E 's|(src="/documents/[^"]*)\?|\1@|g' "$f"
  "${SED_INPLACE[@]}" -E 's|(href="/documents/[^"]*)\?|\1@|g' "$f"
  # Also fix srcset attributes
  "${SED_INPLACE[@]}" -E 's|(srcset="/documents/[^"]*)\?|\1@|g' "$f"
done

# 9b. Collapse UUID filenames: documents/.../image.png/UUID@version=X → documents/.../image.png
#     S3/CloudFront can't handle @, =, & in key names via HTTP URLs
echo ">>> Collapsing UUID document filenames..."
# First collapse files on disk
find "$SITE_DIR/documents" -type f -path '*@version*' -print0 2>/dev/null | while IFS= read -r -d '' filepath; do
  parent_dir=$(dirname "$filepath")
  grandparent=$(dirname "$parent_dir")
  parent_name=$(basename "$parent_dir")
  # parent_name is like "image.png" — move the file up as that name
  newpath="$grandparent/$parent_name"
  if [[ "$filepath" != "$newpath" ]]; then
    # Move file to temp location, remove the directory, then rename
    tmppath="$grandparent/.tmp_collapse_$$"
    mv -- "$filepath" "$tmppath" 2>/dev/null || continue
    rm -rf -- "$parent_dir" 2>/dev/null || true
    mv -- "$tmppath" "$newpath" 2>/dev/null || true
  fi
done
# Also handle &t= files without @version
find "$SITE_DIR/documents" -type f -name '*&t=*' -print0 2>/dev/null | while IFS= read -r -d '' filepath; do
  newpath=$(echo "$filepath" | sed -E 's/&t=[0-9]+//')
  if [[ "$filepath" != "$newpath" ]]; then
    mkdir -p "$(dirname "$newpath")"
    mv "$filepath" "$newpath" || true
  fi
done
# Now fix HTML references: strip /UUID@version=X(&t=...) from document URLs
for f in "${HTML_FILES[@]}"; do
  # src="/documents/.../image.png/UUID@version=X&amp;t=..." → src="/documents/.../image.png"
  perl -pi -e 's{(src="/documents/[^"]+\.(?:png|jpg|jpeg|gif|svg|webp|pdf))/[^"]*"}{$1"}gi' "$f"
  perl -pi -e 's{(href="/documents/[^"]+\.(?:png|jpg|jpeg|gif|svg|webp|pdf))/[^"]*"}{$1"}gi' "$f"
done

# 9c. Convert %20 to + in document/asset URLs to match wget's filename encoding
#     wget saves spaces as + in filenames, but HTML uses %20
echo ">>> Converting %20 to + in document URLs..."
for f in "${HTML_FILES[@]}"; do
  # Use perl to replace %20 with + only inside src/href attributes pointing to /documents/
  perl -pi -e 's{((?:src|href|srcset)="/documents/)([^"]*)"}{my $p=$1; my $v=$2; $v=~s/%20/+/g; "$p$v\""}ge' "$f"
done

# 10. Append .html to internal /indonesia/ links that lack a file extension
#    e.g. href="/indonesia/board-of-directors" → href="/indonesia/board-of-directors.html"
#    Skip links that already have .html, have a hash, query param, or end with /
echo ">>> Appending .html to extensionless internal links..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|href="/indonesia/([a-zA-Z0-9_-]+)"([^.])|href="/indonesia/\1.html"\2|g' "$f"
  # Handle end-of-line case
  "${SED_INPLACE[@]}" -E 's|href="/indonesia/([a-zA-Z0-9_-]+)"$|href="/indonesia/\1.html"|g' "$f"
done

# 11. Flatten: move indonesia/* to root, rewrite /indonesia/ paths to /
echo ">>> Flattening indonesia/ to site root..."
# Copy indonesia subpages to root
if [[ -d "$SITE_DIR/indonesia" ]]; then
  cp -a "$SITE_DIR/indonesia/"* "$SITE_DIR/" 2>/dev/null || true
fi
# Copy indonesia.html as index.html (landing page)
if [[ -f "$SITE_DIR/indonesia.html" ]]; then
  cp "$SITE_DIR/indonesia.html" "$SITE_DIR/index.html"
fi

# Re-find HTML files after flatten (new files at root)
HTML_FILES=()
while IFS= read -r -d '' f; do
  HTML_FILES+=("$f")
done < <(find "$SITE_DIR" -name '*.html' -print0)

# Rewrite /indonesia/ links to / in all HTML
echo ">>> Rewriting /indonesia/ paths to /..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|href="/indonesia/|href="/|g' "$f"
  "${SED_INPLACE[@]}" -E 's|href="/indonesia\.html"|href="/"|g' "$f"
  "${SED_INPLACE[@]}" -E 's|action="/indonesia/|action="/|g' "$f"
done

# 11b. Append .html to root-level extensionless links (e.g. href="/our-history-in-indonesia")
#      Step 10 only caught /indonesia/ prefixed links; some were already root-relative
echo ">>> Appending .html to root-level extensionless links..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|href="/([a-zA-Z0-9_-]+)"([^.])|href="/\1.html"\2|g' "$f"
  "${SED_INPLACE[@]}" -E 's|href="/([a-zA-Z0-9_-]+)"$|href="/\1.html"|g' "$f"
done

# 12. Create 404 page
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
    <p><a href="/">Back to PT Vale Indonesia</a></p>
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
