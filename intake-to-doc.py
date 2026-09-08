#!/usr/bin/env python3
"""intake-to-doc.py — validate a COMMs document request and append it to documents.json.

Takes the `doc-record.json` produced by the visual document form (make-doc-editor.py)
— a tiny record of {section, title, date_published, pdf_file, lang} — validates it,
derives all the plumbing COMMs never sees (folder id, link, fsPath, sizeBytes,
description, id), and prepends a full record to site-data/documents.json so
build-doc-library.py renders it.

Usage:
    python3 intake-to-doc.py path/to/doc-record.json --dry-run    # inspect first
    python3 intake-to-doc.py path/to/doc-record.json              # writes + backs up

The tool NEVER deploys and never hand-mangles the JSON: it backs up documents.json to
a timestamped .bak-… and self-checks the result re-parses before replacing the file.
It prints the on-disk PDF path GDI must ensure exists.
"""

import os
import re
import sys
import json
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("build_doc_library", os.path.join(SCRIPT_DIR, "build-doc-library.py"))
_bd = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bd)
SECTION_ORDER = _bd.SECTION_ORDER
PRESS_SECTION = _bd.PRESS_SECTION

DATA_FILE = os.path.join(SCRIPT_DIR, "site-data", "documents.json")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Stable numeric folder id per section, derived from the existing library. Press
# Releases split by language; Quarterly Reports has no single folder (one per batch)
# so GDI must supply --folder for those.
SECTION_FOLDER = {
    "Annual Reports":         "1371772",
    "Sustainability Reports": "1373270",
    "Financial Statements":   "1374000",
    "Presentation":           "8997207",
}
PRESS_FOLDER = {"EN": "1438416", "BH": "1438419"}


class IntakeError(Exception):
    pass


def _encode(name):
    """Match the on-disk / link encoding used across documents.json: spaces -> '+'."""
    return name.replace(" ", "+")


def resolve_folder(section, lang, override):
    if override:
        return override
    if section == PRESS_SECTION:
        if lang not in PRESS_FOLDER:
            raise IntakeError(
                f"Press Releases need lang EN or BH to pick a folder; got {lang!r}.")
        return PRESS_FOLDER[lang]
    if section == "Quarterly Reports":
        raise IntakeError(
            "Quarterly Reports use a per-batch folder — pass --folder <id> "
            "(reuse the sibling batch's id from documents.json).")
    if section not in SECTION_FOLDER:
        raise IntakeError(f"no folder mapping for section {section!r}.")
    return SECTION_FOLDER[section]


def build_record_from_json(path, folder_override=None):
    path = os.path.abspath(path)
    folder_dir = os.path.dirname(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    section = str(data.get("section", "")).strip()
    if section not in SECTION_ORDER:
        raise IntakeError(
            f"section {section!r} is not allowed. Pick ONE of: {', '.join(SECTION_ORDER)}.")

    title = str(data.get("title", "")).strip()
    if not title:
        raise IntakeError("title is empty.")

    date = str(data.get("date_published", "")).strip()
    if not DATE_RE.match(date):
        raise IntakeError(f"date_published {date!r} is not in YYYY-MM-DD form.")

    pdf_file = str(data.get("pdf_file", "")).strip()
    if not pdf_file:
        raise IntakeError("pdf_file is empty.")
    if not pdf_file.lower().endswith(".pdf"):
        raise IntakeError(f"pdf_file {pdf_file!r} must be a .pdf.")

    lang = data.get("lang")
    if section == PRESS_SECTION and lang not in ("EN", "BH"):
        raise IntakeError("Press Releases require lang EN or BH.")
    if section != PRESS_SECTION:
        lang = None  # everything else is bilingual / not language-specific

    folder = resolve_folder(section, lang, folder_override)
    enc = _encode(pdf_file)
    link = f"/documents/44618/{folder}/{enc}"
    fs_path = f"site/vale.com/documents/44618/{folder}/{enc}"

    rec = {
        "section": section,
        "title": title,
        "fileName": pdf_file,
        "link": link,
        "fsPath": fs_path,
        "ext": "pdf",
        "folder": folder,
        "lang": lang,
        "datePublishedActual": date,
        "sizeBytes": 0,          # real size stamped from the on-disk PDF if present
        "description": title,
        "dup_of": None,
    }
    # stamp real size if the PDF is already staged on disk
    disk = os.path.join(SCRIPT_DIR, fs_path)
    if os.path.isfile(disk):
        rec["sizeBytes"] = os.path.getsize(disk)
    return rec, disk


def next_id(records):
    ids = [r["id"] for r in records if isinstance(r.get("id"), int)]
    return (max(ids) + 1) if ids else 1


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    folder_override = None
    if "--folder" in sys.argv:
        i = sys.argv.index("--folder"); folder_override = sys.argv[i + 1]
        args = [a for a in args if a != folder_override]
    if len(args) != 1:
        print("usage: python3 intake-to-doc.py path/to/doc-record.json [--folder <id>] [--dry-run]",
              file=sys.stderr)
        sys.exit(2)

    try:
        rec, disk = build_record_from_json(args[0], folder_override)
        with open(DATA_FILE, encoding="utf-8") as fh:
            records = json.load(fh)
        rec["id"] = next_id(records)
    except (IntakeError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("── document record ─────────────────────────────────────────")
    print(json.dumps(rec, indent=2, ensure_ascii=False))
    print("────────────────────────────────────────────────────────────")
    if not os.path.isfile(disk):
        print(f"⚠ PDF not on disk yet — place it at:\n    {disk}")
        print("  (sizeBytes will read 0 until the file exists; re-run after staging it,")
        print("   or the card size will show 0 — put the PDF there first for correct size.)")
    else:
        print(f"✓ PDF present ({rec['sizeBytes']} bytes): {disk}")

    if dry_run:
        print("\n[dry-run] nothing written.")
        return

    bak = DATA_FILE + ".bak-" + str(len(records))
    shutil.copy2(DATA_FILE, bak)
    new_records = [rec] + records
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(new_records, fh, indent=2, ensure_ascii=False)
    # self-check: re-parse before replacing
    with open(tmp, encoding="utf-8") as fh:
        json.load(fh)
    os.replace(tmp, DATA_FILE)
    print(f"\n✓ appended record id={rec['id']} ({len(records)} → {len(new_records)}). Backup: {os.path.basename(bak)}")
    print("  Next: python3 build-doc-library.py   (must exit 0), then preview + deploy.")


if __name__ == "__main__":
    main()
