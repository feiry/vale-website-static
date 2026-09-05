#!/usr/bin/env python3
"""build-doc-library.py — Static Document Library page generator for the Vale
Indonesia mirror. Sibling of build-news.py; reuses the same chrome-extraction
approach (split a known-good mirror page into header + footer).

Reads site-data/documents.json (252 records, produced by export-doc-library.py) and
regenerates the two Document Library pages IN PLACE:
  site/vale.com/indonesia/documents-and-reports.html      (EN)
  site/vale.com/in/indonesia/dokumen-dan-laporan.html     (ID)

Layout (approved 2026-07-20):
  - Filter chips at top: All / Annual Reports / Sustainability / Financial /
    Presentation / Press Releases. Chips show/hide whole sections. No-JS fallback:
    every section visible.
  - Each section = a titled block of download cards (title + date + size + PDF link),
    newest-first by date.
  - Press Releases & Announcements combines EN+BH; each card is tagged [EN]/[BH] and
    gets a sub-filter (All / English / Bahasa) scoped to that section.

Both language pages show ALL sections and ALL documents (faithful to the live page,
which serves the same library on both /indonesia/documents-and-reports and the ID URL).
Only the chrome, headings, and filter labels differ per language.

Usage:
  python3 build-doc-library.py            # normal build
  python3 build-doc-library.py --dry-run  # print stats, write nothing

Guardrails:
  - Invalid JSON            → abort with line/column message
  - Missing title/link      → skip record with warning naming the id
  - Missing file on disk     → warning (card still rendered; link may 404 until deployed)

Fully idempotent: running twice produces identical output.
"""

import json
import os
import re
import sys
import html as html_mod
from datetime import datetime

# ─── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "site-data", "documents.json")
SITE_ROOT = os.path.join(SCRIPT_DIR, "site", "vale.com")

# Chrome source pages (same known-good mirror pages build-news.py uses)
EN_CHROME_SRC = os.path.join(SITE_ROOT, "indonesia", "about-pt-vale-indonesia.html")
ID_CHROME_SRC = os.path.join(SITE_ROOT, "in", "indonesia", "esg.html")

# Output pages (the existing empty Liferay shells, overwritten in place)
EN_PAGE_PATH = os.path.join(SITE_ROOT, "indonesia", "documents-and-reports.html")
ID_PAGE_PATH = os.path.join(SITE_ROOT, "in", "indonesia", "dokumen-dan-laporan.html")

# Marker strings used to split chrome source into header + footer (same as build-news)
MAIN_CONTENT_MARKER = '<div class="layout-content portlet-layout"id="main-content"'
FOOTER_MARKER = '<div class="lfr-layout-structure-item-footer--copiar-'

# Section display order (top → bottom on the page). Keyed by the exact `section`
# string in documents.json. Press Releases last (it's the biggest, bilingual one).
SECTION_ORDER = [
    "Annual Reports",
    "Sustainability Reports",
    "Financial Statements",
    "Presentation",
    "Press Releases & Announcements",
]

# Short, filter-chip-friendly labels + a url-safe key per section.
SECTION_META = {
    "Annual Reports":                 {"key": "annual",   "chip_en": "Annual Reports",   "chip_id": "Laporan Tahunan"},
    "Sustainability Reports":         {"key": "sustain",  "chip_en": "Sustainability",   "chip_id": "Keberlanjutan"},
    "Financial Statements":           {"key": "financial","chip_en": "Financial",        "chip_id": "Laporan Keuangan"},
    "Presentation":                   {"key": "present",  "chip_en": "Presentation",     "chip_id": "Presentasi"},
    "Press Releases & Announcements": {"key": "press",    "chip_en": "Press Releases",   "chip_id": "Siaran Pers"},
}

PRESS_SECTION = "Press Releases & Announcements"

warnings = []


def warn(msg):
    warnings.append(msg)
    print(f"WARNING: {msg}", file=sys.stderr)


# ─── Chrome extraction (same technique as build-news.py) ──────────────────────

def _extract_chrome(src_path, lang_code):
    with open(src_path, encoding="utf-8") as fh:
        raw = fh.read()
    mc_pos = raw.find(MAIN_CONTENT_MARKER)
    if mc_pos < 0:
        # Re-cloned chrome sources render `portlet-layout" id="main-content"` (space
        # before id=) vs the literal marker's no-space form. Tolerate both.
        m = re.search(r'<div class="layout-content portlet-layout"\s*id="main-content"', raw)
        if m:
            mc_pos = m.start()
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
    header = re.sub(r'(<html[^>]*\blang=")[^"]*(")', r'\g<1>' + lang_code + r'\g<2>', header, count=1)
    return header, footer


_chrome_cache = {}


def get_chrome(lang):
    if lang in _chrome_cache:
        return _chrome_cache[lang]
    if lang == "en":
        hf = _extract_chrome(EN_CHROME_SRC, "en-US")
    elif lang == "id":
        hf = _extract_chrome(ID_CHROME_SRC, "in-ID")
    else:
        raise ValueError(f"Unknown lang: {lang}")
    _chrome_cache[lang] = hf
    return hf


# ─── Helpers ──────────────────────────────────────────────────────────────────

_MONTHS = {
    "january": 1, "februari": 2, "february": 2, "march": 3, "maret": 3, "april": 4,
    "may": 5, "mei": 5, "june": 6, "juni": 6, "july": 7, "juli": 7, "august": 8,
    "agustus": 8, "september": 9, "october": 10, "oktober": 10, "november": 11,
    "december": 12, "desember": 12,
}
_ID_MONTH_NAMES = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                   "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
_EN_MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]


def parse_title_date(title):
    """Extract the content period from a document title.

    The Liferay clone/publish dates are mostly bulk-upload artifacts (e.g. 88 press
    releases all dated "24 Februari 2026"), so the real chronology lives in the title
    (report year, quarter, or an explicit date). Returns (year, quarter, month, day)
    with quarter/month/day = None when absent, or None if no year could be found.
    """
    if not title:
        return None
    t = title
    tl = t.lower()
    y = q = m = d = None
    # Quarter forms: 1Q22, 2Q26, 1q26, Q1 2024
    mq = re.search(r"\b([1-4])q\s*([0-9]{2,4})\b", tl) or re.search(r"\bq([1-4])\s*([0-9]{4})\b", tl)
    if mq:
        q = int(mq.group(1))
        yy = mq.group(2)
        y = int(yy) if len(yy) == 4 else 2000 + int(yy)
    # ISO date: 2025-10-29 or 2025-12
    md_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t) or re.search(r"\b(\d{4})-(\d{2})\b", t)
    if md_iso:
        g = md_iso.groups()
        y = int(g[0]); m = int(g[1])
        if len(g) > 2 and g[2]:
            d = int(g[2])
    # "31 March 2026" / "31 December 2024"
    md_dmy = re.search(r"\b(\d{1,2})\s+([a-z]+)\s+(\d{4})\b", tl)
    if md_dmy and md_dmy.group(2) in _MONTHS:
        d = int(md_dmy.group(1)); m = _MONTHS[md_dmy.group(2)]; y = int(md_dmy.group(3))
    # "December 2024"
    md_my = re.search(r"\b([a-z]+)\s+(\d{4})\b", tl)
    if y is None and md_my and md_my.group(1) in _MONTHS:
        m = _MONTHS[md_my.group(1)]; y = int(md_my.group(2))
    # Cumulative-month filing form: 3M23 / 6M23 / 9M23 / 12M23 (months-elapsed + 2-digit year)
    md_nm = re.search(r"\b(3|6|9|12)m(\d{2})\b", tl)
    if y is None and md_nm:
        m = int(md_nm.group(1)); y = 2000 + int(md_nm.group(2))
    # Plain 4-digit year (annual / sustainability reports) — take the last one mentioned
    if y is None:
        yrs = re.findall(r"\b(19[6-9]\d|20[0-4]\d)\b", t)
        if yrs:
            y = int(yrs[-1])
    if y is None:
        return None
    return (y, q, m, d)


def _iso_to_ymd(iso):
    """('2026-04-30T..') -> (year, None, month, day). None if unparseable."""
    if not iso:
        return None
    try:
        dt = datetime.strptime(iso[:10], "%Y-%m-%d")
        return (dt.year, None, dt.month, dt.day)
    except ValueError:
        return None


def canonical_ymd(rec):
    """The most-sensible (year, quarter, month, day) for a record.

    Priority: COMMs-supplied actual publish date (datePublishedActual, authoritative —
    from the "Documents & reports" sitemap Excel, per COMMs 2026-09-03) → date embedded
    in the title (real content period) → API datePublished → dateModified → dateCreated.
    Returns None only if every source is empty.
    """
    return (_iso_to_ymd(rec.get("datePublishedActual"))
            or parse_title_date(rec.get("title", ""))
            or _iso_to_ymd(rec.get("datePublished"))
            or _iso_to_ymd(rec.get("dateModified"))
            or _iso_to_ymd(rec.get("dateCreated")))


def sort_key(rec):
    """Descending-chronology sort key. Missing components sort last within their year
    (a bare-year report sorts after any dated item of the same year, which keeps e.g.
    'Financial Statements 31 December 2025' above 'Laporan Tahunan 2025')."""
    ymd = canonical_ymd(rec)
    if not ymd:
        return (0, 0, 0, 0)
    y, q, m, d = ymd
    # derive month from quarter if only quarter known (Q1->3, Q2->6, Q3->9, Q4->12)
    mm = m if m else (q * 3 if q else 0)
    return (y or 0, mm, d or 0, q or 0)


def fmt_date(rec, lang):
    """Display date from the canonical period. Shows the most specific form available:
    full date if day known, "Month YYYY" if month known, "Qn YYYY" if only quarter,
    else "YYYY"."""
    ymd = canonical_ymd(rec)
    if not ymd:
        return ""
    y, q, m, d = ymd
    months = _ID_MONTH_NAMES if lang == "id" else _EN_MONTH_NAMES
    if d and m:
        return f"{d} {months[m - 1]} {y}" if lang == "id" else f"{months[m - 1]} {d}, {y}"
    if m:
        return f"{months[m - 1]} {y}"
    if q:
        return f"Q{q} {y}"
    return str(y)


def fmt_size(n):
    """Human-readable file size."""
    if not n:
        return ""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def file_on_disk(rec):
    fs = rec.get("fsPath", "")
    return bool(fs) and os.path.isfile(os.path.join(SCRIPT_DIR, fs))


# ─── Filter JS ────────────────────────────────────────────────────────────────

FILTER_JS = """
<script>
(function () {
  // Section chips: show/hide whole sections
  var chips = document.querySelectorAll('.doclib-chip');
  var sections = document.querySelectorAll('.doclib-section');
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      var key = chip.getAttribute('data-sec');
      chips.forEach(function (c) { c.classList.remove('active'); });
      chip.classList.add('active');
      sections.forEach(function (sec) {
        sec.style.display = (key === 'all' || sec.getAttribute('data-sec') === key) ? '' : 'none';
      });
    });
  });
}());
</script>
"""

# ─── Styles ───────────────────────────────────────────────────────────────────

STYLES = """
<style>
/* Full-bleed hero (simplified from vale.com .vale-fragmento-header-interno) */
.doclib-hero { position: relative; width: 100%; overflow: hidden; }
.doclib-hero .doclib-hero-img { display: block; width: 100%; height: 30rem; object-fit: cover; }
.doclib-hero .doclib-hero-img.img-mobile { height: 20rem; }
.doclib-hero .doclib-hero-scrim { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0,0,0,.15) 0%, rgba(0,0,0,.35) 55%, rgba(0,0,0,.65) 100%); }
.doclib-hero .doclib-hero-inner { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: flex-end; }
.doclib-hero .doclib-hero-inner .container { padding-bottom: 2.5rem; }
.doclib-hero .doclib-hero-eyebrow { color: #fff; font-size: 0.9rem; font-weight: 500; letter-spacing: .5px; text-transform: uppercase; margin-bottom: 0.5rem; opacity: .95; }
.doclib-hero h1 { color: #fff; font-size: 3.25rem; font-weight: 700; line-height: 1.1; margin: 0; }
@media (max-width: 768px) {
  .doclib-hero h1 { font-size: 1.5rem; }
  .doclib-hero .doclib-hero-inner .container { padding-bottom: 1.75rem; }
}
.doclib-header { padding: 2rem 0 1rem; }
.doclib-header p { color: #555; margin: 0; }
.doclib-chipbar { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; }
.doclib-chip {
  display: inline-flex; align-items: center;
  padding: 0.4rem 1rem; border-radius: 1.5rem;
  border: 2px solid var(--verde-vale, #006633);
  background: #fff; color: var(--verde-vale, #006633);
  font-weight: 500; cursor: pointer; white-space: nowrap;
  text-decoration: none; font-size: 0.9rem;
}
.doclib-chip.active, .doclib-chip:hover { background: var(--verde-vale, #006633); color: #fff; }
.doclib-section { margin-bottom: 1.75rem; }
.doclib-section-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 0.8rem; border-bottom: 2px solid #e8f5ee; padding-bottom: 0.5rem; }
.doclib-section-head h2 { font-size: 1.4rem; font-weight: 700; color: var(--verde-vale, #006633); margin: 0; }
.doclib-section-count { font-size: 0.85rem; color: #888; }
.doclib-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 0.6rem; }
.doclib-card {
  display: flex; align-items: flex-start; gap: 0.85rem;
  border: 1px solid #e0e0e0; border-radius: 8px; background: #fff;
  padding: 0.7rem; transition: box-shadow .15s, border-color .15s;
}
.doclib-card:hover { border-color: var(--verde-vale, #006633); box-shadow: 0 2px 10px rgba(0,102,51,.08); }
.doclib-card-main { flex: 1; min-width: 0; }
.doclib-card-title { font-weight: 600; font-size: 0.95rem; color: #222; line-height: 1.3; margin-bottom: 0.35rem; word-break: break-word; }
.doclib-card-meta { font-size: 0.78rem; color: #777; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
.doclib-card-dl {
  flex: 0 0 auto; align-self: center;
  display: inline-flex; align-items: center; gap: 0.35rem;
  padding: 0.4rem 0.9rem; border-radius: 1.5rem;
  background: var(--verde-vale, #006633); color: #fff;
  font-size: 0.8rem; text-decoration: none; font-weight: 500;
}
.doclib-card-dl:hover { background: #004d26; color: #fff; }
</style>
"""


# ─── Card + section rendering ─────────────────────────────────────────────────

def render_card(rec, lang):
    title = html_mod.escape(rec.get("title", ""))
    date_disp = html_mod.escape(fmt_date(rec, lang))
    size_disp = html_mod.escape(fmt_size(rec.get("sizeBytes", 0)))
    link = html_mod.escape(rec.get("link", ""))
    dl_label = "Download" if lang == "en" else "Unduh"

    # Language badge + per-card language filtering removed (COMMs 2026-09-03): bilingual
    # press releases were duplicating; title alone now distinguishes language.
    meta_parts = []
    if date_disp:
        meta_parts.append(f"<span>{date_disp}</span>")
    if size_disp:
        meta_parts.append(f"<span>{size_disp}</span>")
    meta_html = "".join(meta_parts)

    return f"""\
<div class="doclib-card">
  <div class="doclib-card-main">
    <div class="doclib-card-title">{title}</div>
    <div class="doclib-card-meta">{meta_html}</div>
  </div>
  <a class="doclib-card-dl" href="{link}" target="_blank" rel="noopener" download>&#8681; {dl_label}</a>
</div>"""


def render_section(section, recs, lang):
    meta = SECTION_META[section]
    key = meta["key"]
    heading = section if lang == "en" else _id_section_heading(section)

    # Sort newest-first by canonical (title-derived) chronology
    recs_sorted = sorted(recs, key=sort_key, reverse=True)
    cards = "\n".join(render_card(r, lang) for r in recs_sorted)

    # Language sub-filter removed (COMMs 2026-09-03): title alone distinguishes language.
    return f"""\
<section class="doclib-section" data-sec="{key}">
  <div class="doclib-section-head">
    <h2>{html_mod.escape(heading)}</h2>
    <span class="doclib-section-count">{len(recs_sorted)}</span>
  </div>
  <div class="doclib-cards">
{cards}
  </div>
</section>"""


def _id_section_heading(section):
    return {
        "Annual Reports": "Laporan Tahunan",
        "Sustainability Reports": "Laporan Keberlanjutan",
        "Financial Statements": "Laporan Keuangan",
        "Presentation": "Presentasi",
        "Press Releases & Announcements": "Siaran Pers & Pengumuman",
    }[section]


# ─── Page builder ─────────────────────────────────────────────────────────────

# Chrome carries a Liferay language switcher whose <a> uses the dynamic
# /c/portal/update_language endpoint (404s on static hosting). Repoint it to the
# static other-language Document Library page.
# EN chrome renders this nav EMPTY (no pill) → must INJECT one; ID chrome has a
# pill to repoint. Same logic as build-news.py.
_LANG_NAV_RE = re.compile(
    r'(<nav[^>]*vale-widget-seletor-pt-en[^>]*>)([\s\S]*?)(</nav>)'
)
_HAS_ANCHOR_RE = re.compile(r'<a\b[^>]*\bhref="[^"]*"')

def _fix_lang_toggle(header, target_url, pill_label="EN"):
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


def build_page(records, lang):
    header, footer = get_chrome(lang)

    if lang == "en":
        page_title = "Documents and Reports — PT Vale Indonesia Tbk"
        heading = "Documents and Reports"
        intro = "Annual reports, sustainability reports, financial statements, presentations, and press releases."
        all_label = "All"
        other_page = "/in/indonesia/dokumen-dan-laporan.html"
    else:
        page_title = "Dokumen dan Laporan — PT Vale Indonesia Tbk"
        heading = "Dokumen dan Laporan"
        intro = "Laporan tahunan, laporan keberlanjutan, laporan keuangan, presentasi, dan siaran pers."
        all_label = "Semua"
        other_page = "/indonesia/documents-and-reports.html"

    header = re.sub(r'<title>[^<]*</title>', f'<title>{page_title}</title>', header, count=1)
    header = _fix_lang_toggle(header, other_page, "ID" if lang == "en" else "EN")

    # Group records by section. Press Releases follow the page language toggle
    # (COMMs 2026-09-03): EN page shows EN press releases, ID page shows Bahasa (BH)
    # ones — no per-section language sub-filter, no cross-language duplicates. All other
    # categories still show every document on both language pages.
    page_pr_lang = "EN" if lang == "en" else "BH"
    by_section = {}
    for rec in records:
        if rec["section"] == PRESS_SECTION and rec.get("lang") in ("EN", "BH") \
                and rec.get("lang") != page_pr_lang:
            continue
        by_section.setdefault(rec["section"], []).append(rec)

    # Filter chips (All + one per present section, in canonical order)
    chips = [f'<button class="doclib-chip active" data-sec="all">{all_label}</button>']
    for section in SECTION_ORDER:
        if section in by_section:
            meta = SECTION_META[section]
            label = meta["chip_en"] if lang == "en" else meta["chip_id"]
            chips.append(f'<button class="doclib-chip" data-sec="{meta["key"]}">{html_mod.escape(label)}</button>')

    # Sections in canonical order
    sections_html = "\n".join(
        render_section(section, by_section[section], lang)
        for section in SECTION_ORDER if section in by_section
    )

    hero = f"""\
<section class="doclib-hero">
  <img class="doclib-hero-img img-desktop d-none d-md-block" src="/documents/44618/1276840/press-releases-header.png" alt="{html_mod.escape(heading)}" fetchpriority="high">
  <img class="doclib-hero-img img-mobile d-md-none" src="/documents/44618/1276840/press-releases-header-mobile.png" alt="{html_mod.escape(heading)}" fetchpriority="high">
  <div class="doclib-hero-scrim"></div>
  <div class="doclib-hero-inner">
    <div class="container">
      <div class="doclib-hero-eyebrow">PT Vale Indonesia</div>
      <h1>{html_mod.escape(heading)}</h1>
    </div>
  </div>
</section>"""

    main_content = f"""\
<div class="layout-content portlet-layout" id="main-content" role="main">
{STYLES}
{hero}
<div class="container doclib-header">
  <p>{html_mod.escape(intro)}</p>
</div>
<div class="container">
  <div class="doclib-chipbar">
    {"".join(chips)}
  </div>
{sections_html}
</div>
{FILTER_JS}
</div>
"""

    return header + main_content + footer


# ─── Main ─────────────────────────────────────────────────────────────────────

def load_records():
    try:
        with open(DATA_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as e:
        sys.exit(f"FATAL: invalid JSON in {DATA_FILE} at line {e.lineno}, col {e.colno}: {e.msg}")
    except FileNotFoundError:
        sys.exit(f"FATAL: data file not found: {DATA_FILE}")

    valid = []
    missing_files = 0
    for rec in data:
        if not rec.get("title") or not rec.get("link"):
            warn(f"skipping record id={rec.get('id')} — missing title or link")
            continue
        if rec.get("section") not in SECTION_META:
            warn(f"skipping record id={rec.get('id')} — unknown section {rec.get('section')!r}")
            continue
        if not file_on_disk(rec):
            missing_files += 1
            warn(f"file not on disk (link may 404 until deployed): {rec.get('link')}")
        valid.append(rec)
    if missing_files:
        warn(f"{missing_files} record(s) have no file on disk yet")
    return valid


def main():
    dry_run = "--dry-run" in sys.argv
    records = load_records()

    # stats
    from collections import Counter
    by_sec = Counter(r["section"] for r in records)
    print(f">>> Loaded {len(records)} document records")
    for section in SECTION_ORDER:
        if section in by_sec:
            print(f"      {by_sec[section]:3}  {section}")

    for lang, path in (("en", EN_PAGE_PATH), ("id", ID_PAGE_PATH)):
        html_out = build_page(records, lang)
        if dry_run:
            print(f"  [dry-run] would write {os.path.relpath(path, SCRIPT_DIR)} ({len(html_out):,} bytes)")
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html_out)
            print(f"  wrote {os.path.relpath(path, SCRIPT_DIR)} ({len(html_out):,} bytes)")

    if warnings:
        print(f"\n>>> {len(warnings)} warning(s) — see stderr")
    print(">>> Doc Library build complete." + (" (dry-run)" if dry_run else ""))


if __name__ == "__main__":
    main()
