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

def rec_date(rec):
    """Best display date for a record: prefer datePublished, then modified, created."""
    return rec.get("datePublished") or rec.get("dateModified") or rec.get("dateCreated") or ""


def fmt_date(iso, lang):
    """Format an ISO8601 timestamp (2026-04-30T14:34:00Z) as a display date."""
    if not iso:
        return ""
    try:
        dt = datetime.strptime(iso[:10], "%Y-%m-%d")
    except ValueError:
        return iso[:10]
    if lang == "id":
        months = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                  "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
        return f"{dt.day} {months[dt.month - 1]} {dt.year}"
    return dt.strftime("%B %-d, %Y")


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
  // Press-release language sub-filter: show/hide EN vs BH cards within its section
  var langBtns = document.querySelectorAll('.doclib-langbtn');
  langBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var lang = btn.getAttribute('data-lang');
      langBtns.forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var scope = btn.closest('.doclib-section');
      scope.querySelectorAll('.doclib-card[data-lang]').forEach(function (card) {
        card.style.display = (lang === 'all' || card.getAttribute('data-lang') === lang) ? '' : 'none';
      });
    });
  });
}());
</script>
"""

# ─── Styles ───────────────────────────────────────────────────────────────────

STYLES = """
<style>
.doclib-header { padding: 3rem 0 1.5rem; }
.doclib-header h1 { font-size: 2rem; font-weight: 700; color: var(--verde-vale, #006633); }
.doclib-header p { color: #555; margin-top: 0.5rem; }
.doclib-chipbar { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 2.5rem; }
.doclib-chip, .doclib-langbtn {
  display: inline-flex; align-items: center;
  padding: 0.4rem 1rem; border-radius: 1.5rem;
  border: 2px solid var(--verde-vale, #006633);
  background: #fff; color: var(--verde-vale, #006633);
  font-weight: 500; cursor: pointer; white-space: nowrap;
  text-decoration: none; font-size: 0.9rem;
}
.doclib-chip.active, .doclib-chip:hover,
.doclib-langbtn.active, .doclib-langbtn:hover { background: var(--verde-vale, #006633); color: #fff; }
.doclib-section { margin-bottom: 3rem; }
.doclib-section-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 1.25rem; border-bottom: 2px solid #e8f5ee; padding-bottom: 0.5rem; }
.doclib-section-head h2 { font-size: 1.4rem; font-weight: 700; color: var(--verde-vale, #006633); margin: 0; }
.doclib-section-count { font-size: 0.85rem; color: #888; }
.doclib-langfilter { display: flex; gap: 0.4rem; margin-left: auto; }
.doclib-langfilter .doclib-langbtn { padding: 0.25rem 0.8rem; font-size: 0.8rem; }
.doclib-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
.doclib-card {
  display: flex; align-items: flex-start; gap: 0.85rem;
  border: 1px solid #e0e0e0; border-radius: 8px; background: #fff;
  padding: 1rem; transition: box-shadow .15s, border-color .15s;
}
.doclib-card:hover { border-color: var(--verde-vale, #006633); box-shadow: 0 2px 10px rgba(0,102,51,.08); }
.doclib-card-icon { flex: 0 0 auto; width: 40px; height: 48px; border-radius: 4px; background: #e8f5ee; color: #006633; display: flex; align-items: center; justify-content: center; font-size: 0.65rem; font-weight: 700; letter-spacing: .5px; }
.doclib-card-main { flex: 1; min-width: 0; }
.doclib-card-title { font-weight: 600; font-size: 0.95rem; color: #222; line-height: 1.3; margin-bottom: 0.35rem; word-break: break-word; }
.doclib-card-meta { font-size: 0.78rem; color: #777; display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
.doclib-lang-tag { font-size: 0.68rem; font-weight: 700; padding: 0.1rem 0.45rem; border-radius: 1rem; background: #006633; color: #fff; }
.doclib-lang-tag.bh { background: #b8860b; }
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
    date_disp = html_mod.escape(fmt_date(rec_date(rec), lang))
    size_disp = html_mod.escape(fmt_size(rec.get("sizeBytes", 0)))
    ext = (rec.get("ext") or "pdf").upper()
    link = html_mod.escape(rec.get("link", ""))
    dl_label = "Download" if lang == "en" else "Unduh"

    lang_tag = ""
    lang_attr = ""
    if rec.get("lang"):
        lg = rec["lang"]  # EN or BH
        cls = "doclib-lang-tag bh" if lg == "BH" else "doclib-lang-tag"
        lang_tag = f'<span class="{cls}">{lg}</span>'
        lang_attr = f' data-lang="{lg}"'

    meta_parts = []
    if lang_tag:
        meta_parts.append(lang_tag)
    if date_disp:
        meta_parts.append(f"<span>{date_disp}</span>")
    if size_disp:
        meta_parts.append(f"<span>{size_disp}</span>")
    meta_html = "".join(meta_parts)

    return f"""\
<div class="doclib-card"{lang_attr}>
  <div class="doclib-card-icon">{html_mod.escape(ext)}</div>
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

    # Sort newest-first
    recs_sorted = sorted(recs, key=lambda r: rec_date(r), reverse=True)
    cards = "\n".join(render_card(r, lang) for r in recs_sorted)

    # Press Releases gets an EN/BH language sub-filter
    langfilter = ""
    if section == PRESS_SECTION:
        if lang == "en":
            labels = [("all", "All"), ("EN", "English"), ("BH", "Bahasa")]
        else:
            labels = [("all", "Semua"), ("EN", "English"), ("BH", "Bahasa")]
        btns = "".join(
            f'<button class="doclib-langbtn{" active" if k == "all" else ""}" data-lang="{k}">{v}</button>'
            for k, v in labels
        )
        langfilter = f'<div class="doclib-langfilter">{btns}</div>'

    return f"""\
<section class="doclib-section" data-sec="{key}">
  <div class="doclib-section-head">
    <h2>{html_mod.escape(heading)}</h2>
    <span class="doclib-section-count">{len(recs_sorted)}</span>
    {langfilter}
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

def build_page(records, lang):
    header, footer = get_chrome(lang)

    if lang == "en":
        page_title = "Documents and Reports — PT Vale Indonesia Tbk"
        heading = "Documents and Reports"
        intro = "Annual reports, sustainability reports, financial statements, presentations, and press releases."
        all_label = "All"
    else:
        page_title = "Dokumen dan Laporan — PT Vale Indonesia Tbk"
        heading = "Dokumen dan Laporan"
        intro = "Laporan tahunan, laporan keberlanjutan, laporan keuangan, presentasi, dan siaran pers."
        all_label = "Semua"

    header = re.sub(r'<title>[^<]*</title>', f'<title>{page_title}</title>', header, count=1)

    # Group records by section
    by_section = {}
    for rec in records:
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

    main_content = f"""\
<div class="layout-content portlet-layout" id="main-content" role="main">
{STYLES}
<div class="container doclib-header">
  <h1>{html_mod.escape(heading)}</h1>
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
