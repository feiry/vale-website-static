#!/usr/bin/env python3
"""
Fix ALL broken /in/w/<slug> (legacy ID) links mirror-wide. Our generated ID articles
live at /in/indonesia/w/<slug>.html, but ID pages link via the legacy /in/w/<slug>
form (and EN pages sometimes via /w/<slug>). Rewrite each:
  - slug present in site-data/news.json  -> /in/indonesia/w/<slug>.html
  - slug absent (removed/renamed at source) -> /in/indonesia/all-news.html
Idempotent; only rewrites links that currently resolve to nothing on disk.
"""
import re, os, json, glob, sys

ROOT = "site/vale.com"
data_slugs = {r['slug'] for r in json.load(open('site-data/news.json'))}

# match href="/in/w/<slug>(optional /-/categories/N)" — slug is any non-slash-until /-/
LINK = re.compile(r'href="/in/w/([^"/]+)(?:/-/categories/\d*)?"')

def exists(rel):
    p = os.path.join(ROOT, rel.lstrip('/'))
    return os.path.exists(p) or os.path.exists(p + '.html')

changed_files = 0
rew_article = 0
rew_allnews = 0
absent_seen = set()

for fp in glob.glob(f"{ROOT}/**/*.html", recursive=True):
    html = open(fp, encoding="utf-8", errors="replace").read()
    orig = html
    def _sub(m):
        global rew_article, rew_allnews
        slug = m.group(1)
        target = f"/in/indonesia/w/{slug}.html"
        # only rewrite if the current link is actually broken (target-agnostic: /in/w/<slug> never resolves)
        if slug in data_slugs and exists(f"/in/indonesia/w/{slug}"):
            rew_article += 1
            return f'href="{target}"'
        else:
            absent_seen.add(slug)
            rew_allnews += 1
            return 'href="/in/indonesia/all-news.html"'
    html = LINK.sub(_sub, html)
    if html != orig:
        open(fp, "w", encoding="utf-8").write(html)
        changed_files += 1

print(f"DONE: {rew_article} -> ID article, {rew_allnews} -> ID all-news, across {changed_files} files.")
print(f"absent (redirected to all-news) unique slugs: {len(absent_seen)}")
for s in sorted(absent_seen):
    print("  -", s)
