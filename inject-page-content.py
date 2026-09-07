#!/usr/bin/env python3
"""inject-page-content.py — build a page from an edited content file + a source page.

Takes the content file produced by extract-page-content.py (edited by COMMs) and a
COPY of the source page, and splices the edited values back into the editable
elements — by document-order position — leaving all chrome/footer/nav byte-identical.

Usage:
    python3 inject-page-content.py <filled-content.md> <source-page.html> -o <new-page.html>

Safety: before touching anything, it re-scans the source page and verifies the
editable count + type sequence (and, when possible, the whole-file sha) match the
content file's fingerprint. If the source drifted since extraction, it ABORTS —
position-index injection is only safe when the editable skeleton is unchanged.

Image replacement: for `image[i].new: somefile.jpg`, the new src is set to
/documents/44618/<new-page-slug>/somefile.jpg and the on-disk copy target is printed
for the operator to place (same "print, don't auto-copy" contract as intake-to-news).
"""

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from pagecontent_common import (  # noqa: E402
    scan_editables, type_sequence_sha, file_sha, PageStructureError,
)

_VAL_OPEN = "«VAL»"
_VAL_CLOSE = "«/VAL»"


class InjectError(Exception):
    pass


def parse_content_file(text):
    """Return (header dict, {index: {field: value}})."""
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        raise InjectError("content file missing `--- header ---` block")
    hdr_block, body = m.group(1), m.group(2)
    header = {}
    for line in hdr_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        header[k.strip()] = v.strip()

    values = {}  # idx -> dict of field->value

    # Split body into blocks by the "### " headers; parse key: value lines within.
    # Values may be wrapped in <<< >>> and span multiple lines.
    # Work line-by-line with sentinel-aware accumulation.
    lines = body.splitlines()
    i = 0
    keyline = re.compile(
        r'^(?P<kind>text|richtext|html|link|image)\[(?P<idx>\d+)\](?:\.(?P<field>\w+))?:\s?(?P<rest>.*)$'
    )
    while i < len(lines):
        m = keyline.match(lines[i])
        if not m:
            i += 1
            continue
        idx = int(m.group("idx"))
        kind = m.group("kind")
        field = m.group("field")  # src/alt/new/text/href for image&link; None for text/richtext/html
        rest = m.group("rest")

        # collect a possibly multi-line sentinel value
        val = rest
        if _VAL_OPEN in rest and _VAL_CLOSE not in rest:
            buf = [rest[rest.index(_VAL_OPEN) + len(_VAL_OPEN):]]
            i += 1
            while i < len(lines) and _VAL_CLOSE not in lines[i]:
                buf.append(lines[i]); i += 1
            if i < len(lines):
                tail = lines[i]
                buf.append(tail[:tail.index(_VAL_CLOSE)])
            val = "\n".join(buf)
        elif _VAL_OPEN in rest and _VAL_CLOSE in rest:
            val = rest[rest.index(_VAL_OPEN) + len(_VAL_OPEN):rest.rindex(_VAL_CLOSE)]
        else:
            # plain value (image src/alt/new/href) — strip trailing inline comment
            val = re.sub(r'\s{2,}#.*$', '', rest).strip()

        # canonical field name
        if kind in ("text", "richtext", "html"):
            field = "inner"
        values.setdefault(idx, {})[field] = val
        i += 1
    return header, values


def inject(content_path, source_path, out_path, image_folder=None):
    with open(content_path, encoding="utf-8") as fh:
        header, values = parse_content_file(fh.read())
    with open(source_path, encoding="utf-8") as fh:
        html = fh.read()

    editables = scan_editables(html)

    # ---- drift guard --------------------------------------------------------
    exp_count = int(header.get("editable_count", -1))
    if exp_count != len(editables):
        raise InjectError(
            f"editable count mismatch: content file expects {exp_count}, "
            f"source page has {len(editables)} — the page changed since extraction. Re-extract.")
    if header.get("type_sequence_sha") != type_sequence_sha(editables):
        raise InjectError(
            "type-sequence mismatch: the source page's editable structure changed "
            "since extraction. Re-extract from the current page.")
    src_sha_now = file_sha(html)
    if header.get("source_page_sha") and header["source_page_sha"] != src_sha_now:
        print("  note: source page bytes differ from extraction time, but the editable "
              "skeleton matches — proceeding.", file=sys.stderr)

    # slug for image destinations (from the OUTPUT filename)
    slug = os.path.splitext(os.path.basename(out_path))[0]
    image_registry = {}  # attached filename -> on-disk dest

    # ---- build edits, then apply right-to-left ------------------------------
    edits = []  # (start, end, replacement)
    for idx, e in enumerate(editables):
        v = values.get(idx)
        if not v:
            continue
        etype = e["type"]
        if etype == "image":
            new = (v.get("new") or "").strip()
            if new:
                dest_rel = f"/documents/44618/{slug}/{new}"
                if e["src"]:
                    edits.append((e["src"][0], e["src"][1], dest_rel))
                image_registry[new] = os.path.join(
                    "site", "vale.com", "documents", "44618", slug, new)
            if e["alt"] is not None and "alt" in v:
                edits.append((e["alt"][0], e["alt"][1], v["alt"]))
        elif etype == "link":
            if "text" in v and e["inner"]:
                edits.append((e["inner"][0], e["inner"][1], v["text"]))
            if "href" in v and e["href"]:
                edits.append((e["href"][0], e["href"][1], v["href"]))
        else:  # text / rich-text / html
            if "inner" in v and e["inner"]:
                edits.append((e["inner"][0], e["inner"][1], v["inner"]))

    edits.sort(key=lambda x: x[0], reverse=True)
    for s, en, rep in edits:
        html = html[:s] + rep + html[en:]

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    return image_registry, len(edits)


def main():
    argv = sys.argv[1:]
    out = None
    if "-o" in argv:
        i = argv.index("-o"); out = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("-")]
    if len(args) != 2 or not out:
        print("usage: python3 inject-page-content.py <content.md> <source.html> -o <new.html>",
              file=sys.stderr)
        sys.exit(2)
    content_path, source_path = args
    try:
        reg, n = inject(content_path, source_path, out)
    except (InjectError, PageStructureError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"✓ injected {n} edits -> {out}")
    if reg:
        print("  place these images on disk before deploy:")
        for fn, dest in reg.items():
            print(f"    <content-folder>/{fn}  ->  {dest}")


if __name__ == "__main__":
    main()
