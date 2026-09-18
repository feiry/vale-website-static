#!/usr/bin/env python3
"""
Export the PT Vale Indonesia **Document Library** from Liferay Headless REST API,
tag each document with its section (folder name) + language, and download every
PDF into the static mirror at its real path so the download links work unchanged.

This is the corrected, Indonesia-specific export. The earlier export
(export-vale-data.py, DOC_FOLDERS=["337618"]) used the page JS's FALLBACK default
folder and returned 26 generic global/Oman/Brazil PDFs — useless. Discard those.

Real library = 6 non-empty folders (verified live 2026-07-20):
  1371772 Annual Report          25
  1373270 Sustainability Report   20
  1374000 Financial Statements    73
  8997207 presentation           12
  1438416 EN  (press releases)   64   -> section "Press Releases", lang EN
  1438419 BH  (press releases)   58   -> section "Press Releases", lang BH

Outputs:
  site-data/documents.json  - build input (metadata, one record per document)
  site/vale.com/documents/44618/<folder>/<name>  - the PDF files (flat form, '+'
      literal for spaces, matching the existing mirror convention; NO uuid subpath)

Files are saved at the FLAT contentUrl form (no uuid). Verified both flat and uuid
forms serve 200 application/pdf at source; flat matches the existing mirror layout.
"""
import json, os, re, sys, time, urllib.request, urllib.parse

BASE = "https://vale.com"
UA = "Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
SITE_ROOT = "site/vale.com"          # mirror root
OUT_JSON = "site-data/documents.json"

# folder id -> (section label as shown on the live page, language tag or None)
FOLDERS = [
    ("1371772", "Annual Reports",              None),
    ("1373270", "Sustainability Reports",      None),
    ("1374000", "Financial Statements",        None),
    ("8997207", "Presentation",                None),
    ("1438416", "Press Releases & Announcements", "EN"),
    ("1438419", "Press Releases & Announcements", "BH"),
]

os.makedirs("site-data", exist_ok=True)


def api(path, retries=3):
    url = BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if i == retries - 1:
                print(f"  ! API failed {path}: {e}", file=sys.stderr)
                return None
            time.sleep(2)


def fetch_folder(folder, page_size=100):
    items, page = [], 1
    while True:
        d = api(f"/o/headless-delivery/v1.0/document-folders/{folder}/documents?page={page}&pageSize={page_size}")
        if not d or not d.get("items"):
            break
        items.extend(d["items"])
        if len(items) >= d.get("totalCount", 0) or len(d["items"]) < page_size:
            break
        page += 1
        time.sleep(0.3)
    return items


def path_from_content_url(content_url):
    """Return (mirror_fs_path, site_link) from a Liferay contentUrl.

    contentUrl = /documents/44618/<folder>/<name>.pdf/<uuid>?version=..&download=true
    We want the FLAT form: /documents/44618/<folder>/<name>.pdf (no uuid, no query),
    keeping '+' literal (matches existing mirror + news-image convention). The link
    the page uses is exactly this flat path.
    """
    p = content_url.split("?", 1)[0]                 # drop query
    # strip the trailing /<uuid> segment (32-hex-ish with dashes)
    m = re.match(r"^(/documents/\d+/\d+/.+?\.[A-Za-z0-9]+)/[0-9a-fA-F-]{20,}$", p)
    flat = m.group(1) if m else p
    # filesystem path: '+' stays literal (the mirror serves such names); decode %xx
    fs_rel = urllib.parse.unquote(flat.lstrip("/"))
    fs_path = os.path.join(SITE_ROOT, fs_rel)
    return fs_path, flat


def download(url_path, fs_path, expected_size, retries=3):
    """Download BASE+url_path to fs_path. Skip if present with matching size.
    Returns 'skip' | 'ok' | 'fail'."""
    if os.path.isfile(fs_path):
        if not expected_size or os.path.getsize(fs_path) == expected_size:
            return "skip"
    os.makedirs(os.path.dirname(fs_path), exist_ok=True)
    url = BASE + urllib.parse.quote(url_path, safe="/+%")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            tmp = fs_path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, fs_path)
            return "ok"
        except Exception as e:
            if i == retries - 1:
                print(f"  ! download failed {url_path}: {e}", file=sys.stderr)
                return "fail"
            time.sleep(2)


def main():
    records = []
    seen_files = {}   # flat link -> first record idx (detect true dup files across EN/BH)
    print(">>> Exporting Document Library metadata...")
    for folder, section, lang in FOLDERS:
        items = fetch_folder(folder)
        print(f"    folder {folder} [{section}{'/'+lang if lang else ''}]: {len(items)} docs")
        for it in items:
            curl = it.get("contentUrl", "")
            if not curl:
                print(f"      - SKIP (no contentUrl): {it.get('title')!r}", file=sys.stderr)
                continue
            fs_path, link = path_from_content_url(curl)
            rec = {
                "id": it.get("id"),
                "folder": folder,
                "section": section,
                "lang": lang,
                "title": it.get("title", ""),
                "fileName": it.get("fileName", ""),
                "ext": it.get("fileExtension", ""),
                "sizeBytes": it.get("sizeInBytes", 0),
                "dateCreated": it.get("dateCreated", ""),
                "dateModified": it.get("dateModified", ""),
                "datePublished": it.get("datePublished", ""),
                "description": it.get("description", ""),
                "link": link,             # flat site path used in the download button
                "fsPath": fs_path,        # local mirror path (for build + verify)
                "dup_of": None,
            }
            if link in seen_files:
                rec["dup_of"] = seen_files[link]   # same physical file (EN/BH share it)
            else:
                seen_files[link] = len(records)
            records.append(rec)

    print(f">>> Total records: {len(records)} "
          f"({sum(1 for r in records if r['dup_of'] is None)} unique files, "
          f"{sum(1 for r in records if r['dup_of'] is not None)} shared/dup)")

    json.dump(records, open(OUT_JSON, "w"), ensure_ascii=False, indent=1)
    print(f">>> Wrote {OUT_JSON}")

    # ---- download PDFs ----
    print(">>> Downloading files into the mirror (skip = already present)...")
    stats = {"ok": 0, "skip": 0, "fail": 0}
    failed = []
    uniq = [r for r in records if r["dup_of"] is None]
    for n, r in enumerate(uniq, 1):
        res = download(r["link"], r["fsPath"], r["sizeBytes"])
        stats[res] += 1
        if res == "fail":
            failed.append(r)
        if n % 20 == 0 or res == "ok":
            mb = (r["sizeBytes"] or 0) / 1e6
            print(f"  [{n}/{len(uniq)}] {res:4} {mb:6.1f}MB  {r['section'][:22]:22} {r['title'][:44]}")
    print(f">>> Download done: {stats['ok']} downloaded, {stats['skip']} already present, "
          f"{stats['fail']} FAILED")
    if failed:
        print("   FAILED (source 404 or error) — flag to Vale:")
        for r in failed:
            print(f"     - [{r['section']}] {r['title']}  {r['link']}")
    print("\nEXPORT COMPLETE.")


if __name__ == "__main__":
    main()
