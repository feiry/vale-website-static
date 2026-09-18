#!/usr/bin/env python3
"""intake-to-awards.py — inject COMMs award/certification items into the two
awards-and-certifications pages (EN + ID).

Input is the `awards-record.json` saved by the visual form (make-awards-editor.py):
a batch of items, each an "award" or "certification", with bilingual text and an
optional attached image. Unlike news/docs there is NO data file + rebuild — awards
content lives directly in the cloned Liferay HTML — so this tool does direct row
injection into both language pages, then backs up + self-checks each page.

Usage:
    python3 intake-to-awards.py path/to/awards-record.json --dry-run   # inspect
    python3 intake-to-awards.py path/to/awards-record.json             # writes + backs up

Injection:
- award  -> the accordion panel whose <span class="lead"> == item.year; new 3-col row
            becomes the first DATA row of that panel (after the header-label row).
            Missing year panel is auto-created in descending-year sort position.
- cert   -> new 5-col row inserted as the first row under <h2>Certification</h2>.
- image  -> served from /documents/44618/awards/<file> (keep extension; spaces -> '+').

Safety: per-page timestamped backup, HTML well-formedness self-check (tag balance +
presence of the injected markers); on failure the backup is restored and the tool
exits non-zero. No external dependencies (stdlib only).
"""

import os
import re
import sys
import json
import html
import shutil
import uuid
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

EN_PAGE = os.path.join(SCRIPT_DIR, "site/vale.com/indonesia/awards-and-certifications.html")
ID_PAGE = os.path.join(SCRIPT_DIR, "site/vale.com/in/indonesia/penghargaan-dan-sertifikasi.html")

AWARDS_FOLDER = "awards"           # /documents/44618/awards/<file>
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
YEAR_RE = re.compile(r"^(19|20)\d{2}$")

# link is optional, awards only; restrict to relative/site links to avoid off-site leaks
LINK_OK_RE = re.compile(r"^/(in/)?indonesia/")


class IntakeError(Exception):
    pass


# ─── helpers ──────────────────────────────────────────────────────────────────

def _uid():
    """Fresh Liferay-style id (uuid4, hyphenated hex) — never collides with existing."""
    return str(uuid.uuid4())


def _enc(name):
    """Site path/link encoding: spaces -> '+' (matches documents.json convention)."""
    return name.replace(" ", "+")


def _esc(text):
    """Escape user text for safe HTML body insertion (keep quotes readable)."""
    return html.escape(str(text or ""), quote=False)


def image_paths(filename):
    """Return (served_link, on_disk_dest) for an attached award image, or ('','')."""
    if not filename:
        return "", ""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in IMAGE_EXTS:
        raise IntakeError(
            f"image {filename!r} has unsupported extension {ext!r}. "
            f"Allowed: {', '.join(sorted(IMAGE_EXTS))}.")
    enc = _enc(filename)
    link = f"/documents/44618/{AWARDS_FOLDER}/{enc}"
    dest = os.path.join("site/vale.com/documents/44618", AWARDS_FOLDER, enc)
    return link, dest


# ─── row / panel builders ─────────────────────────────────────────────────────

def _col_paragraph(text):
    return (
        '           <div class="col col-lg-4 col-sm-12 col-12 col-md-4">\n'
        f'            <div class="lfr-layout-structure-item-basic-component-paragraph lfr-layout-structure-item-{_uid()} " data-layout-structure-item-id="{_uid()}">\n'
        f'             <div id="fragment-{_uid()}">\n'
        '              <div class="clearfix component-paragraph text-break" data-lfr-editable-id="element-text" data-lfr-editable-type="rich-text">\n'
        f'               <p>{_esc(text)}</p>\n'
        '              </div>\n'
        '             </div>\n'
        '            </div>\n'
        '           </div>\n'
    )


def _col_image(img_link, href):
    inner_open = (
        f'<a rel="noopener noreferrer" target="_blank" href="{html.escape(href, quote=True)}">\n'
        if href else "")
    inner_close = "</a>" if href else ""
    if img_link:
        img = (
            f'                <picture>\n'
            f'                 <img alt="" class="w-100" data-lfr-editable-id="image-square" data-lfr-editable-type="image" src="{html.escape(img_link, quote=True)}">\n'
            f'                </picture>')
    else:
        img = '                <!-- no image supplied -->'
    return (
        '           <div class="col col-lg-4 col-sm-12 col-12 col-md-4">\n'
        f'            <div class="lfr-layout-structure-item-basic-component-image lfr-layout-structure-item-{_uid()} " data-layout-structure-item-id="{_uid()}">\n'
        f'             <div id="fragment-{_uid()}">\n'
        f'              <div class="component-image overflow-hidden">{inner_open}'
        f'{img}{inner_close}\n'
        '              </div>\n'
        '             </div>\n'
        '            </div>\n'
        '           </div>\n'
    )


def _spacer(py="py-1"):
    return (
        f'         <div class="lfr-layout-structure-item-basic-component-spacer lfr-layout-structure-item-{_uid()} " data-layout-structure-item-id="{_uid()}">\n'
        f'          <div id="fragment-{_uid()}">\n'
        f'           <div class="{py}"></div>\n'
        '          </div>\n'
        '         </div>\n'
    )


def build_award_row(item, lang):
    """3-col award row (description · awarding body · image[+link]) + trailing spacer."""
    blk = item.get(lang) or item.get("en") or item.get("id") or {}
    img_link, _ = image_paths(item.get("image", ""))
    href = item.get("link", "").strip()
    if href and not LINK_OK_RE.match(href):
        raise IntakeError(
            f"award link {href!r} must be a local /indonesia/… or /in/indonesia/… path.")
    row = (
        f'         <div class="lfr-layout-structure-item-{_uid()} lfr-layout-structure-item-row " data-layout-structure-item-id="{_uid()}">\n'
        '          <div class="row align-items-lg-start align-items-sm-start align-items-start align-items-md-start flex-lg-row flex-sm-row flex-row flex-md-row">\n'
        f'{_col_paragraph(blk.get("description", ""))}'
        f'{_col_paragraph(blk.get("awarding_body", ""))}'
        f'{_col_image(img_link, href)}'
        '          </div>\n'
        '         </div>\n'
    )
    return row + _spacer("py-1")


def build_cert_row(item, lang):
    """5-col certification row (standard · validity · scope · issuer · image)."""
    blk = item.get(lang) or item.get("en") or item.get("id") or {}
    img_link, _ = image_paths(item.get("image", ""))

    def col(width, text):
        return (
            f'     <div class="col col-lg-{width} col-sm-12 col-12 col-md-{width}">\n'
            f'      <div class="lfr-layout-structure-item-basic-component-paragraph lfr-layout-structure-item-{_uid()} " data-layout-structure-item-id="{_uid()}">\n'
            f'       <div id="fragment-{_uid()}">\n'
            '        <div class="clearfix component-paragraph text-break" data-lfr-editable-id="element-text" data-lfr-editable-type="rich-text">\n'
            f'         <p>{_esc(text)}</p>\n'
            '        </div>\n'
            '       </div>\n'
            '      </div>\n'
            '     </div>\n'
        )

    if img_link:
        img_col = (
            f'     <div class="col col-lg-3 col-sm-12 col-12 col-md-3">\n'
            f'      <div class="lfr-layout-structure-item-basic-component-image lfr-layout-structure-item-{_uid()} " data-layout-structure-item-id="{_uid()}">\n'
            f'       <div id="fragment-{_uid()}">\n'
            '        <div class="component-image overflow-hidden"><picture>\n'
            f'          <img alt="" class="w-100" data-lfr-editable-id="image-square" data-lfr-editable-type="image" src="{html.escape(img_link, quote=True)}">\n'
            '         </picture>\n'
            '        </div>\n'
            '       </div>\n'
            '      </div>\n'
            '     </div>\n'
        )
    else:
        img_col = '     <div class="col col-lg-3 col-sm-12 col-12 col-md-3"></div>\n'

    row = (
        f'   <div class="lfr-layout-structure-item-{_uid()} lfr-layout-structure-item-row " data-layout-structure-item-id="{_uid()}">\n'
        '    <div class="row align-items-lg-start align-items-sm-start align-items-start align-items-md-start flex-lg-row flex-sm-row flex-row flex-md-row">\n'
        f'{col(2, blk.get("standard", ""))}'
        f'{col(2, blk.get("validity", ""))}'
        f'{col(3, blk.get("scope", ""))}'
        f'{col(2, blk.get("issuer", ""))}'
        f'{img_col}'
        '    </div>\n'
        '   </div>\n'
    )
    return row + _spacer("py-2").replace("         ", "   ")


def build_year_panel(year, inner_rows_html):
    """A fresh accordion-item panel for a year, wrapping the given rows."""
    btn = _uid()[:8]
    return (
        '     <div class="accordion-item">'
        f'<button id="accordion-button-{btn}" aria-expanded="false" class="position-relative d-block text-left py-3 w-100 d-flex flex-wrap flex-md-nowrap align-items-center bg-branco border-0">\n'
        '       <div class="contents-accordion-title">\n'
        '        <div class="accordion-title p-0 m-0 pr-6 text-verde-vale" data-lfr-editable-id="titulo" data-lfr-editable-type="rich-text">\n'
        f'         <span class="lead">{_esc(year)}</span>\n'
        '        </div> <span class="icon2 text-verde-vale" aria-hidden="true"> </span>\n'
        '       </div> </button>\n'
        '      <div class="accordion-content px-3">\n'
        '       <div class="conteudo-montado">\n'
        '        <div>\n'
        f'{inner_rows_html}'
        '        </div>\n'
        '       </div>\n'
        '      </div>\n'
        '     </div>\n'
    )


# ─── page mutation ────────────────────────────────────────────────────────────

def _find_year_panel(text, year):
    """Return (button_start_idx, content_insert_idx) for a year's accordion panel,
    or None. content_insert_idx is right after the panel's `<div class="conteudo-montado">
    <div>` opener where a new first row goes."""
    m = re.search(rf'<span class="lead">\s*{re.escape(year)}\s*</span>', text)
    if not m:
        return None
    # the panel's rows live in the next `conteudo-montado` after this span
    cm = re.search(r'<div class="conteudo-montado">\s*<div>\s*', text[m.end():])
    if not cm:
        raise IntakeError(f"found year {year} but no conteudo-montado after it (markup drift).")
    insert_at = m.end() + cm.end()
    # Skip the leading header-label row (the <h6> Award Name/Presenter/Photo row) so the
    # new data row lands AFTER the header, not spliced into it. The header row is a full
    # `...-row` block containing three heading columns; its `.row` closes with `</div></div>`
    # and is followed by a spacer block. We must consume the WHOLE header row (all three
    # heading cols) — not just the first col — so anchor on the spacer that terminates it.
    after = text[insert_at:]
    hdr = re.match(
        r'\s*<div class="lfr-layout-structure-item-[0-9a-f-]+ lfr-layout-structure-item-row "[^>]*>'
        r'\s*<div class="row[^"]*">'          # the flex row opener
        r'.*?'                                 # the three heading columns
        r'</div>\s*</div>\s*'                  # closes .row and the item-row wrapper
        # header-terminating spacer: <div spacer><div fragment><div py-N></div></div></div>
        # → the py-N div self-closes, then fragment closes, then spacer closes = 3 </div>.
        r'<div class="lfr-layout-structure-item-basic-component-spacer[^>]*>'
        r'\s*<div id="fragment-[^"]*">\s*<div class="py-\d+"></div>\s*</div>\s*</div>\s*',
        after, re.DOTALL)
    # Only skip if this really is the header row (contains the heading components). Guard
    # against over-consuming a data row: require the matched span to include a heading AND
    # not include a paragraph/image component (those mark data rows).
    if hdr:
        span = after[:hdr.end()]
        if "component-heading" in span and "component-paragraph" not in span \
           and "component-image" not in span:
            insert_at += hdr.end()
    return (m.start(), insert_at)


def _accordion_year_positions(text):
    """List of (year:int, span_start_idx) for every year panel, in document order."""
    out = []
    for m in re.finditer(r'<span class="lead">\s*(\d{4})\s*</span>', text):
        out.append((int(m.group(1)), m.start()))
    return out


def inject_award(text, item):
    year = str(item.get("year", "")).strip()
    if not YEAR_RE.match(year):
        raise IntakeError(f"award year {year!r} must be a 4-digit year.")
    found = _find_year_panel(text, year)
    if found:
        _, insert_at = found
        return text[:insert_at] + item["_row_" ] + text[insert_at:]
    # auto-create the panel in descending-year order: place before the first existing
    # panel whose year < this one (i.e. right before its accordion-item wrapper).
    years = _accordion_year_positions(text)
    panel_html = build_year_panel(year, item["_row_"])
    target = None
    for y, span_idx in years:
        if y < int(year):
            target = span_idx
            break
    if target is None:
        raise IntakeError(
            f"could not place new year panel {year} (no accordion years found / all newer). "
            "Add the panel by hand or check markup.")
    # back up from the span to the enclosing `<div class="accordion-item">`
    ai = text.rfind('<div class="accordion-item">', 0, target)
    if ai == -1:
        raise IntakeError(f"no accordion-item wrapper before year {years} — markup drift.")
    return text[:ai] + panel_html + text[ai:]


def inject_cert(text, item):
    m = re.search(r'<h2[^>]*>\s*Certification\s*</h2>', text)
    if not m:
        # ID page heading may differ; try the Indonesian label too
        m = re.search(r'<h2[^>]*>\s*Sertifikasi\s*</h2>', text)
    if not m:
        raise IntakeError("could not find the Certification/Sertifikasi <h2> anchor.")
    # insert after the heading's closing wrapper divs — find the next row start after it
    nxt = re.search(r'(<div class="lfr-layout-structure-item-[0-9a-f-]+ lfr-layout-structure-item-row )', text[m.end():])
    if not nxt:
        raise IntakeError("no row found after the Certification heading (markup drift).")
    insert_at = m.end() + nxt.start()
    return text[:insert_at] + item["_row_"] + text[insert_at:]


# ─── well-formedness self-check ───────────────────────────────────────────────

def _div_delta(text):
    """(opens - closes) for <div>. The cloned Liferay page is NOT perfectly balanced
    (self-closing/void artifacts), so we compare this delta BEFORE vs AFTER injection:
    every div our rows add is balanced, so the delta must be unchanged."""
    return len(re.findall(r'<div\b', text)) - len(re.findall(r'</div>', text))


def self_check(path, markers, baseline_delta):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if _div_delta(text) != baseline_delta:
        return False, (f"div balance drifted (baseline delta {baseline_delta}, "
                       f"now {_div_delta(text)}) — injected rows are not self-balanced")
    for mk in markers:
        if mk not in text:
            return False, f"expected marker not present: {mk[:60]}"
    return True, "ok"


# ─── driver ───────────────────────────────────────────────────────────────────

def load_record(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise IntakeError("record has no 'items' array.")
    for i, it in enumerate(items):
        t = it.get("type")
        if t not in ("award", "certification"):
            raise IntakeError(f"item #{i}: type must be 'award' or 'certification', got {t!r}.")
        if not (it.get("en") or it.get("id")):
            raise IntakeError(f"item #{i}: needs at least one of 'en'/'id' text blocks.")
        if t == "award" and not YEAR_RE.match(str(it.get("year", "")).strip()):
            raise IntakeError(f"item #{i}: award needs a 4-digit 'year'.")
    return items


def process_page(path, items, lang, dry_run):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    baseline_delta = _div_delta(text)
    markers = []
    # process in reverse so multiple same-year awards keep submission order at the top
    for it in reversed(items):
        row = build_award_row(it, lang) if it["type"] == "award" else build_cert_row(it, lang)
        it["_row_"] = row
        # a stable marker: the description/standard text (escaped) to verify presence
        blk = it.get(lang) or it.get("en") or it.get("id") or {}
        key = blk.get("description") or blk.get("standard") or ""
        if key:
            markers.append(_esc(key))
        text = inject_award(text, it) if it["type"] == "award" else inject_cert(text, it)
    if dry_run:
        return None, markers
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak-awards-{stamp}"
    shutil.copy2(path, bak)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    ok, why = self_check(path, markers, baseline_delta)
    if not ok:
        shutil.copy2(bak, path)
        raise IntakeError(f"self-check failed on {os.path.basename(path)} ({why}); restored backup.")
    return bak, markers


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if len(args) != 1:
        print("usage: python3 intake-to-awards.py path/to/awards-record.json [--dry-run]",
              file=sys.stderr)
        sys.exit(2)
    try:
        items = load_record(args[0])
    except (IntakeError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # image plan
    print(f"✓ {len(items)} item(s): "
          f"{sum(1 for i in items if i['type']=='award')} award, "
          f"{sum(1 for i in items if i['type']=='certification')} certification")
    img_plan = []
    for it in items:
        fn = it.get("image", "")
        if fn:
            try:
                link, dest = image_paths(fn)
            except IntakeError as e:
                print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)
            img_plan.append((fn, dest))
    if img_plan:
        print("  images to place on disk (copy from the request folder):")
        for fn, dest in img_plan:
            print(f"    {fn}  ->  {dest}")

    try:
        for path, lang, label in ((EN_PAGE, "en", "EN"), (ID_PAGE, "id", "ID")):
            bak, markers = process_page(path, items, lang, dry_run)
            if dry_run:
                print(f"  [{label}] dry-run: {len(markers)} row(s) would be injected into "
                      f"{os.path.relpath(path, SCRIPT_DIR)}")
            else:
                print(f"  [{label}] injected into {os.path.relpath(path, SCRIPT_DIR)} "
                      f"(backup {os.path.basename(bak)})")
    except IntakeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("\n[dry-run] nothing written.")
    else:
        print("\n✓ Both pages updated. Next: copy the images above onto disk, then preview + deploy.")


if __name__ == "__main__":
    main()
