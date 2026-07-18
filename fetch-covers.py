#!/usr/bin/env python3
"""
Populate cover images for the 408 news records. The original export dropped the
cover URL. This fetches imagemDeCapa.image.contentUrl per article from the SAME
public Liferay Headless API (by friendlyUrlPath), sets rec['cover'] in news.json,
and downloads any cover image file not already present under site/vale.com/documents/.

No site re-crawl — data + specific image files only. Idempotent: skips records that
already have a cover, and images already on disk.
"""
import json, os, re, time, sys, urllib.request, urllib.parse

BASE = "https://vale.com"
SITE = "44618"
UA = "Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
DATA = "site-data/news.json"
SITE_DIR = "site/vale.com"

def api(path, retries=3):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            if i == retries - 1:
                print(f"  ! api fail {path}: {e}", file=sys.stderr); return None
            time.sleep(2)

def fetch_cover(slug):
    flt = urllib.parse.quote(f"friendlyUrlPath eq '{slug}'")
    d = api(f"/o/headless-delivery/v1.0/sites/{SITE}/structured-contents?filter={flt}&pageSize=1")
    if not d or not d.get('items'):
        return None
    it = d['items'][0]
    for f in it.get('contentFields', []):
        if f['name'] == 'imagemDeCapa':
            img = (f.get('contentFieldValue', {}) or {}).get('image', {}) or {}
            return img.get('contentUrl')
    return None

def local_path_for(content_url):
    # content_url like /documents/44618/1868699/Name.jpg/uuid?version=...
    # strip query, map to site dir. Keep the path up to the filename (drop the trailing /uuid).
    path = content_url.split('?', 1)[0]
    # Liferay doc URL: /documents/<group>/<id>/<filename>/<uuid>
    # the servable static file in the mirror is /documents/<group>/<id>/<filename>
    parts = path.split('/')
    # find filename (has an extension) — keep up to and including it
    keep = []
    for seg in parts:
        keep.append(seg)
        if re.search(r'\.(jpg|jpeg|png|gif|webp)$', seg, re.I):
            break
    rel = '/'.join(keep).lstrip('/')
    # On-disk convention (matches existing mirror): '+' kept literal for spaces,
    # percent-escapes decoded (e.g. %281%29 -> (1) ). unquote() would turn '+' into
    # ' ', so protect '+' first.
    rel = rel.replace('+', '\x00PLUS\x00')
    rel = urllib.parse.unquote(rel)
    rel = rel.replace('\x00PLUS\x00', '+')
    return rel  # relative to SITE_DIR

def download(content_url, dest_rel):
    dest = os.path.join(SITE_DIR, dest_rel)
    if os.path.exists(dest):
        return 'exists'
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    url = BASE + content_url  # full URL incl query for the actual bytes
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(dest, 'wb').write(data)
        return 'downloaded'
    except Exception as e:
        print(f"  ! download fail {dest_rel}: {e}", file=sys.stderr)
        return 'failed'

records = json.load(open(DATA))
set_cover = 0; dl = 0; exists = 0; nocover = 0; fail = 0
for i, r in enumerate(records):
    if (r.get('cover') or '').strip():
        continue  # idempotent
    cu = fetch_cover(r['slug'])
    if not cu:
        nocover += 1
        continue
    rel = local_path_for(cu)
    # cover path we store is the servable static path (no query, url-decoded to match mirror)
    r['cover'] = '/' + rel
    set_cover += 1
    status = download(cu, rel)
    if status == 'downloaded': dl += 1
    elif status == 'exists': exists += 1
    else: fail += 1
    if (i + 1) % 25 == 0:
        print(f"  {i+1}/{len(records)}  cover_set={set_cover} dl={dl} exists={exists} nocover={nocover} fail={fail}")
    time.sleep(0.25)

json.dump(records, open(DATA, "w"), ensure_ascii=False, indent=1)
print(f"\nDONE: cover set on {set_cover} records | images downloaded {dl}, already-present {exists}, "
      f"no-cover {nocover}, download-fail {fail}. news.json updated ({len(records)} records).")
