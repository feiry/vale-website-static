# Plan: Vale Updated Sitemap (Maman Tjokke, 2026-09-01)

Source: `Website-Sitemap-cloning-issues-2026-09-01.xlsx` (6 sheets) emailed by M.A.H. Tjokke,
thread "Koordinasi Cloning: [Placeholder] Diskusi Implementasi Static Website".
Scope is MUCH larger than Peter's comparison report. Status as of 2026-09-02: nothing below started.

---

---
## ✅ BUCKET 1 CLOSED (2026-09-02)
Full sweep of all 70 Vale-flagged pages: 68 already OK (stale audit — Peter+earlier fixes).
Fixed this session: 14 EN-button 404s (update_language → static twin, my re-clone regression,
postprocess §7b patched) + 2 missing-toggle EN pages (our-organization, esg/labor-union — injected
ID button into empty seletor nav). 0 lang-routing issues remaining. All verified live (target 200).
NOTE: Vale's "62 points-to-English" was a stale-audit overcount — actual open work was 16 pages, not 62.

## Bucket 1 — 🔴 Language routing (ORIGINAL ANALYSIS BELOW) ("Mengarah ke laman Bahasa Inggris") — HIGHEST IMPACT
**62 of 83 ID pages flagged.** Diagnosis (verified on Tentang page):
- Pages themselves render correctly in Indonesian (`lang="in-ID"`) when opened directly. ✓
- Lang-toggle (EN/ID button) is correct (`update_language?redirect=/in/indonesia/...`). ✓
- BUT ~14 nav/menu links per ID page point to `/indonesia/` (EN path) instead of `/in/indonesia/` (ID).
  (83 correct ID links vs 14 wrong EN links on the sample page.)
- ROOT CAUSE HYPOTHESIS: specific menu items (likely the ones whose EN slug differs from ID,
  or sub-nav links) were never rewritten from EN to ID path during postprocess.
- ALSO: 2 internal-link 404s (Sorowako, Pomalaa ops), 1 footer link → EN, 3 "URL ID terlewat".

**Fix approach (proposed):** site-wide sed/script pass rewriting the specific wrong `/indonesia/<slug>`
nav links → `/in/indonesia/<slug>` on ID pages ONLY (must NOT touch EN pages, must NOT break the
lang-toggle which legitimately references the EN path). Identify the exact 14 link patterns first,
then batch-fix + verify with the same click-QA approach. Est: 1 investigation pass + 1 script + redeploy.
RISK: getting the ID↔EN slug mapping right (some slugs differ: our-organization/struktur-organisasi etc).

## Bucket 2 — 🔄 "Content updated - re-clone" (17 pages) — 9 DONE, 8 REMAIN
DONE this session (Peter report): Beranda, Tentang, Struktur Org, Operasi Kami, Kebijakan Kami,
Towuti, Pengaduan, Beasiswa, Kerja Praktik, Tahapan Perekrutan.
**REMAINING 8 (re-clone via proven pipeline):**
1. Sorowako — operasi-kami-di-sorowako  (also has 404 internal link)
2. Morowali — morowali
3. Pomalaa — indonesia-growth-projects-pomalaa  (also 404 internal link)
4. Sorlim — igp-sorowako-limonite
5. IGP Tanamalia — tanamalia-project
6. Karier — karier-di-pt-vale  (NOTE: ties into Task #10 slug decision — live label "Peluang Karir", live /career 403)
7. Life at PTVI — life-at-pt-vale-indonesia
(Recruitment Stages = tahapan-perekrutan already done.)
Est: same as the 12-file re-clone round — ~fetch+postprocess+assets+CSS+deploy, ~30-45 min.

## Bucket 3 — 🆕 "New content - to clone" (10 pages) — RECONCILE FIRST, not all net-new
⚠️ Several OVERLAP with pages we already have under DIFFERENT slugs:
- "Biodiversity" (/biodiversity) ≈ we have keanekaragaman-hayati.html
- "DEI" (/keberagaman-kesetaraan-dan-inklusi) ≈ we have keberagaman-kesetaraan-inklusi.html
- "Site Closure & Rehab" (/penutupan-tambang-dan-rehabilitasi) ≈ we have rehabilitasi-pascatambang.html
- "Water & Effluents" (/manajemen-air-dan-efluen) ≈ we have air-dan-limbah-cair.html
- "Waste Mgmt B3" (/pengelolaan-limbah-b3-dan-non-b3) ≈ we have limbah.html
- "Emissions & Energy" (/pengelolaan-emisi-dan-energi) ≈ we have emisi.html
GENUINELY NEW (no existing equivalent found):
- Residue/Tailings (/pengelolaan-residu-tailing)
- Resettlement (/relokasi)
- OHS (no ID URL given)
- GCG/Integritas Bisnis (/integritas-bisnis)
ACTION: reconcile each — is Vale RENAMING slugs (new ESG taxonomy) or adding NET-NEW pages?
Likely a sustainability-section restructure. Needs a mapping decision with Vale before cloning,
else we'll create duplicates. Est: reconciliation pass + clone the genuinely-new + rename/redirect others.

## Bucket 4 — 🏷️ Meta-tag (News + Dynamic News)
"Content updated - re-create using new meta tag" / "update follow the new meta tag".
News pages need rebuilding with a new meta-tag structure. Relates to build-news.py.
Ties to Peter's earlier News Recreation work. Est: clarify the "new meta tag" spec with Vale first.

## Bucket 5 — ⚠️ Misc flagged (EN sheet)
- "Refresh photo (New CEO)" + "Refresh official photo Komisaris" → Direksi/Dewan Komisaris new photos
- "Obsolete Purpose and Values" / "Obsolete data" (EN pages)
- Youtube video broken link
- Cookie popup issue: "Setiap page hasil cloning mengaktifkan popup cookie" (Tjokke) — every cloned
  page triggers a cookie popup. May need OneTrust/cookie-banner neutralization (postprocess §5 related).
- Several EN sub-page 404s + "All internal links to sub-page 404" on some pages.

---

## Recommended sequencing
1. **Bucket 1 (lang-routing)** — highest impact, affects 62 pages, likely one scripted fix. Do first.
2. **Bucket 2 (8 re-clones)** — mechanical, proven pipeline, unblocks the operations section.
3. **Bucket 5 misc** — quick wins (CEO/Komisaris photos, cookie popup, obsolete data).
4. **Bucket 3 (new/reconcile)** — needs a Vale mapping decision (rename vs new) before cloning.
5. **Bucket 4 (meta-tag News)** — needs the "new meta tag" spec from Vale.

DECISIONS NEEDED FROM VALE/FEIRY before Buckets 3 & 4:
- Bucket 3: are these slug renames or net-new pages? (avoid duplicates)
- Bucket 4: what is the "new meta tag" structure for News?
- Task #10 (still open): Karier/Komunitas/Kehati slug parity — overlaps Bucket 2 (Karier) & 3.
