#!/usr/bin/env python3
"""extract-page-content.py — pull the editable content out of an existing page.

Given a cloned page under site/vale.com/, emit a simple, position-indexed content
file that COMMs can edit comfortably (no 9,000-line HTML). GDI later feeds the edited
file to inject-page-content.py to produce a new page with the same chrome/layout.

Usage:
    python3 extract-page-content.py <path-to-page.html> [-o out.md]

The output file records, in document order, every editable element in the page's
main-content region. Each block's value is the element's RAW inner content (or the
image src/alt), stored verbatim so an extract→inject round-trip with no edits
reproduces the source byte-for-byte. COMMs edits the visible text/links/images in
place; they must NOT add or remove blocks (v1 = edit-in-place, same structure).

The `--- header ---` block carries a fingerprint (editable count, type sequence,
whole-file sha) that inject-page-content.py verifies before touching anything.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from pagecontent_common import (  # noqa: E402
    scan_editables, type_sequence_sha, file_sha, find_main_content, PageStructureError,
)

# Sentinels delimiting a raw value. Chosen so they cannot collide with HTML content
# (which is full of < and >): use guillemet-fenced tokens that never occur in the pages.
_VAL_OPEN = "«VAL»"    # «VAL»
_VAL_CLOSE = "«/VAL»"  # «/VAL»


def _rel_page(path):
    """site/vale.com/indonesia/dividend.html -> indonesia/dividend.html"""
    p = os.path.abspath(path)
    marker = os.sep + os.path.join("site", "vale.com") + os.sep
    i = p.find(marker)
    return p[i + len(marker):] if i != -1 else os.path.basename(p)


def _heading_hint(html, editables, idx):
    """A short human label for a block: the nearest preceding text editable's content,
    truncated — helps COMMs know what each field is."""
    for j in range(idx, -1, -1):
        e = editables[j]
        if e["type"] in ("text",) and e["inner"]:
            s, en = e["inner"]
            txt = html[s:en].strip()
            txt = " ".join(txt.split())
            if txt:
                return txt[:50]
    return ""


def extract(path):
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    find_main_content(html)  # validate structure early
    editables = scan_editables(html)

    rel = _rel_page(path)
    lang = "id" if rel.startswith("in/") else "en"

    lines = []
    lines.append("---")
    lines.append("# Page content — edit the VALUES only. Do NOT add/remove/reorder blocks.")
    lines.append("# Each block is one editable element, numbered by its position on the page.")
    lines.append(f"source_page: {rel}")
    lines.append(f"lang: {lang}")
    lines.append(f"editable_count: {len(editables)}")
    lines.append(f"type_sequence_sha: {type_sequence_sha(editables)}")
    lines.append(f"source_page_sha: {file_sha(html)}")
    lines.append("---")
    lines.append("")

    for idx, e in enumerate(editables):
        hint = _heading_hint(html, editables, idx)
        label = f"[{idx}] {e['type']}  <{e['tag']}>"
        if hint and e["type"] != "text":
            label += f"  — under: {hint!r}"
        elif e["hint"]:
            label += f"  — id: {e['hint']}"
        lines.append(f"### {label}")

        if e["type"] == "image":
            src = html[e["src"][0]:e["src"][1]] if e["src"] else ""
            alt = html[e["alt"][0]:e["alt"][1]] if e["alt"] else ""
            lines.append(f"image[{idx}].src: {src}")
            lines.append(f"image[{idx}].alt: {alt}")
            lines.append(f"image[{idx}].new:            # attach a file + put its name here to replace; blank = keep")
        elif e["type"] == "link":
            inner = html[e["inner"][0]:e["inner"][1]] if e["inner"] else ""
            href = html[e["href"][0]:e["href"][1]] if e["href"] else ""
            lines.append(f"link[{idx}].text: {_VAL_OPEN}{inner}{_VAL_CLOSE}")
            lines.append(f"link[{idx}].href: {href}")
        else:  # text / rich-text / html
            inner = html[e["inner"][0]:e["inner"][1]] if e["inner"] else ""
            key = e["type"].replace("-", "")
            # multi-line-safe: wrap the raw value between sentinels
            lines.append(f"{key}[{idx}]: {_VAL_OPEN}{inner}{_VAL_CLOSE}")
        lines.append("")

    return "\n".join(lines) + "\n"


def main():
    argv = sys.argv[1:]
    out = None
    if "-o" in argv:
        i = argv.index("-o")
        out = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("-")]
    if len(args) != 1:
        print("usage: python3 extract-page-content.py <page.html> [-o out.md]", file=sys.stderr)
        sys.exit(2)
    path = args[0]
    if not os.path.isfile(path):
        print(f"ERROR: not a file: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        content = extract(path)
    except PageStructureError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(content)
        n = content.count("\n### [")
        print(f"✓ extracted {n} editable blocks -> {out}")
    else:
        sys.stdout.write(content)


if __name__ == "__main__":
    main()
