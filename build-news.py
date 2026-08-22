#!/usr/bin/env python3
"""build-news.py — Static news page generator for the Vale Indonesia mirror.

Reads site-data/news.json and generates:
  site/vale.com/indonesia/all-news.html         (EN listing)
  site/vale.com/in/indonesia/all-news.html      (ID listing)
  site/vale.com/indonesia/w/<slug>.html         (EN article pages)
  site/vale.com/in/indonesia/w/<slug>.html      (ID article pages)

Also rewrites existing /w/<slug>/-/categories/N links in the mirror to the
new static .html paths, and reports any /w/ links whose slugs are not in data.

Usage:
  python3 build-news.py            # normal build
  python3 build-news.py --dry-run  # print stats, write nothing

Guardrails:
  - Invalid JSON            → abort with line/column message
  - Missing date or title   → skip record with warning naming slug
  - Duplicate slug          → warning, last occurrence wins
  - Orphan generated files  → warning (files whose slug no longer in data)

Fully idempotent: running twice produces identical output.
"""

import json
import os
import re
import sys
import html as html_mod
import unicodedata
from datetime import datetime
from urllib.parse import unquote

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# news.json is the FULL master export (995 articles incl. global Vale content).
# news-indonesia.json is the published scope — only PT Vale Indonesia news, per
# Ibu Sri's curated CSV list (KEEP = on her list OR genuine Indonesia-local tag,
# excluding global). Build from the Indonesia set; regenerate it via the
# reconciliation when the master export or her list changes.
DATA_FILE = os.path.join(SCRIPT_DIR, "site-data", "news-indonesia.json")
SITE_ROOT = os.path.join(SCRIPT_DIR, "site", "vale.com")

# Chrome source pages (known-good mirror pages to extract header/footer from)
EN_CHROME_SRC = os.path.join(SITE_ROOT, "indonesia", "about-pt-vale-indonesia.html")
ID_CHROME_SRC = os.path.join(SITE_ROOT, "in", "indonesia", "esg.html")

# Output directories
EN_LISTING_PATH = os.path.join(SITE_ROOT, "indonesia", "all-news.html")
ID_LISTING_PATH = os.path.join(SITE_ROOT, "in", "indonesia", "all-news.html")
EN_ARTICLE_DIR = os.path.join(SITE_ROOT, "indonesia", "w")
ID_ARTICLE_DIR = os.path.join(SITE_ROOT, "in", "indonesia", "w")

# Homepage files whose dynamic "latest news" carousel we pre-render statically
EN_HOME_PATH = os.path.join(SITE_ROOT, "indonesia.html")
ID_HOME_PATH = os.path.join(SITE_ROOT, "in", "indonesia.html")
HOME_HIGHLIGHT_COUNT = 6
# Categories marking an article as genuinely Indonesia-LOCAL news (preferred on the
# homepage). Note: the broad "Indonesia" region tag is also applied to global corporate
# news (blanket-tagged to every country), so it is deliberately excluded here — only the
# local "Indonesia news"/"Indonesia ESG" tags reliably indicate local content.
INDONESIA_CATS = {"Indonesia news", "Indonesia ESG"}
# Markers delimiting the empty carousel wrapper we inject slides into
HOME_WRAPPER_OPEN = '<div class="swiper-carrosel'
HOME_WRAPPER_INNER_OPEN = '<div class="swiper-wrapper">'
# Sentinel comment so re-runs replace our injected block instead of stacking
HOME_INJECT_START = "<!-- static-news-highlight:start -->"
HOME_INJECT_END = "<!-- static-news-highlight:end -->"

# Marker strings used to split chrome source into header + footer
MAIN_CONTENT_MARKER = '<div class="layout-content portlet-layout"id="main-content"'
FOOTER_MARKER = '<div class="lfr-layout-structure-item-footer--copiar-'

# Default cover image used when a record has no cover set
DEFAULT_COVER = "/o/vale-theme/images/default-news-cover.png"

# ─── Duplicate-image detection (cover vs first body image) ────────────────────
import hashlib
from urllib.parse import unquote as _unquote

_MD5_CACHE = {}

def _md5_of(src):
    """md5 of the local file a /documents/... src points to, or None if absent.
    Normalizes the src first (strips trailing /<uuid> + ?query) so a cover URL in
    the '/documents/<id>/name.jpg/<uuid>' form resolves to the same on-disk file as
    its '/documents/d/guest/name-jpg' body-image twin — otherwise the duplicate
    cover header (same photo shown twice) is never detected."""
    if not src or not src.startswith("/documents/"):
        return None
    if src in _MD5_CACHE:
        return _MD5_CACHE[src]
    rel = _unquote(_served_cover_path(src)).lstrip("/")
    path = os.path.join(SITE_ROOT, rel)
    digest = None
    try:
        with open(path, "rb") as f:
            digest = hashlib.md5(f.read()).hexdigest()
    except OSError:
        digest = None
    _MD5_CACHE[src] = digest
    return digest

def _same_image_bytes(a, b):
    """True only if both srcs resolve to local files with identical bytes."""
    da = _md5_of(a)
    db = _md5_of(b)
    return da is not None and da == db

def _served_cover_path(src):
    """Normalize a Liferay document URL to the path the mirror actually stores.
    Cover URLs look like '/documents/44618/xxx/name.jpg/<uuid>?version=...' — the
    trailing /<uuid> segment (after the filename) and the ?query must be dropped so
    the path matches the on-disk file 'name.jpg'. Returns the cleaned /documents path."""
    if not src:
        return ""
    p = src.split("?", 1)[0]
    parts = p.rstrip("/").split("/")
    # Keep everything up to and including the last segment that has a file extension.
    for i in range(len(parts) - 1, -1, -1):
        if "." in parts[i]:
            return "/".join(parts[: i + 1])
    return p

def _local_exists(src):
    """True if a /documents/... src resolves to an actual FILE in the mirror.
    Must be a file, not a directory — some cover paths collide with a folder name,
    and os.path.exists() would wrongly pass for those. The src is normalized first
    (strips the trailing /<uuid> segment + ?query) so real covers aren't missed."""
    if not src or not src.startswith("/documents/"):
        return False
    rel = _unquote(_served_cover_path(src)).lstrip("/")
    return os.path.isfile(os.path.join(SITE_ROOT, rel))

def _first_body_image(rec):
    """First body image (any language) that is actually present on disk, or None.
    Used as a fallback card cover for articles with no dedicated cover image."""
    for lang in ("id", "en"):
        block = rec.get(lang) or {}
        for m in re.findall(r'<img[^>]+src="([^"]+)"', block.get("body", "") or ""):
            if m.startswith("/documents/") and _local_exists(m):
                return _served_cover_path(m)
    return None

def _card_cover(rec):
    """Effective cover for a listing card: the record's own cover IF its file is
    actually present in the mirror, else the first on-disk body image, else ''
    (caller renders a colored placeholder). Verifying the file exists prevents a
    broken <img> when a cover URL was recorded but never downloaded / 404s. The
    returned src is normalized to the served path (no trailing /<uuid> or ?query)."""
    cover = (rec.get("cover") or "").strip()
    if cover and _local_exists(cover):
        return _served_cover_path(cover)
    return _first_body_image(rec) or ""

# ─── Slug sanitization ────────────────────────────────────────────────────────

def sanitize_slug(slug):
    """Return a filesystem- and URL-safe version of a slug.

    Handles:
    - Slugs that accidentally include a full URL (https-//...)
    - Percent-encoded characters (%C3%B3 → o)
    - Path separators (/) → hyphens
    - Non-ASCII Unicode (normalise to ASCII equivalents)
    - Other non-alphanumeric characters → hyphens
    """
    # Strip full-URL prefix left by some Liferay exports
    if re.match(r'^https?', slug, re.IGNORECASE):
        slug = re.sub(r'^https?[-:]?//[^/]+/w/', '', slug, flags=re.IGNORECASE)
        slug = re.sub(r'/-/categories.*$', '', slug)
    # Decode percent-encoded sequences
    slug = unquote(slug)
    # Normalise Unicode to ASCII equivalents (é → e, ó → o, etc.)
    slug = unicodedata.normalize('NFKD', slug)
    slug = slug.encode('ascii', 'ignore').decode('ascii')
    # Replace path separators with hyphens
    slug = slug.replace('/', '-')
    # Replace any remaining non-slug characters with hyphens
    slug = re.sub(r'[^a-zA-Z0-9\-_]', '-', slug)
    # Collapse runs of hyphens and strip leading/trailing
    slug = re.sub(r'-{2,}', '-', slug).strip('-')
    # Truncate to a filesystem-safe length (240 chars leaves room for ".html")
    if len(slug) > 240:
        slug = slug[:240].rstrip('-')
    return slug


# ─── Warnings / stats ─────────────────────────────────────────────────────────

warnings = []


def warn(msg):
    warnings.append(msg)
    print(f"WARNING: {msg}", file=sys.stderr)


# ─── Chrome extraction ────────────────────────────────────────────────────────

def _extract_chrome(src_path, lang_code, listing_url, article_url_pattern=None):
    """Return (header_html, footer_html) extracted from a known-good mirror page.

    The header ends just before the main-content div; the footer begins at the
    footer structure-item div and continues through </body> (exclusive).

    lang_code:           e.g. "en-US" or "in-ID"
    listing_url:         URL used for the "Skip to Main Content" anchor href
    article_url_pattern: unused here; kept for possible future use
    """
    with open(src_path, encoding="utf-8") as fh:
        raw = fh.read()

    mc_pos = raw.find(MAIN_CONTENT_MARKER)
    if mc_pos < 0:
        raise RuntimeError(f"Cannot find main-content marker in {src_path}")

    footer_pos = raw.find(FOOTER_MARKER)
    if footer_pos < 0:
        raise RuntimeError(f"Cannot find footer marker in {src_path}")

    body_close = raw.rfind("</body>")
    if body_close < 0:
        raise RuntimeError(f"Cannot find </body> in {src_path}")

    header = raw[:mc_pos]
    footer = raw[footer_pos:body_close] + "\n</body>\n</html>\n"

    # Patch the lang attribute to the requested code
    header = re.sub(r'(<html[^>]*\blang=")[^"]*(")', r'\g<1>' + lang_code + r'\g<2>', header, count=1)

    return header, footer


# Cached chrome so we only read the source files once per run
_chrome_cache = {}


# The chrome header carries a Liferay language switcher whose <a> uses the dynamic
# /c/portal/update_language endpoint (404s on static hosting) with a redirect baked
# in from the chrome SOURCE page — wrong for every page that reuses that chrome.
# ALSO: the EN chrome (from an EN source page) renders this nav EMPTY (Liferay only
# emits the "switch to the OTHER language" link, which wasn't captured), so EN pages
# have NO pill at all — we must INJECT one.
# Match the WHOLE nav (open, inner, close). Scoping the has-anchor test to the inner
# is critical: a header-spanning [\s\S]*? would greedily cross the empty EN nav and
# match a downstream <a>, mis-detecting "has anchor" and skipping the injection.
_LANG_NAV_RE = re.compile(
    r'(<nav[^>]*vale-widget-seletor-pt-en[^>]*>)([\s\S]*?)(</nav>)'
)
_HAS_ANCHOR_RE = re.compile(r'<a\b[^>]*\bhref="[^"]*"')

def _fix_lang_toggle(header, target_url, pill_label="EN"):
    """Make the chrome language pill point to `target_url` (the static other-language
    version of THIS page). Repoint the nav's existing <a> if present; if the nav is
    EMPTY (EN chrome renders it empty), inject a pill labelled `pill_label`."""
    if not target_url or "vale-widget-seletor-pt-en" not in header:
        return header
    def repl(m):
        open_tag, inner, close = m.group(1), m.group(2), m.group(3)
        if _HAS_ANCHOR_RE.search(inner):
            inner = re.sub(r'(<a\b[^>]*\bhref=")[^"]*(")',
                           r'\g<1>' + target_url + r'\g<2>', inner, count=1)
        else:
            inner = (f'<a href="{target_url}" class="lang-sel-link lang-sel-btn '
                     f'font-weight-medium texto-sm" aria-label="{pill_label}">'
                     f'<span>{pill_label}</span></a>')
        return open_tag + inner + close
    return _LANG_NAV_RE.sub(repl, header, count=1)


def get_chrome(lang):
    """Return (header, footer) for lang="en" or lang="id"."""
    if lang in _chrome_cache:
        return _chrome_cache[lang]
    if lang == "en":
        h, f = _extract_chrome(EN_CHROME_SRC, "en-US", "/indonesia/all-news.html")
    elif lang == "id":
        h, f = _extract_chrome(ID_CHROME_SRC, "in-ID", "/in/indonesia/all-news.html")
    else:
        raise ValueError(f"Unknown lang: {lang}")
    _chrome_cache[lang] = (h, f)
    return h, f


# ─── Date formatting ──────────────────────────────────────────────────────────

def fmt_date(date_str, lang):
    """Format a YYYY-MM-DD string for display."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return date_str
    if lang == "id":
        months_id = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
        return f"{dt.day} {months_id[dt.month - 1]} {dt.year}"
    return dt.strftime("%B %-d, %Y")


# ─── Category filter JS ───────────────────────────────────────────────────────

CATEGORY_FILTER_JS = """
<script>
(function () {
  var btns = document.querySelectorAll('.news-filter-btn');
  var cards = document.querySelectorAll('.news-card[data-categories]');
  btns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var cat = btn.getAttribute('data-cat');
      btns.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      cards.forEach(function (card) {
        if (cat === 'all') {
          card.style.display = '';
        } else {
          var cats = card.getAttribute('data-categories').split('|');
          card.style.display = cats.indexOf(cat) >= 0 ? '' : 'none';
        }
      });
    });
  });
}());
</script>
"""

# ─── Scoped styles ────────────────────────────────────────────────────────────

LISTING_STYLES = """
<style>
.news-hero { position: relative; width: 100%; overflow: hidden; }
.news-hero-img { display: block; width: 100%; height: 30rem; object-fit: cover; }
@media (max-width: 767px) { .news-hero-img { height: 22rem; } }
.news-hero-scrim {
  position: absolute; inset: 0;
  background: linear-gradient(90deg, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.35) 50%, rgba(0,0,0,0.1) 100%);
}
.news-hero-inner {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; justify-content: flex-end;
}
.news-hero-inner .container { padding-bottom: 2.5rem; }
.news-hero-eyebrow {
  color: #fff; font-size: 0.9rem; font-weight: 500;
  letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.5rem;
  opacity: 0.9;
}
.news-hero-title {
  color: #fff; font-size: 3rem; font-weight: 700;
  line-height: 1.1; margin: 0; max-width: 40rem;
}
@media (max-width: 767px) { .news-hero-title { font-size: 2rem; } }
.news-listing-header { padding: 3rem 0 2rem; }
.news-listing-header h1 { font-size: 2rem; font-weight: 700; color: var(--verde-vale, #006633); }
.news-filter-bar { display: flex; flex-wrap: wrap; gap: 0.5rem; padding-top: 2.5rem; margin-bottom: 2rem; }
.news-filter-btn {
  display: inline-flex; align-items: center;
  padding: 0.4rem 1rem; border-radius: 1.5rem;
  border: 2px solid var(--verde-vale, #006633);
  background: #fff; color: var(--verde-vale, #006633);
  font-weight: 500; cursor: pointer; white-space: nowrap;
  text-decoration: none; font-size: 0.9rem;
}
.news-filter-btn.active,
.news-filter-btn:hover { background: var(--verde-vale, #006633); color: #fff; }
.news-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  padding-bottom: 3rem;
}
.news-card {
  border: 1px solid #e0e0e0; border-radius: 8px;
  overflow: hidden; background: #fff;
  display: flex; flex-direction: column;
}
.news-card-cover { width: 100%; height: 180px; object-fit: cover; background: #f5f5f5; }
.news-card-cover-placeholder { width: 100%; height: 180px; background: linear-gradient(135deg, #006633 0%, #00a64e 100%); }
.news-card-body { padding: 1rem; flex: 1; display: flex; flex-direction: column; }
.news-card-date { font-size: 0.8rem; color: #666; margin-bottom: 0.4rem; }
.news-card-title { font-weight: 700; font-size: 1rem; color: #222; margin-bottom: 0.5rem; line-height: 1.3; }
.news-card-subtitle { font-size: 0.875rem; color: #555; flex: 1; margin-bottom: 0.75rem; }
.news-card-cats { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.75rem; }
.news-card-cat { font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 1rem; background: #e8f5ee; color: #006633; }
.news-card-link {
  display: inline-block; margin-top: auto;
  padding: 0.4rem 1rem; border-radius: 1.5rem;
  background: var(--verde-vale, #006633); color: #fff;
  font-size: 0.85rem; text-decoration: none; font-weight: 500;
  align-self: flex-start;
}
.news-card-link:hover { background: #004d26; color: #fff; }
</style>
"""

ARTICLE_STYLES = """
<style>
/* Full-bleed hero banner (mirrors vale.com article pages + our listing hero). It
   pushes all article content BELOW the wavy chrome header so the decorative .wave
   SVG never overlaps the language switcher / title. */
.news-article-hero { position: relative; width: 100%; overflow: hidden; }
.news-article-hero-img { display: block; width: 100%; height: 22rem; object-fit: cover; }
@media (max-width: 767px) { .news-article-hero-img { height: 16rem; } }
.news-article-hero-scrim { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.35) 50%, rgba(0,0,0,0.1) 100%); }
.news-article-hero-inner { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: flex-end; }
.news-article-hero-inner .container { max-width: 860px; margin: 0 auto; padding: 0 1rem 2rem; width: 100%; }
.news-article-hero-eyebrow { color: #fff; font-size: 0.9rem; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 0.4rem; opacity: 0.9; }
.news-article-hero-title { color: #fff; font-size: 2.5rem; font-weight: 700; line-height: 1.1; margin: 0; }
@media (max-width: 767px) { .news-article-hero-title { font-size: 1.75rem; } }
.news-article-wrap { max-width: 860px; margin: 0 auto; padding: 2rem 1rem 4rem; }
.news-article-back { display: inline-flex; align-items: center; gap: 0.4rem; margin-bottom: 1.5rem; color: var(--verde-vale, #006633); text-decoration: none; font-weight: 500; }
.news-article-back:hover { text-decoration: underline; }
/* position:relative + z-index lifts the switcher above the decorative .wave SVG
   (z-index:0, position-absolute, ~20rem wide, top-left) whose box otherwise
   overlaps and swallows clicks/hover on the left-most button (the "English"
   button on ID pages). The chrome's own CSS only sets pointer-events:none on
   .images-wave-image, NOT on .wave — so we raise our switcher instead. */
.news-article-lang-switcher { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; position: relative; z-index: 1; }
.lang-sel-btn {
  display: inline-flex; align-items: center; padding: 0.4rem 1rem;
  border-radius: 1.5rem; border: 2px solid var(--verde-vale, #006633);
  background: #fff; color: var(--verde-vale, #006633);
  font-weight: 500; cursor: pointer; white-space: nowrap; text-decoration: none; font-size: 0.9rem;
}
.lang-sel-btn.active, .lang-sel-btn:hover { background: var(--verde-vale, #006633); color: #fff; }
.news-article-title { font-size: 1.75rem; font-weight: 700; color: #222; margin-bottom: 0.5rem; line-height: 1.25; }
.news-article-date { font-size: 0.9rem; color: #666; margin-bottom: 0.75rem; }
.news-article-subtitle { font-size: 1.1rem; color: #444; margin-bottom: 1.25rem; font-style: italic; }
.news-article-cover { width: 100%; max-height: 400px; object-fit: cover; border-radius: 6px; margin-bottom: 1.5rem; }
.news-article-body { font-size: 1rem; line-height: 1.7; color: #333; }
.news-article-body img { max-width: 100%; height: auto; border-radius: 4px; margin: 1rem 0; }
.news-article-body p { margin-bottom: 1rem; }
.news-article-body h2, .news-article-body h3 { margin: 1.5rem 0 0.75rem; }
</style>
"""


# ─── Page builders ────────────────────────────────────────────────────────────

def build_listing_page(records, lang, all_categories, dry_run=False):
    """Generate the all-news listing page for one language."""
    header, footer = get_chrome(lang)

    # Patch the <title> to "News — Vale Indonesia"
    if lang == "en":
        page_title = "News — PT Vale Indonesia Tbk"
        heading = "News"
        read_more = "Read more"
        listing_url = "/indonesia/all-news.html"
        article_url_prefix = "/indonesia/w/"
        all_label = "All"
        back_url = listing_url
    else:
        page_title = "Berita — PT Vale Indonesia Tbk"
        heading = "Berita"
        read_more = "Selengkapnya"
        listing_url = "/in/indonesia/all-news.html"
        article_url_prefix = "/in/indonesia/w/"
        all_label = "Semua"
        back_url = listing_url

    header = re.sub(r'(<title>)[^<]*(</title>)', r'\g<1>' + page_title + r'\g<2>', header, count=1)

    # Repoint the chrome language pill to the OTHER-language listing (this page's
    # counterpart), replacing the dynamic update_language 404 link.
    other_listing = "/in/indonesia/all-news.html" if lang == "en" else "/indonesia/all-news.html"
    header = _fix_lang_toggle(header, other_listing, "ID" if lang == "en" else "EN")

    # Build filter buttons
    filter_btns = [f'<button class="news-filter-btn active" data-cat="all">{all_label}</button>']
    for cat in sorted(all_categories):
        safe = html_mod.escape(cat)
        filter_btns.append(f'<button class="news-filter-btn" data-cat="{safe}">{safe}</button>')

    # Build news cards
    cards_html = []
    for rec in records:
        lang_block = rec.get(lang)
        if not lang_block:
            continue
        slug = rec["slug"]
        date_display = fmt_date(rec["date"], lang)
        title = html_mod.escape(lang_block.get("title", ""))
        subtitle_raw = lang_block.get("subtitle", "")
        # truncate subtitle for card
        subtitle = html_mod.escape(subtitle_raw[:160] + ("…" if len(subtitle_raw) > 160 else ""))
        cover = _card_cover(rec)
        cats = rec.get("categories", [])
        cats_attr = html_mod.escape("|".join(cats))
        article_url = f"{article_url_prefix}{slug}.html"

        if cover:
            cover_html = f'<img class="news-card-cover" src="{html_mod.escape(cover)}" alt="{title}" loading="lazy">'
        else:
            cover_html = '<div class="news-card-cover-placeholder"></div>'

        cat_badges = "".join(
            f'<span class="news-card-cat">{html_mod.escape(c)}</span>' for c in cats
        )

        cards_html.append(f"""\
<div class="news-card" data-categories="{cats_attr}">
  {cover_html}
  <div class="news-card-body">
    <div class="news-card-date">{html_mod.escape(date_display)}</div>
    <div class="news-card-title">{title}</div>
    <div class="news-card-subtitle">{subtitle}</div>
    <div class="news-card-cats">{cat_badges}</div>
    <a class="news-card-link" href="{article_url}">{read_more}</a>
  </div>
</div>""")

    main_content = f"""\
<div class="layout-content portlet-layout" id="main-content" role="main">
{LISTING_STYLES}
<div class="news-hero">
  <img class="news-hero-img" src="/documents/44618/9161766/news-header-mining.jpg" alt="{html_mod.escape(heading)}">
  <div class="news-hero-scrim"></div>
  <div class="news-hero-inner">
    <div class="container">
      <div class="news-hero-eyebrow">PT Vale Indonesia</div>
      <h1 class="news-hero-title">{html_mod.escape(heading)}</h1>
    </div>
  </div>
</div>
<div class="container">
  <div class="news-filter-bar">
    {"".join(filter_btns)}
  </div>
  <div class="news-cards-grid">
    {"".join(cards_html)}
  </div>
</div>
{CATEGORY_FILTER_JS}
</div>
"""

    return header + main_content + footer


def build_article_page(rec, lang, dry_run=False):
    """Generate one article page for the given record and language."""
    lang_block = rec.get(lang)
    if not lang_block:
        return None

    other_lang = "id" if lang == "en" else "en"
    has_other = bool(rec.get(other_lang))

    header, footer = get_chrome(lang)

    title = lang_block.get("title", "")
    subtitle = lang_block.get("subtitle", "")
    body = lang_block.get("body", "")
    date_display = fmt_date(rec["date"], lang)
    cover = rec.get("cover", "")
    slug = rec["slug"]

    if lang == "en":
        back_url = "/indonesia/all-news.html"
        back_label = "← Back to News"
        self_url = f"/indonesia/w/{slug}.html"
        other_url = f"/in/indonesia/w/{slug}.html"
        en_label = "English"
        id_label = "Indonesia"
    else:
        back_url = "/in/indonesia/all-news.html"
        back_label = "← Kembali ke Berita"
        self_url = f"/in/indonesia/w/{slug}.html"
        other_url = f"/indonesia/w/{slug}.html"
        en_label = "English"
        id_label = "Indonesia"

    # Patch title
    safe_title = html_mod.escape(title)
    header = re.sub(
        r'(<title>)[^<]*(</title>)',
        r'\g<1>' + safe_title + r' — PT Vale Indonesia Tbk\g<2>',
        header, count=1
    )

    # Repoint the chrome language pill to THIS article's other-language version
    # (only when it exists), replacing the dynamic update_language 404 link.
    if has_other:
        header = _fix_lang_toggle(header, other_url, "ID" if lang == "en" else "EN")

    # Language switcher
    if lang == "en":
        switcher = (
            f'<a class="lang-sel-btn active" href="{self_url}">{en_label}</a>'
        )
        if has_other:
            switcher += f'\n    <a class="lang-sel-btn" href="{other_url}">{id_label}</a>'
    else:
        if has_other:
            switcher = f'<a class="lang-sel-btn" href="{other_url}">{en_label}</a>\n    '
        else:
            switcher = ""
        switcher += f'<a class="lang-sel-btn active" href="{self_url}">{id_label}</a>'

    # Detect whether the body LEADS with an image (its first content element is an
    # <img>, allowing a wrapping <p>). When it does, the body already opens with a
    # photo, so also rendering the cover header stacks two images back-to-back — the
    # cover and the body's lead shot are almost always the same event (often the same
    # photo in a different crop / URL form / variant suffix), which reads as a doubled
    # image. In that case we skip the cover header and let the body image be the lead.
    body_leads_with_img = bool(
        re.match(r'\s*(?:<p[^>]*>\s*)?<img\b', body or "", re.IGNORECASE)
    )

    cover_html = ""
    # Only render the cover header if the cover file is actually present in the mirror
    # (a recorded-but-missing cover would render a broken image), and skip it when the
    # body already opens with an image (same photo would otherwise show twice).
    if cover and _local_exists(cover):
        if body_leads_with_img:
            pass  # body opens with a photo — skip the duplicate cover header
        else:
            # Emit the normalized served path (no trailing /<uuid> or ?query), else
            # the <img> would 404 against the on-disk file name.
            cover_src = _served_cover_path(cover)
            cover_html = f'<img class="news-article-cover" src="{html_mod.escape(cover_src)}" alt="{safe_title}">'

    hero_heading = "News" if lang == "en" else "Berita"
    # Hero image matches vale.com's News ARTICLE header (train-through-hills),
    # which differs from the News LISTING hero (field workers). Desktop + mobile
    # variants, same as the source page.
    hero = f"""\
<section class="news-article-hero">
  <img class="news-article-hero-img d-none d-md-block" src="/documents/d/guest/banner-teste12-1" alt="{hero_heading}">
  <img class="news-article-hero-img d-md-none" src="/documents/d/guest/banner-mobile-final" alt="{hero_heading}">
  <div class="news-article-hero-scrim"></div>
  <div class="news-article-hero-inner">
    <div class="container">
      <div class="news-article-hero-eyebrow">PT Vale Indonesia</div>
      <h2 class="news-article-hero-title">{hero_heading}</h2>
    </div>
  </div>
</section>"""

    main_content = f"""\
<div class="layout-content portlet-layout" id="main-content" role="main">
{ARTICLE_STYLES}
{hero}
<div class="news-article-wrap">
  <a class="news-article-back" href="{back_url}">{back_label}</a>
  <div class="news-article-lang-switcher">
    {switcher}
  </div>
  <h1 class="news-article-title">{safe_title}</h1>
  <div class="news-article-date">{html_mod.escape(date_display)}</div>
  {"" if not subtitle else f'<div class="news-article-subtitle">{html_mod.escape(subtitle)}</div>'}
  {cover_html}
  <div class="news-article-body">
    {body}
  </div>
</div>
</div>
"""

    return header + main_content + footer


# ─── /w/ link rewrite ─────────────────────────────────────────────────────────

# Matches href="/w/<slug>/-/categories/<anything>" or href="/w/<slug>/-/categories/"
W_LINK_RE = re.compile(r'href="/w/([^/"]+)/-/categories(/[^"]*)?(?=#|")', re.IGNORECASE)


def rewrite_w_links(site_root, known_slugs):
    """Rewrite /w/<slug>/-/categories/N links in all site HTML files.

    Only rewrites links whose slug is in known_slugs (generated pages).
    Reports links whose slug is NOT in known_slugs without touching them.
    Returns (rewritten_count, reported_unknown) tuple.
    """
    rewritten = 0
    unknown_links = {}  # slug → set of files

    html_files = []
    for dirpath, _dirnames, filenames in os.walk(site_root):
        for fname in filenames:
            if fname.endswith(".html"):
                html_files.append(os.path.join(dirpath, fname))

    def replacer(m):
        nonlocal rewritten
        slug = m.group(1)
        # Clean slug from any trailing junk that isn't part of the slug
        if slug in known_slugs:
            rewritten += 1
            return f'href="/indonesia/w/{slug}.html"'
        # Not our slug - record it but leave intact
        return m.group(0)

    for fpath in html_files:
        try:
            with open(fpath, encoding="utf-8") as fh:
                original = fh.read()
        except (OSError, UnicodeDecodeError):
            continue

        # First pass: collect unknown slugs from this file
        for m in W_LINK_RE.finditer(original):
            slug = m.group(1)
            if slug not in known_slugs:
                unknown_links.setdefault(slug, set()).add(
                    os.path.relpath(fpath, site_root)
                )

        new_content, n = W_LINK_RE.subn(replacer, original)
        if n > 0 and new_content != original:
            with open(fpath, "w", encoding="utf-8") as fh:
                fh.write(new_content)

    return rewritten, unknown_links


# ─── Orphan detection ─────────────────────────────────────────────────────────

def find_orphans(article_dir, known_slugs):
    """Return list of .html files in article_dir whose slug is not in known_slugs."""
    orphans = []
    if not os.path.isdir(article_dir):
        return orphans
    for fname in os.listdir(article_dir):
        if not fname.endswith(".html"):
            continue
        slug = fname[:-5]  # strip .html
        if slug not in known_slugs:
            orphans.append(os.path.join(article_dir, fname))
    return orphans


# ─── Broken-link scan (extensionless-aware) ───────────────────────────────────

def scan_broken_w_links(generated_files, site_root, known_slugs):
    """Scan generated pages for /w/ links that don't resolve to a file on disk.

    Extensionless-aware: for a link like /indonesia/w/slug we check both
    site/vale.com/indonesia/w/slug and site/vale.com/indonesia/w/slug.html.
    Returns list of (file, href) pairs that are broken.
    """
    broken = []
    href_re = re.compile(r'href="(/[^"#?]*)"')

    for fpath in generated_files:
        try:
            with open(fpath, encoding="utf-8") as fh:
                content = fh.read()
        except OSError:
            continue
        for m in href_re.finditer(content):
            href = m.group(1)
            if "/w/" not in href:
                continue
            # Map href to disk path
            disk_path = os.path.join(site_root, href.lstrip("/"))
            disk_path_html = disk_path if disk_path.endswith(".html") else disk_path + ".html"
            if not os.path.exists(disk_path) and not os.path.exists(disk_path_html):
                broken.append((os.path.relpath(fpath, site_root), href))

    return broken


# ─── Main ─────────────────────────────────────────────────────────────────────

def _home_slide_html(rec, lang):
    """One <div class="swiper-slide"> using the site's own card markup
    (vale-modelo-card-com-mais), pointing at our static article page."""
    block = rec.get(lang) or {}
    title = html_mod.escape(block.get("title", ""))
    subtitle_raw = block.get("subtitle", "") or ""
    subtitle = html_mod.escape(subtitle_raw[:130] + ("…" if len(subtitle_raw) > 130 else ""))
    slug = rec["slug"]
    if lang == "en":
        url = f"/indonesia/w/{slug}.html"
    else:
        url = f"/in/indonesia/w/{slug}.html"
    img = _card_cover(rec)  # cover, else first body image, else '' (reuse listing logic)
    if img:
        img_html = (f'<img width="300" height="300" class="card-img d-block" '
                    f'src="{html_mod.escape(img)}" alt="{title}" loading="lazy">')
    else:
        img_html = '<div class="card-img d-block news-card-cover-placeholder" style="height:300px"></div>'
    return (
        '<div class="swiper-slide">'
        f'<a class="vale-modelo-card-com-mais" href="{url}">'
        f'<div class="overflow-hidden">{img_html}</div>'
        '<div class="card-text px-4 pt-5 bg-white bg-white">'
        f'<p class="h4 text-verde-vale mb-3">{title}</p>'
        f'<p class="text-cinza-escuro">{subtitle}</p>'
        '<span class="card-link position-absolute">&nbsp;</span>'
        '</div>'
        '<svg class="card-cut mw-100 w-100 h-auto" xmlns="http://www.w3.org/2000/svg" '
        'width="360.998" height="91.795" viewBox="0 0 360.998 91.795">'
        '<path d="M18240,24500.742v-90.795h151.865v.426H18600v24.373c-4.918,0-10.262.08-15.82,0-69.656-.982-103.1,65.8-192.312,65.994v0Z" '
        'transform="translate(-18239.498 -24409.447)" fill="#fff" stroke="rgba(0,0,0,0)" stroke-width="1"/>'
        '</svg>'
        '</a></div>'
    )


def inject_home_highlight(records, lang, home_path):
    """Pre-render the top-N newest Indonesia-focused articles into the homepage
    carousel's empty .swiper-wrapper. Idempotent: replaces a previously injected
    block (delimited by sentinel comments). Returns True if the file was updated."""
    if not os.path.isfile(home_path):
        warn(f"Homepage not found, skipped highlight: {os.path.relpath(home_path, SCRIPT_DIR)}")
        return False

    # Prefer Indonesia-tagged, newest-first; top up with the rest if fewer than N.
    lang_recs = [r for r in records if r.get(lang)]
    indo = [r for r in lang_recs if INDONESIA_CATS.intersection(r.get("categories", []))]
    chosen = indo[:HOME_HIGHLIGHT_COUNT]
    if len(chosen) < HOME_HIGHLIGHT_COUNT:
        seen = {r["slug"] for r in chosen}
        for r in lang_recs:
            if r["slug"] not in seen:
                chosen.append(r)
                if len(chosen) >= HOME_HIGHLIGHT_COUNT:
                    break

    slides = "".join(_home_slide_html(r, lang) for r in chosen)

    # The site's Swiper is normally initialized inside the (now-dead) Liferay API fetch
    # callback, so on the static mirror it never runs and the carousel can't scroll.
    # Initialize Swiper ourselves on the same container/config once the lib is loaded.
    init_script = (
        '<script>(function(){'
        'function initValeNewsSwiper(){'
        'var el=document.querySelector(".swiper-carrosel-lnko");'
        'if(!el){return;}'
        'if(typeof Swiper==="undefined"){return setTimeout(initValeNewsSwiper,120);}'
        'if(el.classList.contains("swiper-initialized")){return;}'
        'new Swiper(".swiper-carrosel-lnko",{'
        'slidesPerView:1,spaceBetween:10,'
        'navigation:{nextEl:".btn-next-lnko",prevEl:".btn-prev-lnko",'
        'disabledClass:"disabled",navigationDisabledClass:"disabled"},'
        'pagination:{el:".swiper-pagination-lnko",clickable:true},'
        'breakpoints:{640:{slidesPerView:2.1,spaceBetween:20},'
        '768:{slidesPerView:3.3,spaceBetween:32}}'
        '});'
        '}'
        'if(document.readyState!=="loading"){initValeNewsSwiper();}'
        'else{document.addEventListener("DOMContentLoaded",initValeNewsSwiper);}'
        '})();</script>'
    )
    # Slides go INSIDE the .swiper-wrapper; the init <script> goes AFTER the wrapper
    # closes (a <script> among .swiper-wrapper's direct children would be treated as a
    # slide by Swiper). Both are wrapped in sentinels so re-runs replace cleanly.
    slides_block = f"{HOME_INJECT_START}{slides}{HOME_INJECT_END}"
    script_block = f"{HOME_INJECT_START}{init_script}{HOME_INJECT_END}"

    html = open(home_path, encoding="utf-8", errors="replace").read()

    # Remove any previously injected blocks first (idempotence) — there may be two.
    html = re.sub(
        re.escape(HOME_INJECT_START) + r".*?" + re.escape(HOME_INJECT_END),
        "",
        html,
        flags=re.DOTALL,
    )

    # Find the carousel's empty wrapper.
    car = html.find(HOME_WRAPPER_OPEN)
    if car == -1:
        warn(f"No carousel found on homepage, skipped: {os.path.relpath(home_path, SCRIPT_DIR)}")
        return False
    w_open = html.find(HOME_WRAPPER_INNER_OPEN, car)
    if w_open == -1:
        warn(f"No swiper-wrapper found on homepage, skipped: {os.path.relpath(home_path, SCRIPT_DIR)}")
        return False
    # Locate the matching closing </div> of the wrapper (it starts empty as
    # '<div class="swiper-wrapper"> </div>', so the next </div> closes it).
    inner_start = w_open + len(HOME_WRAPPER_INNER_OPEN)
    close_idx = html.find("</div>", inner_start)
    if close_idx == -1:
        warn(f"Malformed swiper-wrapper on homepage, skipped: {os.path.relpath(home_path, SCRIPT_DIR)}")
        return False
    wrapper_end = close_idx + len("</div>")

    # Insert slides inside the wrapper, then the init script right after it closes.
    new_html = (
        html[:inner_start]
        + slides_block
        + html[inner_start:wrapper_end]
        + script_block
        + html[wrapper_end:]
    )

    with open(home_path, "w", encoding="utf-8") as fh:
        fh.write(new_html)
    return True


def main():
    dry_run = "--dry-run" in sys.argv

    # ── 1. Load and validate JSON ──────────────────────────────────────────────
    try:
        with open(DATA_FILE, encoding="utf-8") as fh:
            raw_text = fh.read()
        records_raw = json.loads(raw_text)
    except FileNotFoundError:
        print(f"ERROR: Data file not found: {DATA_FILE}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Invalid JSON in {DATA_FILE}: {exc.msg} "
            f"at line {exc.lineno} col {exc.colno}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(records_raw, list):
        print(f"ERROR: {DATA_FILE} must contain a JSON array at the top level.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Validate records and collect valid ones ─────────────────────────────
    seen_slugs = {}  # sanitized_slug → original index (for dup detection)
    records = []
    all_categories = set()

    for i, rec in enumerate(records_raw):
        raw_slug = rec.get("slug", "").strip()
        date = rec.get("date", "").strip()

        if not raw_slug:
            warn(f"Record #{i+1}: missing slug — skipped")
            continue

        slug = sanitize_slug(raw_slug)
        if not slug:
            warn(f"Record #{i+1}: slug {raw_slug!r} becomes empty after sanitization — skipped")
            continue

        # Attach the sanitized slug back to the record dict so downstream code
        # can use rec["slug"] consistently.
        rec = dict(rec)  # shallow copy to avoid mutating the loaded JSON
        if raw_slug != slug:
            warn(f"Record #{i+1}: slug sanitized from {raw_slug!r} to {slug!r}")
        rec["slug"] = slug

        # Check for missing date
        if not date:
            warn(f"Record slug={slug!r}: missing date — skipped")
            continue

        # Check for missing title in both languages
        en_title = (rec.get("en") or {}).get("title", "").strip()
        id_title = (rec.get("id") or {}).get("title", "").strip()
        if not en_title and not id_title:
            warn(f"Record slug={slug!r}: missing title in both languages — skipped")
            continue

        # Duplicate slug detection (after sanitization)
        if slug in seen_slugs:
            warn(f"Duplicate slug {slug!r} (first at #{seen_slugs[slug]+1}, now #{i+1}) — last wins")

        seen_slugs[slug] = i

        for cat in rec.get("categories", []):
            all_categories.add(cat)

        records.append(rec)

    # Re-deduplicate keeping last occurrence per sanitized slug
    deduped = {}
    for rec in records:
        deduped[rec["slug"]] = rec
    records = list(deduped.values())

    # Sort newest first
    records.sort(key=lambda r: r.get("date", ""), reverse=True)

    known_slugs = {r["slug"] for r in records}
    en_records = [r for r in records if r.get("en")]
    id_records = [r for r in records if r.get("id")]

    print(f"Loaded {len(records)} valid records "
          f"({len(en_records)} EN, {len(id_records)} ID)")

    if dry_run:
        print("[dry-run] No files written.")
        return

    # ── 3. Create output directories ───────────────────────────────────────────
    os.makedirs(EN_ARTICLE_DIR, exist_ok=True)
    os.makedirs(ID_ARTICLE_DIR, exist_ok=True)

    generated_files = []

    # ── 4. Generate listing pages ──────────────────────────────────────────────
    en_listing = build_listing_page(records, "en", all_categories)
    with open(EN_LISTING_PATH, "w", encoding="utf-8") as fh:
        fh.write(en_listing)
    generated_files.append(EN_LISTING_PATH)
    print(f"Wrote EN listing → {os.path.relpath(EN_LISTING_PATH, SCRIPT_DIR)}")

    id_listing = build_listing_page(records, "id", all_categories)
    with open(ID_LISTING_PATH, "w", encoding="utf-8") as fh:
        fh.write(id_listing)
    generated_files.append(ID_LISTING_PATH)
    print(f"Wrote ID listing → {os.path.relpath(ID_LISTING_PATH, SCRIPT_DIR)}")

    # ── 4b. Inject homepage "latest news" highlight (top-N, Indonesia-focused) ──
    if inject_home_highlight(records, "en", EN_HOME_PATH):
        generated_files.append(EN_HOME_PATH)
        print(f"Injected homepage highlight → {os.path.relpath(EN_HOME_PATH, SCRIPT_DIR)}")
    if inject_home_highlight(records, "id", ID_HOME_PATH):
        generated_files.append(ID_HOME_PATH)
        print(f"Injected homepage highlight → {os.path.relpath(ID_HOME_PATH, SCRIPT_DIR)}")

    # ── 5. Generate article pages ──────────────────────────────────────────────
    en_written = 0
    id_written = 0

    for rec in records:
        slug = rec["slug"]

        # EN article
        en_page = build_article_page(rec, "en")
        if en_page is not None:
            out = os.path.join(EN_ARTICLE_DIR, f"{slug}.html")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(en_page)
            generated_files.append(out)
            en_written += 1

        # ID article
        id_page = build_article_page(rec, "id")
        if id_page is not None:
            out = os.path.join(ID_ARTICLE_DIR, f"{slug}.html")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(id_page)
            generated_files.append(out)
            id_written += 1

    print(f"Wrote {en_written} EN article pages → site/vale.com/indonesia/w/")
    print(f"Wrote {id_written} ID article pages → site/vale.com/in/indonesia/w/")

    # ── 6. Orphan detection ────────────────────────────────────────────────────
    for art_dir, label in [(EN_ARTICLE_DIR, "EN"), (ID_ARTICLE_DIR, "ID")]:
        orphans = find_orphans(art_dir, known_slugs)
        for orphan in orphans:
            warn(f"Orphan {label} article (slug no longer in data): {orphan}")

    # ── 7. /w/ link rewrite pass ───────────────────────────────────────────────
    print("Running /w/ link rewrite pass…")
    rewritten, unknown_links = rewrite_w_links(SITE_ROOT, known_slugs)
    print(f"Rewrote {rewritten} /w/ links across the mirror.")

    if unknown_links:
        for slug, files in sorted(unknown_links.items()):
            warn(
                f"/w/ link slug not in data (left untouched): {slug!r} "
                f"in {', '.join(sorted(files))}"
            )

    # ── 8. Broken-link scan ────────────────────────────────────────────────────
    broken = scan_broken_w_links(generated_files, SITE_ROOT, known_slugs)
    if broken:
        for frel, href in broken:
            warn(f"Broken /w/ link in generated page: {frel} → {href}")

    # ── 9. Summary ────────────────────────────────────────────────────────────
    total_generated = len(generated_files)
    print(f"\nBuild complete: {total_generated} files generated "
          f"(2 listings + {en_written} EN + {id_written} ID articles)")

    if warnings:
        print(f"\n{len(warnings)} warning(s):")
        for w in warnings:
            print(f"  ⚠  {w}")
    else:
        print("No warnings.")

    sys.exit(0)


if __name__ == "__main__":
    main()
