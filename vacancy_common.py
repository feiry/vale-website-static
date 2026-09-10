"""vacancy_common.py — shared career-page vacancy-slot scanner.

Used by make-vacancy-manager.py (to populate the current-vacancy table) and
intake-to-vacancy.py (to locate slots for insert/remove and compute the drift
fingerprint), so both understand the career page the SAME way.

A job vacancy on career.html is a self-contained Liferay layout block:

  <div class="lfr-layout-structure-item-basic-component-paragraph lfr-layout-structure-item-<UUID> "
       data-layout-structure-item-id="<UUID>">
    <div id="fragment-<FRAG>" >
      <div class="clearfix component-paragraph text-break" data-lfr-editable-id="element-text"
           data-lfr-editable-type="rich-text"[ style="..."]>
        <p><a href="/documents/d/guest/<slug>" rel="noopener noreferrer" target="_blank">
          <strong>&gt;[ ]MM/DD/YYYY - Job vacancy for <title></strong>
        </a></p>
      </div>
    </div>
  </div>

The distinguishing marker of a *vacancy* paragraph (vs any other component-paragraph)
is that its <a> href points to /documents/d/guest/ AND the visible <strong> label
contains "Job vacancy" (EN) or "Lowongan Kerja" (ID). We work on raw offsets and never
reserialize — the pages must stay byte-identical outside the spans we change.

Font-size note: each vacancy slot renders at 20px because of a per-UUID CSS rule
`.lfr-layout-structure-item-<UUID>{font-size:var(--font-size-lg)}` in the external
layout stylesheet. A slot with a fresh UUID and no inline style falls back to 18px.
intake-to-vacancy.py handles this (reuse removed UUIDs, else inline style). This module
only *reads*; it exposes has_inline_fontsize so callers can reason about it.
"""

import re
import hashlib

SLOT_OPEN = '<div class="lfr-layout-structure-item-basic-component-paragraph'
# a vacancy link inside a slot
_VAC_A_RE = re.compile(
    r'<a href="(?P<href>/documents/d/guest/(?P<slug>[^"]+))"[^>]*>\s*'
    r'<strong>(?P<label>[^<]*(?:Job vacanc(?:y|ies)|Lowongan Kerja)[^<]*)</strong>'
)
_UUID_RE = re.compile(r'data-layout-structure-item-id="(?P<uuid>[0-9a-fA-F-]+)"')
_FRAG_RE = re.compile(r'<div id="fragment-(?P<frag>[0-9a-fA-F-]+)"')
_INLINE_FS_RE = re.compile(r'component-paragraph text-break"[^>]*style="[^"]*font-size')


class CareerStructureError(Exception):
    """career.html doesn't have the expected recent-opportunities structure."""


def _slot_span(html, inner_pos):
    """Given an offset inside a vacancy slot, return (start, end) of the enclosing
    lfr-layout-structure-item-basic-component-paragraph div (depth-balanced)."""
    start = html.rfind(SLOT_OPEN, 0, inner_pos)
    if start < 0:
        raise CareerStructureError("vacancy link not inside a component-paragraph slot")
    depth = 0
    for m in re.finditer(r'<div\b|</div>', html[start:start + 4000]):
        depth += 1 if m.group() == '<div' else -1
        if depth == 0:
            return start, start + m.end()
    raise CareerStructureError("unterminated vacancy slot div")


def scan_vacancies(html):
    """Return an ordered list of vacancy descriptors as they appear in the page.

    Each descriptor:
      { "slug":  <doc slug>,
        "href":  "/documents/d/guest/<slug>",
        "label": <visible strong text, HTML-escaped as stored>,
        "uuid":  <layout-item uuid>,
        "frag":  <fragment id>,
        "span":  (start, end),      # full slot div byte span
        "has_inline_fontsize": bool # slot carries an inline font-size style
      }
    """
    out = []
    for m in _VAC_A_RE.finditer(html):
        span = _slot_span(html, m.start())
        slot_html = html[span[0]:span[1]]
        um = _UUID_RE.search(slot_html)
        fm = _FRAG_RE.search(slot_html)
        out.append({
            "slug": m.group("slug"),
            "href": m.group("href"),
            "label": m.group("label").strip(),
            "uuid": um.group("uuid") if um else None,
            "frag": fm.group("frag") if fm else None,
            "span": span,
            "has_inline_fontsize": bool(_INLINE_FS_RE.search(slot_html)),
        })
    return out


def recent_list_insertion_point(html):
    """Byte offset at which a new (newest) vacancy slot should be inserted: right
    before the first existing vacancy slot. If none exist, insert right after the
    'Recent opportunities' heading's enclosing structure item — but in practice the
    page always has entries, so we require at least one and insert before it."""
    vac = scan_vacancies(html)
    if not vac:
        raise CareerStructureError("no existing vacancy slots to anchor insertion")
    return vac[0]["span"][0]


def vacancy_signature(html):
    """Ordered slug list — the stable identity of the current vacancy set, language
    independent enough for a drift check when combined per-page."""
    return [v["slug"] for v in scan_vacancies(html)]


def type_sequence_sha(html):
    return hashlib.sha256("|".join(vacancy_signature(html)).encode("utf-8")).hexdigest()[:16]


def file_sha(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
