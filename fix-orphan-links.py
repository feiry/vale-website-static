#!/usr/bin/env python3
"""
Repoint the 10 dead /w/ orphan links (articles removed/renamed on vale.com itself,
confirmed 404 at source) to the correct current static article page where one exists,
otherwise to the all-news listing. Idempotent: only rewrites the exact dead slugs.

EN pages get EN targets (/indonesia/w/... or /indonesia/all-news.html);
ID pages get ID targets (/in/indonesia/w/... or /in/indonesia/all-news.html).
"""
import re, os, sys

ROOT = "site/vale.com"

# dead slug -> replacement target SLUG (an article we generate) or None for all-news
SUBROTO = "winning-2025-subroto-award-for-matano-iniaku-program-pt-vale-indonesia-demonstrates-sustainable-mining-that-revitalizes-nature-and-communities"
TOWUTI_WATER = "commitment-to-towuti-s-environment-and-community-pt-vale-affirms-water-safety-and-measured-recovery-progress"
TOWUTI_RECOVERY = "open-dialogue-with-local-communities-continues-pt-vale-and-east-luwu-government-strengthen-collaboration-in-towuti-s-recovery"

MAP = {
    "t-vale-raih-subroto-award-esdm-atas-komitmen-efisiensi-energi": SUBROTO,
    "commitment-to-towuti-s-environment-and-communities-pt-vale-confirms-water-quality-is-safe-and-recovery-progress-is-measurable": TOWUTI_WATER,
    "commitment-to-collective-recovery": TOWUTI_RECOVERY,
    "together-for-towuti-s-recovery-a-collaboration-between-government-community-and-pt-vale-for-shared-resilience-4": TOWUTI_RECOVERY,
    "tangani-krisis-pt-vale-apresiasi-sinergi-pemerintah-dan-masyarakat-dalam-penanganan-kebocoran-pipa-di-towuti": TOWUTI_RECOVERY,
    "local-residents-voluntarily-join-recovery-efforts": TOWUTI_RECOVERY,
    "gotong-royong-warga-bantu-pemulihan": TOWUTI_RECOVERY,
    "komitmen-pulih-bersama": TOWUTI_RECOVERY,
    "pt-vale-raih-penghargaan-padmamitra-award-kategori-kewirausahaan-di-forum-csr-indonesia": None,  # no current match -> all-news
    "dorong-pemberdayaan-dengan-meningkatkan-daya-saing-tenaga-kerja-lokal-pt-vale-dan-alkhairaat-gelar-peletakan-batu-pertama-welding-academy": None,
}

def target_href(dead_slug, is_id_page):
    tgt = MAP[dead_slug]
    if tgt is None:
        return ("/in/indonesia/all-news.html" if is_id_page else "/indonesia/all-news.html")
    return (f"/in/indonesia/w/{tgt}.html" if is_id_page else f"/indonesia/w/{tgt}.html")

# match href="/w/<slug>/-/categories/N" — tolerate optional prefixes (/indonesia, /in/indonesia,
# /in) and an OPTIONAL/empty categories number (/-/categories/ or /-/categories/5). The prefix marks
# whether the LINK is an ID link (/in...) independent of the page's own path.
patterns = {s: re.compile(r'href="(/in/indonesia|/indonesia|/in)?/w/' + re.escape(s) + r'(?:/-/categories/\d*)?"')
            for s in MAP}

changed_files = 0
total_subs = 0
for dirpath, _, files in os.walk(ROOT):
    for fn in files:
        if not fn.endswith(".html"):
            continue
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, ROOT)
        is_id = rel.startswith("in/") or rel.startswith("in\\") or "/in/" in ("/"+rel)
        try:
            html = open(fp, encoding="utf-8", errors="replace").read()
        except Exception as e:
            print(f"  ! read fail {fp}: {e}", file=sys.stderr); continue
        orig = html
        for s, pat in patterns.items():
            def _sub(m):
                global total_subs
                prefix = m.group(1) or ""
                # link is ID if the page is under /in/ OR the link prefix itself is /in...
                link_is_id = is_id or prefix.startswith("/in")
                total_subs += 1
                return f'href="{target_href(s, link_is_id)}"'
            html = pat.sub(_sub, html)
        if html != orig:
            open(fp, "w", encoding="utf-8").write(html)
            changed_files += 1
            print(f"  ~ {rel}")

print(f"\nDONE: {total_subs} link(s) rewritten across {changed_files} file(s).")
