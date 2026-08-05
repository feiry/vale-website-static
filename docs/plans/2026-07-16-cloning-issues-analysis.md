# Vale Cloning-Issues Verification — Analysis & Fix Plan

**Source:** `Website Sitemap - update-cloning-issues.xlsx` (Rohman/Sri, 2026-07-16), 2 sheets: Cloning Issues (ID) 84 rows, Cloning Issues (EN) 85 rows. Meeting held 2026-07-16 15:30.
**How Vale tested:** by clicking through the site NAVIGATION (not typing ID URLs directly). This is the key to interpreting the findings.

## TL;DR
The **pages themselves are correct** (EN 83/83 en-US, ID 83/83 in-ID — re-verified live). Almost every finding traces to **internal navigation links**, not missing/wrong content. One root cause dominates the ID sheet; a handful of genuine 404s and source-content issues remain.

---

## ROOT CAUSE #1 — ID pages navigate to English (drives ~62 ID findings)
**Finding:** "Mengarah ke laman Bahasa Inggris (EN)" on 62 ID pages.
**Verified:** ID home page (`/in/indonesia.html`) has **103 links to `/indonesia/` (EN)** and **0 links to `/in/indonesia/`**. Every ID page's nav menu points to English. Clicking any ID nav item lands on EN.
**Why:** Liferay renders ID pages with EN-canonical URLs in nav/body. Our `postprocess-bilingual.sh` preserved `/in/` and stripped foreign locales, but never *rewrote bare `/indonesia/` links to `/in/indonesia/` on ID pages*.
**Fix (ours):** add a postprocess pass that, ON ID PAGES ONLY (files under `vale.com/in/indonesia/`), rewrites internal `href="/indonesia/..."` → `href="/in/indonesia/..."` (and `/indonesia.html` → `/in/indonesia.html`). Guard: only rewrite links whose ID target actually exists; leave EN-only pages (5 known) pointing to EN. Re-deploy. **This single fix clears the majority of the ID sheet.**

## ROOT CAUSE #2 — Root-level pages (Morowali/Pomalaa) path mismatch (genuine 404)
**Finding:** IGP Morowali, IGP Pomalaa → 404 (both EN + ID).
**Verified:** spec URLs are `vale.com/indonesia-growth-project-morowali` (at DOMAIN ROOT, not under /indonesia/). Files deployed correctly to `/indonesia-growth-project-morowali.html` (root). But nav links point to `/indonesia/indonesia-growth-project-morowali.html` → 404.
**Fix (ours):** rewrite nav links to the root-level path, OR (cleaner) also place copies under `/indonesia/` and `/in/indonesia/` to match the link structure. Decide in fix phase.

## ROOT CAUSE #3 — Internal-link 404s from uncloned/renamed targets
**Findings:** Sorowako, PPM/PPMSDP, Investors sub-pages, Sustainability→(Environment/Social/Operations), Biodiversity→(Rehab/Sawerigading), SR Report 2024, ESG→SR Report.
**Likely cause:** links to slugs that either (a) weren't in the 166-URL scope, (b) use a different slug than the cloned file, or (c) are depth-2 pages beyond our crawl. `ppm.html` exists (200) but `ppmsdp.html` link 404s — slug mismatch. Needs per-link verification in fix phase.
**Fix (ours, mostly):** map each broken link to its real cloned file and rewrite; for genuinely out-of-scope targets, confirm with Vale whether to add to scope.

## VALE-SIDE ITEMS (not our cloning bugs — source content)
- **"Refresh photo (New CEO)"** (Governance), **"Refresh official photo Komisaris"** (Board of Commissioners) — live source has old photos; our clone mirrored faithfully. Vale updates source, we re-clone those pages.
- **"Obsolete Purpose and Values"** (OHS), **"Obsolete data"** (Community) — stale source content. Vale's to refresh.
- **"Library document not loading (Vale global library)"** (Documents & Reports) — documents hosted on Vale's INTERNAL global server (same limitation as News). Not cloneable from public site; needs Vale to provide the files or a decision.
- **YouTube video broken link** (Post-mining) — external embed; check if source link is dead (may be Vale-side).

## Response strategy to Vale
1. Acknowledge findings, thank them for the thorough nav-based check.
2. Clarify the ID pages ARE correct Bahasa — issue is internal nav links (root cause #1), which we'll fix so the ID site navigates within Bahasa.
3. Commit to fixing #1, #2, #3 (our side); give ETA.
4. Separate out the Vale-side items (content refresh, internal-library docs) — ask Vale to action or decide.
5. Note we'll update the shared SharePoint issues file with status per row.

## Fix sequencing
1. **Root cause #1** (ID nav → /in/) — biggest impact, one postprocess pass.
2. **Root cause #2** (Morowali/Pomalaa paths).
3. **Root cause #3** (per-link 404 mapping) — verify each, rewrite.
4. Re-deploy to dev, re-verify by NAVIGATION (not just URL), update SharePoint file.
5. Vale-side items tracked separately.

## FIXES APPLIED (2026-07-06, on working site/)
- **RC#1 (ID nav → Bahasa):** built EN→ID slug map (65/75 slugs DIFFER) from sitemap. `fix-id-nav-links.py` rewrote ID-page links: `/indonesia/<en-slug>` → `/in/indonesia/<id-slug>` (translated) + `/indonesia/<id-slug>` → `/in/indonesia/<id-slug>` (prefix). **72 ID files edited. ID home: 103 EN-links/0 ID → 10/93. 8246 ID-page /in/ links now resolve, 0 broken.** ✅
- **RC#2 (Morowali/Pomalaa root pages):** these live at vale.com ROOT (`/indonesia-growth-project-morowali`), not under /indonesia/. Fixed: appended `.html` (36 links lacked it) + corrected language prefix (EN pages linked `/in/` versions). 11 files. ✅
- **RC#3 (internal-link 404s):** systematic scan found 21 broken → fixed 13 via reverse ID→EN slug remap on EN pages (11), double-path bug `/indonesia/indonesia/` (2 files), doc-link path (`/indonesia/documents/` → `/documents/`, strip spurious .html). Final cross-prefix pass (37 files) using file-existence as guide. **21 → 8 remaining.** ✅

## RESIDUAL 8 broken links — NOT our bugs (for Vale)
- **Broken on live vale.com source too** (we mirrored faithfully): `anti-corruption-program`, `program-anti-korupsi`, `annual-and-sustainability-reports` — all 404 on live vale.com.
- **Out-of-scope live pages** (200 live, but NOT in the 166-URL spec): `esg/kinerja-esg` (ESG Performance), `esg/peringkat-esg-kami` (ESG Ratings), `esg/kabar-terkini-esg` (ESG Updates), `indonesia-growth-projects` (IGP parent, EN+ID). → Vale decides: add to scope or accept.

## Vale-side content items (unchanged — their action)
Photo refresh (New CEO, Komisaris), Obsolete Purpose/Values & data, Vale-global-library documents (Docs & Reports), YouTube broken embed.

## Status
Fixes applied to working site/. NEXT: re-deploy to Azure dev, then Peter QA (click-through navigation both languages) BEFORE informing Vale.
