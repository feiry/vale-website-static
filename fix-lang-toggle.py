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

# Some pages have INDONESIAN-named files under BOTH /indonesia/ and /in/indonesia/
# but their real ENGLISH page has a different (English) name. Prefix-swapping alone
# links Indonesian→Indonesian (URL changes, content stays ID — Peter's 2026-08-06
# audit). This explicit map pairs each Indonesian slug with its English twin so both
# directions resolve to the correctly-languaged page.
ID_EN_TWINS = {
    "operasi-kami": "our-operations",
    "direksi": "board-of-directors",
    "dewan-komisaris": "board-of-commisioners",
    "komite": "committees",
    "kebijakan-tata-kelola-perusahaan": "corporate-governance-policy",
    "manajemen-risiko": "risk-management",
    "sistem-pelaporan-pelanggaran": "whistleblowing-system",
    "rehabilitasi-pascatambang": "post-mining-rehabilitation",
    "keanekaragaman-hayati": "biodiversity",
    "taman-kehati-sawerigading-wallacea": "sawerigading-wallacea-biodiversity-park",
    "air-dan-limbah-cair": "water-and-effluent",
    "emisi": "emission",
    "limbah": "waste",
    "talenta-kami": "our-people",
    "keberagaman-kesetaraan-inklusi": "diversity-equity-inclusion",
    "kesehatan-dan-keselamatan-kerja": "occupational-health-and-safety",
    "hak-asasi-manusia": "human-rights",
    "komunitas": "community",
    "program-pengembangan-masyarakat": "social-development-program",
    "tata-kelola-esg": "esg-governance",
    "strategi-esg": "esg-strategy",
    "manajemen-risiko-esg": "esg-risk-management",
}

_NAV_RE = re.compile(r'(<nav[^>]*vale-widget-seletor-pt-en[^>]*>)([\s\S]*?)(</nav>)')
_HAS_ANC = re.compile(r'<a\b[^>]*\bhref="[^"]*"')

def _set_pill(html, target, label):
    m = _NAV_RE.search(html)
    if not m:
        return html, False
    inner = m.group(2)
    if _HAS_ANC.search(inner):
        inner = re.sub(r'(<a\b[^>]*\bhref=")[^"]*(")', r'\g<1>' + target + r'\g<2>', inner, count=1)
    else:
        inner = (f'<a href="{target}" class="lang-sel-link lang-sel-btn font-weight-medium '
                 f'texto-sm" aria-label="{label}"><span>{label}</span></a>')
    return html[:m.start()] + m.group(1) + inner + m.group(3) + html[m.end():], True

def fix_id_en_twins():
    """Point Indonesian-named pages (under both prefixes) at their English twin, and
    the English twin back at the Indonesian page. Both must exist."""
    fixed = 0
    for idslug, enslug in ID_EN_TWINS.items():
        en_target = f"/indonesia/{enslug}.html"
        if not os.path.isfile(os.path.join(SITE_ROOT, en_target.lstrip("/"))):
            continue
        # ID-content pages (both prefixes) → EN twin
        for rel in (f"indonesia/{idslug}.html", f"in/indonesia/{idslug}.html"):
            p = os.path.join(SITE_ROOT, rel)
            if not os.path.isfile(p):
                continue
            html = open(p, encoding="utf-8").read()
            new, ok = _set_pill(html, en_target, "EN")
            if ok and new != html:
                open(p, "w", encoding="utf-8").write(new)
                fixed += 1
        # EN twin → ID page (prefer /in/ prefix)
        id_target = f"/in/indonesia/{idslug}.html"
        if not os.path.isfile(os.path.join(SITE_ROOT, id_target.lstrip("/"))):
            id_target = f"/indonesia/{idslug}.html"
        p = os.path.join(SITE_ROOT, f"indonesia/{enslug}.html")
        html = open(p, encoding="utf-8").read()
        new, ok = _set_pill(html, id_target, "ID")
        if ok and new != html:
            open(p, "w", encoding="utf-8").write(new)
            fixed += 1
    print(f"Fixed ID↔EN twin toggles on {fixed} pages.")

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

    inject_en_pills(files)
    fix_id_en_twins()

# ─── Symmetric pass: inject an "ID" pill into EN pages ────────────────────────
# The EN chrome renders the language nav EMPTY (Liferay only emits the "switch to
# the OTHER language" link, uncaptured for an already-EN page), so EN pages have no
# pill. Each ID page's (now static) EN pill tells us that page's EN counterpart —
# invert it to get EN→ID, then inject an ID pill into the matching empty EN nav.
# EN pages with no ID counterpart are correctly left pill-less.
_NAV_RE = re.compile(r'(<nav[^>]*vale-widget-seletor-pt-en[^>]*>)([\s\S]*?)(</nav>)')
_HAS_ANC = re.compile(r'<a\b[^>]*\bhref="[^"]*"')
_HREF = re.compile(r'<a\b[^>]*\bhref="([^"]*)"')

def inject_en_pills(files):
    # Build EN→ID from ID pages' EN pills.
    en_to_id = {}
    for path in files:
        rel = os.path.relpath(path, SITE_ROOT)
        if not rel.startswith("in/") or "/w/" in rel:
            continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        m = _NAV_RE.search(html)
        if not m:
            continue
        hm = _HREF.search(m.group(2))
        if hm and not hm.group(1).startswith("/c/portal"):
            en_to_id[hm.group(1).lstrip("/")] = "/" + rel

    injected = pill_less = 0
    for path in files:
        rel = os.path.relpath(path, SITE_ROOT)
        if rel.startswith("in/") or "/w/" in rel:
            continue
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        m = _NAV_RE.search(html)
        if not m or _HAS_ANC.search(m.group(2)):
            continue  # not present, or already has a pill
        target = en_to_id.get(rel)
        if not target or not os.path.isfile(os.path.join(SITE_ROOT, target.lstrip("/"))):
            pill_less += 1
            continue  # English-only page — correctly no pill
        pill = (f'<a href="{target}" class="lang-sel-link lang-sel-btn '
                f'font-weight-medium texto-sm" aria-label="ID"><span>ID</span></a>')
        new = html[:m.start()] + m.group(1) + pill + m.group(3) + html[m.end():]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
        injected += 1
    print(f"Injected ID pill into {injected} EN pages; {pill_less} left pill-less (no ID version).")

if __name__ == "__main__":
    main()
