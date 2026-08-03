#!/usr/bin/env python3
"""fix-lang-toggle.py — repoint the header EN/ID language pill to static pages.

The Vale chrome header carries a Liferay language switcher
(<nav class="vale-widget-seletor-pt-en">) whose links use the DYNAMIC endpoint
    /c/portal/update_language?p_l_id=…&redirect=<current-path>&languageId=<lang>
That endpoint only exists on a live Liferay server → 404 on our static host.

This rewrites each such <a href> to a DIRECT static link to the other-language
page. The mapping is deterministic for pages that differ only by the /in/ prefix
(news + most chrome). Pages whose EN/ID FILENAMES differ (e.g.
documents-and-reports.html vs dokumen-dan-laporan.html) don't prefix-resolve —
those toggles are LEFT UNTOUCHED and reported, to be handled with an explicit map.

Idempotent: only rewrites hrefs still pointing at /c/portal/update_language.
Run from repo root: python3 fix-lang-toggle.py
"""
import os, re, sys
from urllib.parse import unquote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_ROOT = os.path.join(SCRIPT_DIR, "site", "vale.com")

# href="/c/portal/update_language?...redirect=<PATH>&...languageId=<lang>..."
TOGGLE_RE = re.compile(
    r'href="(/c/portal/update_language\?[^"]*)"'
)

def parse_params(qs):
    """Extract redirect + languageId from the (html-escaped) query string."""
    qs = qs.replace("&amp;", "&")
    redirect = re.search(r'redirect=([^&]*)', qs)
    lang = re.search(r'languageId=([a-z_]+)', qs)
    return (unquote(redirect.group(1)) if redirect else None,
            lang.group(1) if lang else None)

def static_target(redirect, lang_id):
    """Static .html path for the other-language version of `redirect`, or None
    if it can't be resolved by prefix-swapping to an existing file."""
    if not redirect or not lang_id:
        return None
    r = redirect.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    to_en = lang_id.startswith("en")
    if to_en:
        if r.startswith("/in/"):
            r = "/" + r[len("/in/"):]
        elif r == "/in":
            r = ""
        # else already an EN path (EN page toggling — unusual)
    else:  # switch TO id (pt_/id_)
        if not r.startswith("/in"):
            r = "/in" + r
    target = (r or "/indonesia") + ".html"
    return target if os.path.isfile(os.path.join(SITE_ROOT, target.lstrip("/"))) else None

def main():
    files = []
    for dp, _, fns in os.walk(SITE_ROOT):
        for fn in fns:
            if fn.endswith(".html"):
                files.append(os.path.join(dp, fn))

    fixed_files = 0
    fixed_links = 0
    unresolved = {}  # target-redirect → count (filename-mismatch, left untouched)

    for path in files:
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        if "/c/portal/update_language" not in html:
            continue

        changed = False
        def repl(m):
            nonlocal changed, fixed_links
            redirect, lang_id = parse_params(m.group(1))
            target = static_target(redirect, lang_id)
            if target:
                changed = True
                fixed_links += 1
                return f'href="{target}"'
            unresolved[redirect] = unresolved.get(redirect, 0) + 1
            return m.group(0)  # leave untouched

        new_html = TOGGLE_RE.sub(repl, html)
        if changed and new_html != html:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_html)
            fixed_files += 1

    print(f"Rewrote {fixed_links} lang-toggle links across {fixed_files} files.")
    if unresolved:
        print(f"\n{len(unresolved)} toggle target(s) left UNTOUCHED "
              f"(EN/ID filename differs — needs explicit map):")
        for red, n in sorted(unresolved.items()):
            print(f"  {n:3d}x  redirect={red}")

if __name__ == "__main__":
    main()
