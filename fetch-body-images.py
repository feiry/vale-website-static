#!/usr/bin/env python3
"""
Download inline body images referenced inside article HTML (news.json bodies).
These use the Liferay friendly form /documents/d/guest/<name> (which serves the
image bytes on vale.com) but were never in the mirror, so they 404 as broken
placeholders in article pages.

Fetch each unique /documents/d/guest/ src from vale.com and save it at the EXACT
same path under site/vale.com/ so the existing HTML src resolves. Idempotent:
skips files already on disk. Records failures. Leaves external (http) srcs alone.
"""
import json, re, os, sys, time, urllib.request, urllib.parse

BASE = "https://vale.com"
UA = "Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
SITE_DIR = "site/vale.com"

d = json.load(open("site-data/news.json"))
srcs = set()
for r in d:
    for lang in ("en", "id"):
        body = r[lang]["body"] or ""
        for m in re.findall(r'<img[^>]+src="([^"]+)"', body):
            srcs.add(m)

guest = sorted(s for s in srcs if s.startswith("/documents/d/guest/"))
print(f"unique /documents/d/guest/ body images: {len(guest)}")

dl = 0; exists = 0; fail = 0
failed = []
for i, s in enumerate(guest):
    dest = os.path.join(SITE_DIR, s.lstrip("/"))
    if os.path.exists(dest):
        exists += 1
        continue
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    # request the encoded URL; server serves the image bytes
    url = BASE + urllib.parse.quote(s)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    ok = False
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as rsp:
                ct = rsp.headers.get("Content-Type", "")
                data = rsp.read()
            if not ct.startswith("image/") or len(data) < 100:
                raise ValueError(f"not an image (ct={ct}, {len(data)}B)")
            open(dest, "wb").write(data)
            ok = True
            break
        except Exception as e:
            if attempt == 2:
                print(f"  ! fail {s}: {e}", file=sys.stderr)
    if ok: dl += 1
    else:  fail += 1; failed.append(s)
    if (i + 1) % 40 == 0:
        print(f"  {i+1}/{len(guest)}  dl={dl} exists={exists} fail={fail}")
    time.sleep(0.2)

print(f"\nDONE: downloaded {dl}, already-present {exists}, failed {fail}.")
if failed:
    open("/private/tmp/body-images-failed.txt", "w").write("\n".join(failed) + "\n")
    print("failures written to /private/tmp/body-images-failed.txt")
