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
DATA_FILE = os.path.join(SCRIPT_DIR, "site-data", "news.json")
SITE_ROOT = os.path.join(SCRIPT_DIR, "site", "vale.com")

# Chrome source pages (known-good mirror pages to extract header/footer from)
EN_CHROME_SRC = os.path.join(SITE_ROOT, "indonesia", "about-pt-vale-indonesia.html")
ID_CHROME_SRC = os.path.join(SITE_ROOT, "in", "indonesia", "esg.html")

# Output directories
EN_LISTING_PATH = os.path.join(SITE_ROOT, "indonesia", "all-news.html")
ID_LISTING_PATH = os.path.join(SITE_ROOT, "in", "indonesia", "all-news.html")
EN_ARTICLE_DIR = os.path.join(SITE_ROOT, "indonesia", "w")
ID_ARTICLE_DIR = os.path.join(SITE_ROOT, "in", "indonesia", "w")

# Marker strings used to split chrome source into header + footer
MAIN_CONTENT_MARKER = '<div class="layout-content portlet-layout"id="main-content"'
FOOTER_MARKER = '<div class="lfr-layout-structure-item-footer--copiar-'

# Default cover image used when a record has no cover set
DEFAULT_COVER = "/o/vale-theme/images/default-news-cover.png"

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
.news-listing-header { padding: 3rem 0 2rem; }
.news-listing-header h1 { font-size: 2rem; font-weight: 700; color: var(--verde-vale, #006633); }
.news-filter-bar { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 2rem; }
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
.news-article-wrap { max-width: 860px; margin: 0 auto; padding: 2rem 1rem 4rem; }
.news-article-back { display: inline-flex; align-items: center; gap: 0.4rem; margin-bottom: 1.5rem; color: var(--verde-vale, #006633); text-decoration: none; font-weight: 500; }
.news-article-back:hover { text-decoration: underline; }
.news-article-lang-switcher { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
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
        cover = rec.get("cover", "")
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
<div class="container news-listing-header">
  <h1>{html_mod.escape(heading)}</h1>
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

    cover_html = ""
    if cover:
        cover_html = f'<img class="news-article-cover" src="{html_mod.escape(cover)}" alt="{safe_title}">'

    main_content = f"""\
<div class="layout-content portlet-layout" id="main-content" role="main">
{ARTICLE_STYLES}
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
