#!/usr/bin/env python3
"""rollback-vacancy.py — undo the last intake-to-vacancy.py apply.

intake-to-vacancy.py writes a `<page>.bak-<timestamp>` next to each career page on
every apply. This restores both pages from their most-recent backup, so you can undo
an apply without hand-copying files.

Usage:
  python3 rollback-vacancy.py [--dry-run] [--keep-backups] [--remove-pdf <slug>]

  --dry-run        show what would happen, change nothing
  --keep-backups   restore but do NOT delete the .bak files afterward
  --remove-pdf S   also delete site/vale.com/documents/d/guest/<S> (a placed PDF).
                   May be given multiple times.

Safe: if a page has no backup, it is left untouched and reported. Restoring copies the
newest backup over the page, then (by default) removes ALL .bak files for that page.
"""

import sys, os, glob, argparse

PAGES = [
    "site/vale.com/indonesia/career.html",
    "site/vale.com/in/indonesia/career.html",
]
DOC_DIR = "site/vale.com/documents/d/guest"


def newest_backup(page):
    baks = sorted(glob.glob(page + ".bak-*"))  # timestamp suffix sorts chronologically
    return baks[-1] if baks else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-backups", action="store_true")
    ap.add_argument("--remove-pdf", action="append", default=[],
                    help="slug under documents/d/guest to delete (repeatable)")
    args = ap.parse_args()

    print("=== VACANCY ROLLBACK ===")
    restored = 0
    for page in PAGES:
        if not os.path.isfile(page):
            print(f"  SKIP (page missing): {page}")
            continue
        bak = newest_backup(page)
        if not bak:
            print(f"  NO BACKUP for {page} — left untouched")
            continue
        allbaks = sorted(glob.glob(page + ".bak-*"))
        print(f"  RESTORE {page}")
        print(f"     from {os.path.basename(bak)}"
              + (f"  (+{len(allbaks)-1} older backup(s))" if len(allbaks) > 1 else ""))
        if not args.dry_run:
            with open(bak, "rb") as f:
                data = f.read()
            with open(page, "wb") as f:
                f.write(data)
            restored += 1
            if not args.keep_backups:
                for b in allbaks:
                    os.remove(b)
                print(f"     removed {len(allbaks)} backup file(s)")

    for slug in args.remove_pdf:
        path = os.path.join(DOC_DIR, slug)
        if os.path.isfile(path):
            print(f"  REMOVE PDF {path}")
            if not args.dry_run:
                os.remove(path)
        else:
            print(f"  PDF not found (skip): {path}")

    if args.dry_run:
        print("\n[dry-run] nothing changed.")
    else:
        print(f"\nDone. Restored {restored} page(s).")


if __name__ == "__main__":
    main()
