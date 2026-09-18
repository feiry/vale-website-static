#!/usr/bin/env python3
"""
Export Vale News + Document Library data via Liferay Headless REST APIs.

Exports EVERYTHING (all categories) so Vale can validate/filter — nothing dropped.
Each record is tagged with its category so Vale can slice by "Indonesia"/"Indonesia news"/etc.

Outputs (under ./vale-export/):
  news.json          - all articles, full fields, per language merged
  news.csv           - flat index (title EN/ID, date, categories, slug, url)
  articles/<slug>-<lang>.html - full body per article per language
  documents.json     - all documents metadata
  documents.csv      - flat index (title, type, size, date, category, download url)
  (document files themselves are already in site/vale.com/documents/)

Public no-auth Liferay Headless APIs on vale.com. Site/group 44618.
"""
import json, csv, re, os, time, urllib.request, urllib.parse, sys

BASE = "https://vale.com"
SITE = "44618"
UA = "Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
OUT = "vale-export"
# Indonesia-news content-structure id. The structured-contents endpoint returns
# only a SCOPED 415-item view by default; adding flatten=true unscopes it to the
# full collection (3208 site-wide), and filtering to this structure yields the
# complete 995 Indonesia-news set. Without flatten=true ~580 articles are silently
# hidden — this was the cause of the 2026-08 "134 missing CSV articles" gap.
NEWS_STRUCTURE_ID = "62668"
DOC_FOLDERS = ["337618"]  # library folder; extend if more discovered

os.makedirs(OUT, exist_ok=True)
os.makedirs(f"{OUT}/articles", exist_ok=True)

def api(path, lang=None, retries=3):
    url = BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    if lang:
        req.add_header("Accept-Language", lang)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except Exception as e:
            if i == retries - 1:
                print(f"  ! failed {path} ({lang}): {e}", file=sys.stderr)
                return None
            time.sleep(2)

def fetch_all(path_tmpl, lang=None, page_size=100):
    """Paginate a headless collection endpoint; return list of items."""
    items, page = [], 1
    while True:
        sep = '&' if '?' in path_tmpl else '?'
        d = api(f"{path_tmpl}{sep}page={page}&pageSize={page_size}", lang=lang)
        if not d or not d.get('items'):
            break
        items.extend(d['items'])
        total = d.get('totalCount', 0)
        if len(items) >= total or len(d['items']) < page_size:
            break
        page += 1
        time.sleep(0.5)
    return items

def cf_map(article):
    """Flatten contentFields to name->value."""
    out = {}
    for f in article.get('contentFields', []):
        v = f.get('contentFieldValue', {})
        out[f['name']] = v.get('data', v.get('value', ''))
    return out

# ---------------- NEWS ----------------
# flatten=true is REQUIRED (see NEWS_STRUCTURE_ID note) — the default scoped view
# caps at 415 and hides ~580 Indonesia articles. Filter to the news structure so we
# get the full 995-article Indonesia set, not the 3208 site-wide global superset.
_news_filter = urllib.parse.quote(f"contentStructureId eq {NEWS_STRUCTURE_ID}")
NEWS_PATH = (f"/o/headless-delivery/v1.0/sites/{SITE}/structured-contents"
             f"?flatten=true&filter={_news_filter}")
print(">>> NEWS: fetching EN...")
news_en = fetch_all(NEWS_PATH, lang="en-US")
print(f"    EN articles: {len(news_en)}")
print(">>> NEWS: fetching ID...")
news_id = fetch_all(NEWS_PATH, lang="in-ID")
print(f"    ID articles: {len(news_id)}")

id_by_id = {a['id']: a for a in news_id}
records = []
for a in news_en:
    aid = a['id']
    en_cf = cf_map(a)
    idv = id_by_id.get(aid)
    id_cf = cf_map(idv) if idv else {}
    cats = [c.get('taxonomyCategoryName') for c in a.get('taxonomyCategoryBriefs', []) if c.get('taxonomyCategoryName')]
    rec = {
        'id': aid,
        'slug': a.get('friendlyUrlPath', ''),
        'title_en': a.get('title', ''),
        'title_id': idv.get('title', '') if idv else '',
        'date': en_cf.get('data', ''),
        'subtitle_en': en_cf.get('subtitulo', ''),
        'subtitle_id': id_cf.get('subtitulo', ''),
        'categories': cats,
        'languages': a.get('availableLanguages', []),
        'dateModified': a.get('dateModified', ''),
        'body_en': en_cf.get('conteudo', ''),
        'body_id': id_cf.get('conteudo', ''),
    }
    records.append(rec)
    # write body files (sanitize slug for filesystem)
    slug = re.sub(r'[^a-z0-9-]', '-', (rec['slug'] or str(aid)).lower())[:120]
    if rec['body_en']:
        open(f"{OUT}/articles/{slug}-en.html", "w").write(f"<h1>{rec['title_en']}</h1>\n{rec['body_en']}")
    if rec['body_id']:
        open(f"{OUT}/articles/{slug}-id.html", "w").write(f"<h1>{rec['title_id']}</h1>\n{rec['body_id']}")

json.dump(records, open(f"{OUT}/news.json", "w"), ensure_ascii=False, indent=1)
with open(f"{OUT}/news.csv", "w", newline='') as f:
    w = csv.writer(f)
    w.writerow(['id', 'date', 'title_en', 'title_id', 'categories', 'slug', 'languages', 'url_en'])
    for r in records:
        w.writerow([r['id'], r['date'][:10], r['title_en'], r['title_id'],
                    '; '.join(r['categories']), r['slug'], '; '.join(r['languages']),
                    f"{BASE}/indonesia/w/{r['slug']}"])
print(f">>> NEWS done: {len(records)} articles -> news.json, news.csv, articles/")

# ---------------- DOCUMENTS ----------------
print(">>> DOCUMENTS: fetching...")
docs = []
for folder in DOC_FOLDERS:
    docs += fetch_all(f"/o/headless-delivery/v1.0/document-folders/{folder}/documents")
print(f"    documents: {len(docs)}")
drecs = []
for d in docs:
    cats = [c.get('taxonomyCategoryName') for c in d.get('taxonomyCategoryBriefs', []) if c.get('taxonomyCategoryName')]
    drecs.append({
        'id': d.get('id'), 'title': d.get('title', ''), 'fileName': d.get('fileName', ''),
        'ext': d.get('fileExtension', ''), 'sizeBytes': d.get('sizeInBytes', 0),
        'dateModified': d.get('dateModified', ''), 'categories': cats,
        'description': d.get('description', ''), 'contentUrl': d.get('contentUrl', ''),
    })
json.dump(drecs, open(f"{OUT}/documents.json", "w"), ensure_ascii=False, indent=1)
with open(f"{OUT}/documents.csv", "w", newline='') as f:
    w = csv.writer(f)
    w.writerow(['id', 'title', 'fileName', 'ext', 'sizeBytes', 'dateModified', 'categories', 'downloadUrl'])
    for r in drecs:
        w.writerow([r['id'], r['title'], r['fileName'], r['ext'], r['sizeBytes'],
                    r['dateModified'][:10], '; '.join(r['categories']), BASE + r['contentUrl']])
print(f">>> DOCUMENTS done: {len(drecs)} -> documents.json, documents.csv")
print("\nEXPORT COMPLETE ->", OUT)
