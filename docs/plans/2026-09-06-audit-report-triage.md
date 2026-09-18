# Peter Audit Report v3 — Triage & Work Plan

**Source:** `docs/Laporan Audit Vale Indonesia (ID+EN).html` (Peter, 5–6 Sep 2026)
**Scope:** Full manual page-by-page audit of the deployed site (now `valeindonesia.com`, origin `stidstaticsiteprod`). Physically click-tested, not DOM-sampled.
**Total findings:** 97 raw. **ESG hub = OUT OF SCOPE (Feiry, 2026-09-06)** → ~24 findings dropped.
**In-scope (non-ESG):** ~51 findings + typos.

> ⚠️ **Key insight from Peter:** many bugs are **byte-identical to the old live vale.com** — they were cloned into our mirror. The old "live-vs-staging comparison" method could never catch them (both equally wrong). These are now on **our production**, so they ARE ours to fix if we choose. Others are genuine clone/build defects.

---

## Scope summary (non-ESG)

| Severity | Count | Nature |
|----------|-------|--------|
| 🔴 Kritis | 13 | Dead links / 404 / broken interaction / dead-end CTA |
| 🟠 Tinggi | 12 | Wrong data, untranslated ID pages, swapped docs |
| 🟡 Sedang | 22 | Translation gaps, duplicated text, leaked code/entities, stale domain |
| 🟢 Rendah | 4 | Cosmetic / UX |

---

## ⚡ Likely ALREADY FIXED — verify first (cheap wins)

These match work we already did or were noted "fixed" by Peter himself. **Re-verify before touching:**

| # | Finding | Why likely done |
|---|---------|-----------------|
| K6 | Doc Library filter "doesn't filter" | We REBUILT the Doc Library filter (Quarterly work). All News already confirmed fixed by Peter. **Re-verify our new chip filter actually filters.** |
| K3 (partial) | Taman Kehati "See our Map" English | We FIXED "See our Map"→"Lihat Peta Kami" (report v2). S5 duplicates this — verify deployed. |
| K4 / K11 / K13 | Kerja Praktik / Practical Work form "akan dibuka" but closed | Matches completed task #4 (registration window). **Verify current on-page text + Google Form state.** |
| S5 | "See our Map" untranslated | Same as above — already fixed. |

---

## 🔴 BATCH 1 — Critical dead links & broken interactions (13)

### Group 1A — Broken/malformed internal links (fixable by href correction)
| # | Page | Problem | Fix |
|---|------|---------|-----|
| K1 | `pemulihan-kebocoran-minyak-towuti.html` | 4/4 "Berita" news links → 404. URL pattern broken: `/in/w/...` (missing `indonesia`) + stray `/-/categories/5` | Rewrite hrefs to `/in/indonesia/w/<slug>.html`; verify each target exists |
| K10 | `towuti-oil-leakage-recovery.html` (EN) | 1 news href = **entire paragraph text** pasted (starts `http://The oil pipeline...`); 2 more 404 (missing `indonesia`/`/in/`) | Replace the 3 hrefs with correct article URLs |
| K5 | `sekretaris-perusahaan.html` | "Klik di sini untuk melihat Direksi" → `/indonesia/direksi.html` (stale orphan copy, Update Sep 2025) instead of `/in/indonesia/direksi.html` (active, May 2026) | Fix href to `/in/` version. **SYSTEMIC** — see T1/T5. |
| K7 | Footer (all pages) | 2 different "Accessibility" links; broken one = `/acessibilidade` (Portuguese spelling, global-template leftover) | Rewrite to `/in/accessibility`. Sitewide → postprocess candidate |
| K12 | `life-at-pt-vale-indonesia.html` (EN) | "#PTVIGreatPlaceToWork" link → 404 even with correct prefix; article never published | Point to valid article OR remove link (needs decision — target may not exist) |

### Group 1B — Missing/dead-end links (need a target or removal)
| # | Page | Problem | Fix |
|---|------|---------|-----|
| K2 | `pemasok.html` + `suppliers.html` + homepage EN | "unduh formulir pendaftaran **di sini**" = plain `<p>` text, NO `<a>`. (Also on live vale.com) | Add `<a>` to the registration form — **needs the form URL from COMMs** |
| K9 | `community.html` (EN, Social hub) | 4/4 "Find out more" links → `href="community.html"` (self, dead-end) | Needs correct targets (people/human-rights/OHS/social-dev). **Is this an ESG-hub page? → may be out of scope** |
| K3 | `jwpc.html` + `taman-kehati-...html` | Accordion left-side click blocked by decorative `<img class="wave">` overlay (shared component) | CSS/z-index fix on the wave overlay — **shared component, may affect many pages** |

### Group 1C — Stale/wrong content behind links
| # | Page | Problem | Fix |
|---|------|---------|-----|
| K8 | `general-meeting-of-shareholders.html` (EN) | 3 of 223 GMS documents → 404 (AGMS Agenda 2025, EGMS Announcement 2024, PoA AGMS 2023) | Re-download the 3 PDFs from live OR remove dead entries |
| K4 | `kerja-praktik-dan-penelitian-tugas-akhir.html` | Page says form "akan dibuka 1 Agt 2026" + timeline as upcoming, but Google Form = CLOSED | Update text/timeline to reflect closed status (verify vs task #4) |
| K11 | `practical-work-student-research.html` (EN) | Same as K4, EN twin (same Google Form) | Same fix, EN |
| K13 | (dated content past its date) | Content shown as "upcoming" when already elapsed | Refresh dated content |

---

## 🟠 BATCH 2 — High: wrong data / untranslated / swapped docs (12)

### Group 2A — SYSTEMIC: stale `/indonesia/` orphan-copy links (the big pattern)
> Site keeps parallel copies: `/in/indonesia/*` (active, maintained ID) vs `/indonesia/*` (stale default/EN). Internal ID links wrongly point at the stale copies.
| # | Page | Fix |
|---|------|-----|
| T1 | Whistleblower Channel/VWC links wrong on **3 pages** (Integritas Bisnis, Pengaduan, Komunitas) → point to stale EN copy | Fix hrefs to active `/in/indonesia/` versions |
| K5 | (above) Direksi link — same pattern | Same |
| → | **Sitewide sweep** for `href="/indonesia/..."` inside `/in/indonesia/` pages | One scripted pass could fix the whole class |

### Group 2B — Untranslated ID pages (content, needs Bahasa copy)
| # | Page | Problem |
|---|------|---------|
| T2 | `grievance.html` / `whistleblowing-system.html` (ID) | Entire page 100% English — never translated |
| T12 | `life-at-pt-vale-indonesia.html` (EN) | A full **Indonesian** paragraph appears under "Work Locations" (wrong-language leak) |

### Group 2C — Wrong data / swapped documents
| # | Page | Problem |
|---|------|---------|
| T3 | `dampak-ekonomi-lokal.html` | "Laporan Keberlanjutan" card opens the **Policy** doc, not the Report — swapped |
| T4 | `tanamalia-project.html` + `our-operations.html` | PPKH permit number differs in 3 places (885 vs 855 Tahun 2025) — data error |
| T5 | `governance.html` / `tata-kelola.html` | Governance cut-off date differs by 1 year between languages (31 Des 2024 vs 2025) |
| T6 | `indonesia-growth-projects-pomalaa.html` (ID) | 2 sub-sections have identical copy-pasted paragraph (should differ) |
| T7 | `awards-and-certifications.html` (EN) | ISO 14001 row crams 3 certs; ISO 17025 row lost its photo. (Also on live) |
| T8 | `documents-and-reports.html` | EN has 6 more entries than ID for same period — duplicate files. **Relates to our Doc Library work — re-verify** |
| T9 | `board-of-directors.html` (EN) | Translation error makes director bio contradictory ("last served" → "currently serves") |
| T10/T11 | `towuti-oil-leakage-recovery.html` (EN) | Timeline dates out of order (dup calendar dates); "Compensation" section is empty (title only) |
| T13 | homepage (EN) | English section heading about "supplier" content placed under an Investor section |

---

## 🟡 BATCH 3 — Medium: translation/dup/leaked-text (22)

Grouped by fix type:

**Duplicated headings/paragraphs (delete the dup):** S1 (Towuti Day3=Day4), S4 (Taman Kehati H1 ×2), S18 (Towuti "Day 1" ×2), S19 (Practical Work closing clause ×2), S20 (Sawerigading H1 ×2), S21 (career "Archives" heading ×2), S16 ("Directors' Decree" ×2)

**Wrong-language text on a page:** S2 (Code of Conduct docs English on ID), S10 (Komite: 4 named, 3 shown), S13 (Tanamalia Briefing Book Indonesian on EN page), S15 (truncated sentence EN), S17 ("dan" in English sentence)

**Leaked code/entities:** S9 (truncated "ka"→"kami"), S11 (stray "|" after %), S12 (`&quot;` not rendered), S8 (`Fotógrafo: xxxx` placeholder captions on 10+ pages)

**Stale domain `vale.com`→`valeindonesia.com`:** S3 (JWPC poster ×2), S14 (5 links on major-shareholders EN), S22 (JWPC body text)

**Untranslated labels:** S5 (See our Map — DONE?), S6 (grievance table English labels/dates)

**Other:** S7 (double ID+EN caption)

---

## 🟢 BATCH 4 — Low / cosmetic (4)

| # | Fix |
|---|-----|
| R1 | FAQ says "PT Vale" twice awkwardly (Towuti) — text edit |
| R2 | Literal `>` before each career listing (arrow icon fail) — `career.html` |
| R3 | Domain-change popup reappears every page load (no session memory) — **relates to our popup work; add sessionStorage flag** |
| R4 | "All News" menu item untranslated in ID hamburger — nav label |

---

## Recommended execution order

1. **Batch 0 (verify):** re-check the ~5 likely-already-fixed (K6, K4/K11/K13, S5, T8) — clear them cheaply.
2. **Batch 1A (systemic hrefs):** the `/indonesia/`→`/in/indonesia/` orphan-link sweep (K5, T1) + Accessibility footer (K7) — high impact, scriptable, low risk. Resolves several at once.
3. **Batch 1A/1C (dead links):** Towuti news links (K1, K10), GMS 3 docs (K8).
4. **Batch 1B (needs input):** K2 (supplier form URL), K9 (community targets), K12 (GPTW article) — **need COMMs/target info before fixing.**
5. **Batch 2/3 (content):** translation + dedup + domain sweeps — mostly mechanical, batch per page.
6. **Batch 4:** cosmetic + popup session flag.

## Open questions for Feiry
- **K2 / K9 / K12:** need real target URLs (supplier form, community sub-pages, GPTW article) — do these exist, or should broken links be removed?
- **K9 / community.html:** is this part of the ESG hub (out of scope)?
- **"Identical-to-live-vale.com" warts** (K2, T7, S8, etc.): fix on our prod, or leave as upstream Vale/COMMs content issues?
- **Deploy cadence:** batch-by-batch to dev→prod (like Doc Library), or accumulate then one deploy?
