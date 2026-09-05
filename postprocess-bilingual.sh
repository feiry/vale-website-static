#!/usr/bin/env bash
set -euo pipefail

# BILINGUAL post-process. Differs from postprocess.sh (EN-only) in three ways:
#   - section 2b strips only FOREIGN locale prefixes (ar/de/fr/...), preserving /in/ (ID)
#   - section 10 appends .html to BOTH /indonesia/ and /in/indonesia/ links
#   - NO flatten (old sections 11/11b removed): EN stays at /indonesia/, ID at /in/indonesia/
#     mirroring the live Vale URL structure exactly.
# All other fixes (Liferay alt strip, GTM removal, asset path rewrite, doc URL fixes,
# safe UUID collapse, polyfill) are language-agnostic and kept as-is.

SITE_DIR="${SITE_DIR:-./site/vale.com}"
MIGRATION_NOTES="${MIGRATION_NOTES:-./MIGRATION_NOTES.md}"

if [[ ! -d "$SITE_DIR" ]]; then
  echo "ERROR: $SITE_DIR not found. Run the crawl first."
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

# 2b. Strip FOREIGN language-locale prefixes from internal links, but PRESERVE /in/ (ID).
#     The live site links to 14 locales (/ar/, /de/, /fr/, ...). We keep only EN (/indonesia/)
#     and ID (/in/indonesia/); every other locale link is rewritten to the EN path so it
#     resolves within the mirror. NOTE: must NOT touch /in/indonesia/ — that's our Bahasa tree.
echo ">>> Stripping FOREIGN locale prefixes (preserving /in/ ID)..."
# Loop per-locale instead of (a|b) alternation — BSD sed (macOS) doesn't support
# alternation even with -E; this form is portable to BSD and GNU sed alike.
FOREIGN_LOCALES="ar ca de es fi fr hu ja nl pt sv zh"
for f in "${HTML_FILES[@]}"; do
  for loc in $FOREIGN_LOCALES; do
    "${SED_INPLACE[@]}" -E "s|\"/$loc/indonesia/|\"/indonesia/|g" "$f"
    "${SED_INPLACE[@]}" -E "s|'/$loc/indonesia/|'/indonesia/|g" "$f"
  done
done

# 2b-2. The EN locale prefix `/en/indonesia/<slug>` is a BROKEN link in our mirror — live
#       serves English at /indonesia/ (no /en/), so `/en/indonesia/sawerigading...` 404s.
#       'en' is deliberately NOT in FOREIGN_LOCALES (it's a real language), so the loop above
#       skips it. Rewrite `/en/indonesia/<slug>` → `/indonesia/<slug>.html` (append .html since
#       these are extensionless; §10 won't catch them once the /en/ prefix is stripped).
#       (Found 2026-09-03: Biodiversity's Sawerigading link + ~15 others were broken this way.)
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" -E 's|href="/en/indonesia/([a-z0-9-]+)"|href="/indonesia/\1.html"|g' "$f"
  "${SED_INPLACE[@]}" -E "s|href='/en/indonesia/([a-z0-9-]+)'|href='/indonesia/\1.html'|g" "$f"
done

# 3. Remove Google Tag Manager noscript iframe
echo ">>> Removing GTM noscript iframe..."
for f in "${HTML_FILES[@]}"; do
  "${SED_INPLACE[@]}" '/<noscript>.*googletagmanager\.com.*<\/noscript>/d' "$f"
  # Multi-line GTM removal (noscript block)
  "${SED_INPLACE[@]}" '/<noscript><iframe src="https:\/\/www\.googletagmanager\.com/,/<\/noscript>/d' "$f"
  # BARE GTM iframe not wrapped in <noscript> and/or inline (the sed rules above miss these):
  # some pages (tahapan-perekrutan, covid-19, esg-target, sustainability-report, ...) carry a
  # standalone hidden GTM tracking iframe. Strip it regardless of wrapping/whitespace so no
  # cloned page loads a tracker (keeps the static mirror cookie-free — see cookie-consent note).
  perl -0777 -i -pe 's{<iframe[^>]*googletagmanager\.com/ns\.html[^>]*>(\s*</iframe>)?}{}gis' "$f"
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

# 7b. Fix language-toggle (EN/ID) links that point to Liferay's dynamic endpoint.
#     The clone keeps href="/c/portal/update_language?...&languageId=en_US" (and =in_ID),
#     which 404s on a static host (no server to swap language). Repoint each toggle to the
#     static twin page. The twin URL is available in the page's own hreflang <link> alternate:
#       ID page: <link hreflang="en-US" href="/indonesia/<en-slug>.html">  -> EN button target
#       EN page: <link hreflang="in-ID" href="/in/indonesia/<id-slug>.html"> -> ID button target
#     If no hreflang alternate is found, leave the link untouched (better a dead toggle than a wrong page).
echo ">>> Fixing language-toggle (update_language) links to static twins..."
for f in "${HTML_FILES[@]}"; do
  perl -0777 -i -pe '
    # Attribute order varies (href before OR after hreflang), so match the whole <link ... rel="alternate">
    # tag containing the right hreflang, then pull href out of it regardless of position.
    # EN button: find the en-US alternate <link>, extract its /indonesia/... href.
    # Tolerate hreflang href WITHOUT .html (this pass may run before .html is appended) — add it.
    for my $tag ($_ =~ /(<link\b[^>]*\bhreflang="en[^"]*"[^>]*>)/gi) {
      if (my ($en) = $tag =~ /href="(\/indonesia\/[^"]+?)(?:\.html)?"/i) {
        $en .= ".html" unless $en =~ /\.html$/;
        s{href="/c/portal/update_language\?[^"]*languageId=en_US"}{href="$en"}g;
        last;
      }
    }
    # ID button: find the in-ID/id alternate <link>, extract its /in/indonesia/... href.
    for my $tag ($_ =~ /(<link\b[^>]*\bhreflang="(?:in|id)[^"]*"[^>]*>)/gi) {
      if (my ($id) = $tag =~ /href="(\/in\/indonesia\/[^"]+?)(?:\.html)?"/i) {
        $id .= ".html" unless $id =~ /\.html$/;
        s{href="/c/portal/update_language\?[^"]*languageId=in_ID"}{href="$id"}g;
        last;
      }
    }
  ' "$f"
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
#     S3/CloudFront/Azure can't handle @, =, & in key names via HTTP URLs.
#     Delegated to collapse-documents.sh — the previous inline loops did
#     `mv one file; rm -rf parent_dir`, which silently destroyed sibling files when a
#     human-filename dir held MULTIPLE versioned entries (data loss; see
#     docs/crawl-prep/test-collapse.sh for the regression test). The extracted script
#     keeps the highest version, preserves losing versions as <name>.v<ver>, and never
#     rm -rf's a dir that could hold unrelated content (e.g. documents/d/guest/*).
echo ">>> Collapsing UUID document filenames (safe)..."
"$(dirname "$0")/collapse-documents.sh" "$SITE_DIR"
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

# 10. Append .html to extensionless internal links for BOTH languages.
#    EN: href="/indonesia/board-of-directors"      → .../board-of-directors.html
#    ID: href="/in/indonesia/dewan-komisaris"      → .../dewan-komisaris.html
#    Also handle deeper ESG paths (/indonesia/esg/foo, /in/indonesia/esg/foo).
#    Skip links that already have .html, a hash, query param, or trailing slash.
echo ">>> Appending .html to extensionless internal links (EN + ID)..."
for f in "${HTML_FILES[@]}"; do
  # one or more path segments after /indonesia/ or /in/indonesia/, last segment gets .html
  "${SED_INPLACE[@]}" -E 's|href="(/(in/)?indonesia(/[a-zA-Z0-9_-]+)*)/([a-zA-Z0-9_-]+)"([^.])|href="\1/\4.html"\5|g' "$f"
  "${SED_INPLACE[@]}" -E 's|href="(/(in/)?indonesia(/[a-zA-Z0-9_-]+)*)/([a-zA-Z0-9_-]+)"$|href="\1/\4.html"|g' "$f"
  # bare /indonesia and /in/indonesia (the landing pages) → /indonesia.html, /in/indonesia.html
  "${SED_INPLACE[@]}" -E 's|href="/indonesia"([^.])|href="/indonesia.html"\1|g' "$f"
  "${SED_INPLACE[@]}" -E 's|href="/in/indonesia"([^.])|href="/in/indonesia.html"\1|g' "$f"
done

# 11. NO FLATTEN (bilingual). EN stays under /indonesia/, ID under /in/indonesia/,
#     mirroring the live Vale URL structure. We only create a root index.html that
#     sends the bare domain to the EN landing page (the static-website index document).
echo ">>> Creating root index.html → /indonesia/ (no flatten)..."
cat > "$SITE_DIR/index.html" << 'EOFIDX'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="0; url=/indonesia.html">
  <link rel="canonical" href="/indonesia.html">
  <title>PT Vale Indonesia</title>
</head>
<body>
  <p>Redirecting to <a href="/indonesia.html">PT Vale Indonesia</a>…</p>
</body>
</html>
EOFIDX

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
# 13. Fix the floating scroll-to-top/bottom button on the two landing pages.
#     Two landing-page bugs made the button dead (Purbayu report, 2026-09-05):
#       (a) the scroll-arrow fragment is DUPLICATED — two .progress-arrow-container stacked at the
#           same fixed spot; the top one has a dead handler and swallows every real click.
#       (b) CSS `scroll-behavior:smooth` on <html> silently drops programmatic scrolls on these
#           pages, so even when the handler fires, scrollTo()/scrollBy()/scrollTop do nothing.
#     Fix (a) with a small DOMContentLoaded dedupe script; fix (b) by rewriting scrollToAndFocus()
#     to force scroll-behavior:auto + do its own rAF tween (with a direct-jump safety net).
#     Idempotent: guarded by the GDI-SCROLLFIX sentinel so re-runs don't stack.
echo ">>> Fixing landing-page scroll button (dedupe + smooth-scroll)..."
for home in "$SITE_DIR/indonesia.html" "$SITE_DIR/in/indonesia.html"; do
  [[ -f "$home" ]] || continue
  HOME_FILE="$home" python3 - << 'PYEOF'
import os, re

path = os.environ["HOME_FILE"]
with open(path, encoding="utf-8") as fh:
    html = fh.read()

if "GDI-SCROLLFIX" in html or "dedupeScrollArrow" in html:
    raise SystemExit(0)  # already patched (idempotent; matches this step or an earlier hand-patch)

changed = False

# --- Fix (b): rewrite the smooth scrollTo in scrollToAndFocus() ---
old_block = '''  scrollingElement.scrollTo({
    top: targetTop,
    behavior: prefersReducedMotion ? "auto" : "smooth",
  });

  window.requestAnimationFrame(() => {
    focusRegionStart(target, triggerElement, preferLast);
  });'''

new_block = '''  /* GDI-SCROLLFIX: CSS scroll-behavior:smooth on <html> silently drops programmatic scrolls on
     the landing page. Force scroll-behavior:auto, run our own rAF tween, and fall back to a
     direct jump if rAF is throttled. Restore the previous inline value at the end. */
  (function gdiScrollFix() {
    var scrollEl = (scrollingElement === document.scrollingElement)
      ? document.documentElement : scrollingElement;
    var prevBehavior = scrollEl.style.scrollBehavior;
    scrollEl.style.setProperty("scroll-behavior", "auto", "important");
    function restore() {
      scrollEl.style.scrollBehavior = prevBehavior;
      focusRegionStart(target, triggerElement, preferLast);
    }
    if (prefersReducedMotion) { scrollingElement.scrollTop = targetTop; restore(); return; }
    var startTop = scrollingElement.scrollTop;
    var delta = targetTop - startTop;
    var duration = 500, startTime = null;
    function step(now) {
      if (startTime === null) startTime = now;
      var t = Math.min(1, (now - startTime) / duration);
      var eased = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      scrollingElement.scrollTop = startTop + delta * eased;
      if (t < 1) { window.requestAnimationFrame(step); } else { restore(); }
    }
    window.requestAnimationFrame(step);
    window.setTimeout(function () {
      if (Math.abs(scrollingElement.scrollTop - targetTop) > 4) {
        scrollingElement.scrollTop = targetTop; restore();
      }
    }, 800);
  })();'''

n = html.count(old_block)
if n:
    html = html.replace(old_block, new_block)
    changed = True

# --- Fix (a): dedupe the duplicated scroll button, injected before </body> ---
dedupe = '''<script>
/* GDI-SCROLLFIX: the scroll-arrow fragment is duplicated on this page (two
   .progress-arrow-container stacked); the top duplicate has a dead handler and swallows clicks.
   Remove all but the first (working) one so real clicks reach it. */
(function () {
  function dedupeScrollArrow() {
    var btns = document.querySelectorAll(".progress-arrow-container");
    for (var i = 1; i < btns.length; i++) {
      var wrap = btns[i].closest(".vale-fragmento-seta-de-progresso") || btns[i];
      wrap.parentNode && wrap.parentNode.removeChild(wrap);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", dedupeScrollArrow);
  } else { dedupeScrollArrow(); }
})();
</script>
</body>'''
if "</body>" in html and "dedupeScrollArrow" not in html:
    html = html.replace("</body>", dedupe, 1)
    changed = True

if changed:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("    patched " + os.path.relpath(path))
else:
    print("    WARNING: scroll-fix anchors not found in " + os.path.relpath(path))
PYEOF
done

# 14. Fix footer sub-column alignment (SITEWIDE — the footer is on every page).
#     The footer link lists used `columns: 2` (@media min-width:992px), which balances the two
#     sub-columns by HEIGHT so the 2nd sub-column started lower (uneven tops) — worsened by
#     2-line items and the A+/A- font control. Replace with CSS grid + a fixed row count so both
#     sub-columns always top-align, independent of content height / wrapping / font size.
#     Desktop-only (the mobile/tablet footer is a separate single-column menu). Idempotent.
echo ">>> Fixing footer sub-column alignment (sitewide)..."
for f in "${HTML_FILES[@]}"; do
  HTML_FILE="$f" python3 - << 'PYEOF'
import os, re
path = os.environ["HTML_FILE"]
html = open(path, encoding="utf-8").read()
if "grid-auto-flow: column" in html and "columns: 2;" not in html:
    raise SystemExit(0)  # already fixed
# Match the columns:2 rule block, capturing the leading indent of the selector line.
pat = re.compile(
    r'([ \t]*)\.vale-fragmento-footer \.desktop-content ul \{\s*'
    r'columns:\s*2;\s*-moz-columns:\s*2;\s*-webkit-columns:\s*2;\s*\}',
    re.MULTILINE)
def repl(m):
    ind = m.group(1); b = ind + "  "
    return (f'{ind}/* GDI-FOOTERGRID: footer sub-columns top-aligned via CSS grid (was columns:2,\n'
            f'{ind}   which balanced by height so the 2nd sub-column started lower). Desktop-only. */\n'
            f'{ind}.vale-fragmento-footer .desktop-content ul {{\n'
            f'{b}display: grid;\n{b}grid-template-columns: 1fr 1fr;\n{b}grid-template-rows: repeat(4, auto);\n'
            f'{b}grid-auto-flow: column;\n{b}column-gap: 1rem;\n{b}align-content: start;\n{ind}}}')
new, n = pat.subn(repl, html)
if n:
    open(path, "w", encoding="utf-8").write(new)
PYEOF
done

# 15. Swap the homepage promo popup to the COMMs domain-change media (landing pages only).
#     Points the popup image + button at the Domain Change Notification PDF, uses the horizontal
#     media, and caps the image so it fits one screen without distortion (natural ratio preserved).
#     Idempotent (guarded by GDI-POPUP marker). Only touches pages that carry the #modal-tvhs popup.
echo ">>> Applying domain-change popup (landing pages)..."
# Ensure the popup image is on disk (source of truth lives in docs/, which is tracked; site/ is not).
POPUP_IMG_DIR="$SITE_DIR/documents/44618/1068266"
POPUP_IMG="$POPUP_IMG_DIR/popup-domain-change-2026-09-h.jpg"
if [[ ! -f "$POPUP_IMG" && -f "docs/New-Popup_Media-horizontal.jpeg" ]]; then
  mkdir -p "$POPUP_IMG_DIR"
  cp "docs/New-Popup_Media-horizontal.jpeg" "$POPUP_IMG"
  echo "    placed popup image: ${POPUP_IMG#$SITE_DIR/}"
fi
for home in "$SITE_DIR/indonesia.html" "$SITE_DIR/in/indonesia.html"; do
  [[ -f "$home" ]] || continue
  HOME_FILE="$home" python3 - << 'PYEOF'
import os, re
path = os.environ["HOME_FILE"]
html = open(path, encoding="utf-8").read()
if 'id="modal-tvhs"' not in html:
    raise SystemExit(0)  # no popup on this page
if "GDI-POPUP" in html and "popup-domain-change-2026-09-h.jpg" in html:
    raise SystemExit(0)  # already applied

changed = False
PDF = "/documents/44618/1438416/Domain+Change+Notification.pdf"
IMG = "/documents/44618/1068266/popup-domain-change-2026-09-h.jpg"

# Isolate ONLY the #modal-tvhs popup block so link/image/button edits never touch the many
# identical "Investor Relation Publications" (ir-publications) links elsewhere on the page.
mstart = html.find('id="modal-tvhs"')
open_div = html.rfind("<div", 0, mstart)          # the modal's opening <div ... id="modal-tvhs">
# walk forward to the matching </div> for that opening div
depth = 0; i = open_div; end = -1
for m in re.finditer(r'<div\b|</div>', html[open_div:]):
    depth += 1 if m.group(0) == "<div" else -1
    if depth == 0:
        end = open_div + m.end(); break
if open_div != -1 and end != -1:
    block = html[open_div:end]
    orig_block = block
    # a) point the popup image + button links at the PDF (whatever the current target is:
    #    ir-publications / publikasi-ir, absolute vale.com or root-relative)
    block = re.sub(r'href="[^"]*(?:ir-publications|publikasi-ir)\.html"', f'href="{PDF}"', block)
    # b) swap the image src (old AR-2025 image or the portrait interim → the horizontal media)
    block = re.sub(r'/documents/44618/1068266/pop-up-AR-2025[^"]*\.jpg', IMG, block)
    block = block.replace("/documents/44618/1068266/popup-domain-change-2026-09.jpg", IMG)
    # c) button label → domain-change CTA (EN + ID)
    block = block.replace("Read our 2025 Annual Report &amp; Sustainability Report", "Read the Domain Change Notification")
    block = block.replace("Baca Laporan Tahunan &amp; Laporan Keberlanjutan 2025", "Baca Pemberitahuan Perubahan Domain")
    if block != orig_block:
        html = html[:open_div] + block + html[end:]; changed = True

# d) cap the popup image so a landscape/portrait media fits one screen without distortion
if "GDI-POPUP" not in html:
    css = ('\n/* GDI-POPUP: cap the popup image to fit one screen at its natural ratio (override w-100). */\n'
           '.vale-fragmento-modal-popup.modal .modal-content .component-image img {\n'
           '  width: auto !important; height: auto !important; max-width: 100%;\n'
           '  max-height: 70vh; object-fit: contain; margin: 0 auto; display: block;\n}\n')
    m = re.search(r'(\.vale-fragmento-modal-popup\.modal \.modal-content \{[^}]*\})', html)
    if m:
        html = html[:m.end()] + css + html[m.end():]; changed = True

if changed:
    open(path, "w", encoding="utf-8").write(html)
    print("    popup applied: " + os.path.relpath(path))
PYEOF
done

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
