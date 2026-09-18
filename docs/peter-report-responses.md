# Responses to Peter's Live-vs-Staging Report — working notes

(For compiling answers into the report at the end. One entry per finding, in order.)

---

## Finding #1 — "Life at PT Vale" menu link → `-old` stale slug
**Peter:** Live ☰ menu "Life at PT Vale Indonesia" → `/in/indonesia/life-at-pt-vale-indonesia-old` (stale: title missing "Indonesia", older sections).
**Status on dev:** Internal menu ALREADY FIXED — dev menu points to the current `life-at-pt-vale-indonesia.html` (EN + ID, both 200). Live is the one still using `-old`; dev is ahead/correct. Only 4 leftover `-old` refs on dev are external links to Vale's press-room domain (`saladeimprensa.vale.com/en/indonesia/life-at-pt-vale-indonesia-old`) in a newsroom menu column — off-site, Vale-controlled.
**Decision (Feiry):** LEAVE AS-IS. No change. (Dev already correct; the 4 external press-room links left to match live's newsroom menu.)

---

## Finding #2 — "Kunjungi Taman Kehati" link on Biodiversity (ID) → jumped to English
**Peter:** Live ID Biodiversity page's Sawerigading CTA uses `/en/indonesia/sawerigading-wallacea-biodiversity-park` (EN locale) — ID readers thrown to English page.
**Status on dev:** Confirmed same class of bug on dev — the body CTA button on `in/indonesia/keanekaragaman-hayati.html` pointed to `/indonesia/sawerigading-wallacea-biodiversity-park.html` (EN page). (Nav submenu link was already correct.)
**Decision (Feiry):** FIX to point to the ID page.
**Action taken:** Repointed the body CTA → `/in/indonesia/taman-kehati-sawerigading-wallacea.html`. Both Sawerigading links on the page now ID. Deployed + verified live (target 200). Dev now better than live on this point.

---

## Finding #3 — Photo credits missing on staging (4 ID pages)
**Peter:** Staging missing "Foto:/Photo:" credit captions — Sekretaris Perusahaan (1 of 3), Kebijakan Tata Kelola (1), Sistem Pelaporan Pelanggaran (2), Rapat Umum Pemegang Saham (2).
**Status on dev — verified live-vs-dev credit counts, all IDENTICAL:**
- Sekretaris Perusahaan: 4 = 4 (3× "Foto: PT Vale Indonesia" + 1× "Photo: Marcelo Coelho")
- Kebijakan Tata Kelola Perusahaan: 5 = 5
- Sistem Pelaporan Pelanggaran: 3 = 3
- Rapat Umum Pemegang Saham: 2 = 2
Feiry also eyeballed Sekretaris (EN+ID) — credits render same as live.
**Decision (Feiry):** NO ACTION — finding is stale (already synced by our re-clones since Peter's audit). Dev = live on all 4 pages.

---

## Finding #4 — Card descriptions missing on staging (carousel cards)
**Peter:** Description text under card titles not showing — "Kenali kami lebih jauh" carousel on Tujuan dan Nilai-nilai Kami (Operasi kami / Keberlanjutan / Investor), + 5 cards on ESG page.
**Status on dev:** Descriptions ARE present in HTML, markup byte-identical to live. The desc div has Bootstrap class `d-none d-sm-block` = hidden on mobile, shown on desktop — SAME rule on live. Peter likely viewed at mobile width (or pre-re-clone).
**Verified:** Feiry confirmed by eye — dev & live identical on desktop (descriptions show under all 3 cards).
**Decision (Feiry):** NO ACTION — no real difference; responsive-by-design, matches live.
ESG page (5 cards: Tata Kelola/Strategi/Manajemen Risiko/Peta Jalan/Kinerja ESG): CONFIRMED same pattern — descriptions present in HTML with `d-none d-sm-block` responsive class, matches live. Whole finding #4 = no action.

---

## Finding #5 — Komite (Committees) photo credit "Foto: Vale" vs "Foto: PT Vale Indonesia"
**Peter:** 2nd photo credit differs — live "Foto: PT Vale Indonesia" vs staging "Foto: Vale".
**Status on dev — deeper cause (Feiry spotted):** not just a caption — the WHOLE Komite page was refreshed on live with different/newer images (new committee header, woman-in-mining, mobile header, ptvi-people-01) while dev had the old F00060420/835A8352 set. The credit difference was a symptom of the stale images.
**Decision (Feiry):** RE-CLONE komite + committees from live.
**Action taken:** Re-cloned both EN (`committees.html`) + ID (`komite.html`). Fetched 4 new images + new layout CSS. Photo credits now match live (ID: "Foto: Vale" + "Foto: PT Vale Indonesia"; EN: "Photo: PT Vale Indonesia"×2). Toggles/footer/menu all correct. Deployed + verified live (pages 200, new header image 200). Finding fully resolved incl. the underlying staleness.

---

## Finding #6 — "Telusuri lebih lanjut" button on Tentang PT Vale → wrong target
**Peter:** Live button → /informasi-saham ; staging → /pemegang-saham-utama-dan-pengendali.html (both valid pages; live just links to Informasi Saham here).
**Status on dev:** Confirmed on ID page. EN twin (about-pt-vale-indonesia.html) was ALREADY correct ("Find out more" → shares-information.html, matches live). Only ID wrong.
**Decision (Feiry):** FIX to match live, both langs (EN already correct).
**Action taken:** ID `tentang-pt-vale-indonesia.html` "Telusuri lebih lanjut" repointed `/in/indonesia/pemegang-saham-utama-dan-pengendali.html` → `/in/indonesia/informasi-saham.html`. Deployed + verified (target 200). EN needed no change.

---

## Finding #7 — Contact email domain: live @vale.com vs staging @valeindonesia.com
**Peter:** Live uses @vale.com (ptvi-corpsec@vale.com, ptvi.investorrelation@vale.com); staging uses @valeindonesia.com.
**Status on dev:** Confirmed different — dev EN+ID both @valeindonesia.com.
**Decision (Feiry):** LEAVE AS-IS — INTENTIONAL. This was a deliberate change Feiry requested earlier (change @vale.com → @valeindonesia.com on the contact pages). Not a clone error; dev is intentionally different from live here.

---

## Finding #8 — Stale breadcrumb on Pemasok/Suppliers
**Peter:** Staging shows "Transparansi dan Kebijakan > Pemasok" (retired category, merged into Keberlanjutan); live is clean "Pemasok".
**Status on dev:** Confirmed on BOTH — ID pemasok.html had middle crumb → /in/indonesia/transparansi-dan-kebijakan.html; EN suppliers.html had → /indonesia/transparency-and-policies.html.
**Decision (Feiry):** FIX both ID + EN.
**Action taken:** Removed the stale "Transparansi dan Kebijakan"/"Transparency and Policies" breadcrumb <li> from both pages → now just Home › Pemasok / Home › Suppliers (matches live). Deployed + verified (0 stale crumbs live).

---

## Finding #9 — Awards 2026: live 5, staging 3 (missing 2 newest)
**Peter:** Live 2026 accordion = 5 awards; staging = 3 (missing "Juara 1 Confined Space Rescue IMERC 2026" + "Posisi 74 Fortune 100 / Fortune Indonesia"). 2011–2025 identical.
**Status on dev:** Confirmed — IMERC + Fortune 100 absent on dev (both langs). Live ~802KB vs dev ~749KB.
**Decision (Feiry):** RE-CLONE awards EN + ID.
**Action taken:** Re-cloned `awards-and-certifications.html` (EN) + `penghargaan-dan-sertifikasi.html` (ID). Both now show all 5 2026 awards incl. IMERC + Fortune 100 #74. Fetched 3 new award images + layout CSS. 2011–2025 verified byte-identical (unchanged). Toggles/footer/menu correct; 7 award news-card links normalized to on-disk /w/*.html. Deployed + verified live.

---

## Finding #10 (EN bug) — Corporate Secretary EN photo credit "Foto:PT Vale / Image Bank"
**Peter:** EN page shows "Foto:PT Vale / Image Bank" — Indonesian "Foto", no space after colon, wrong source. Live correct: "Photo: PT Vale Indonesia".
**Status on dev:** Confirmed — 3× "Foto:PT Vale / Image Bank" on EN corporate-secretary.html.
**Decision (Feiry):** FIX.
**Action taken:** Replaced 3× → "Photo: PT Vale Indonesia" (matches live). 0 "Foto:" left on EN page. Deployed + verified live (3× "Photo: PT Vale Indonesia" + 1× "Photo: Marcelo Coelho").

---

## Finding #11 (EN) — About EN missing Makassar Rep Office address (reverse pattern: live incomplete)
**Peter:** Live EN About page missing Makassar Representative Office details (city/province/phone/fax); staging EN has them.
**Status on dev:** Verified live vs dev — now IDENTICAL. Both show full Makassar block ("Jl. Somba Opu No. 281 Makassar 90113, Sulawesi Selatan, Tel +62 411 366 9000, Fax +62 411 366 9020"). Live has since been fixed (or transient miss in Peter's audit).
**Decision (Feiry):** NO ACTION — resolved, dev = live.

---

## Finding #12 (EN bug) — "Documents and Reports" EN accordion broken on LIVE (0 results)
**Peter:** Live EN Documents & Reports accordion shows "0" in ALL categories (Press Releases, Financial Statements, Annual, Sustainability, Presentation) — live bug, confirmed w/ screenshots.
**Status on dev:** Dev is BETTER than live. Our custom static Doc Library renders all documents: 195 PDF links across 5 categories (Annual 25, Sustainability 20, Financial 74, Presentation 13, Press Releases 63). Live's JS accordion is broken; our static version works.
**Decision (Feiry):** NO ACTION — resolved; dev superior to live (this is a win for staging). Nothing to fix on our side.

---

## Finding #13 (EN recurring patterns) — Peter's "Pola dari versi ID berulang di EN"
**13a. All News (EN):** live /en/indonesia shows Vale Brasil global news; staging shows curated PT Vale Indonesia news (translated). DECISION: NO ACTION — intentional; dev is the correct curated set (same rationale as ID All News).
**13b. Card descriptions (Our Organization + Our Purpose EN):** descriptions present in HTML with `d-none d-sm-block` (mobile-hidden by design, matches live). DECISION: NO ACTION (same as Finding #4).
**13c. Photo credits EN — 5 pages Peter listed:**
  - General Meeting of Shareholders (EN): verified SAME as live — no issue.
  - Committees (EN): already fixed via Finding #5 re-clone.
  - Risk Management (EN): images identical to live (not stale) → caption-only. FIXED: 3× "Photo: Vale / Image Bank" → "Photo: PT Vale Indonesia". Deployed. (ID twin manajemen-risiko already matched live.)
  - Whistleblowing System (EN): same — images identical → caption-only. FIXED: 3× → "Photo: PT Vale Indonesia". Deployed. (ID twin already matched.)
  - Corporate Governance Policy (EN): STALE IMAGES (live has "Timur Angin" + "PT Vale Indonesia" photographer credits dev lacks). DECISION: RE-CLONE EN+ID (in progress).
**13d. Awards accordion EN:** already fixed via Finding #9 re-clone (both langs now 5 2026 awards; 2011–2025 identical).

---

## Finding #13c (cont.) — Corporate Governance Policy (EN+ID) stale images
**Status:** Confirmed stale — old dev had zero "Timur Angin"/"PT Vale Indonesia" credits + pointed at stale images (835A9635/Brasil-img/F00060495); live uses header.png/our-people-6.jpg/pt+vale+indonesia+tbk photos.
**Decision (Feiry):** RE-CLONE EN+ID (stale images, not just captions).
**Action taken:** Re-cloned both. Credits now match live (EN: PT Vale Indonesia×2, Timur Angin, Vale/Image Bank, Marcelo Coelho; ID: matching set). All assets on disk, toggles/footer/menu correct. Deployed + verified live (Timur Angin credit present both langs).

**NOTE (Feiry observation):** On LIVE itself, the corp-gov-policy ID page differs from the EN page (live's own ID vs EN are not in sync — e.g. credit sets differ). This is a live-side ID/EN inconsistency, NOT a staging bug. Our dev clones each language faithfully from its own live source, so dev mirrors live per-language. No action on our side; flagged for Vale/Comms awareness.

---

## Finding #14 — "Ronde verifikasi tambahan" (Peter's extra verify round — all confirmed OK)
This whole section = items Peter RE-VERIFIED as identical/working, not new bugs:
- Awards 2011–2025: identical (only 2026 differed → fixed via #9 re-clone). ✅
- 11 YouTube video IDs across 4 pages (Tentang, Sorowako, IGP Pomalaa, Morowali, Sorowako Limonite): same live & staging. ✅
- Homepage footer: all 12 internal links match link-per-link (only .html suffix differs). ✅
- Struktur Organisasi card links + "meet Direksi/Komisaris": identical. ✅
- 3 policy download links (Anti-corruption, Code of Conduct, Sustainability Policy) on Kebijakan Kami: href identical. ✅
- Audit Committee member names (plain text, not links both sites): consistent, not a bug. ✅
- Sejarah Vale nested 2023 carousel: works, no error. ✅
**Decision (Feiry):** NO ACTION — all confirmed-good; only real diff (Awards 2026) already fixed.

---

## Finding #15 — "Cakupan pengecekan" + "Temuan Tambahan Audit Fungsional Mendalam" (coverage/methodology)
This is Peter's coverage summary + methodology note, NOT new findings:
- Coverage: burger menu (58 pages), footers (main + Investor columns), social/cookie buttons, full text of all 58 pages, Financial Highlights table (corrected: it's HTML text not an image — verified identical), all interactive elements (every "Telusuri" link/download/accordion clicked). Visual/screenshot-per-page comparison = "Belum" (not done; used text extraction).
- Methodology caveat (Peter's own): the 58-page re-verify ran via 4 parallel processes sharing browser tabs → small race-condition risk; "if any finding seems odd, re-check manually." This explains why several text-based findings (#3 photo credits, #11 Makassar) turned out already-matching live.
- The deep functional audit validated text findings + surfaced the functional bugs already covered above (#1, #2, #12, etc.).
**Decision (Feiry):** NO ACTION — coverage/methodology summary. Our per-finding verify-against-live approach already accounted for the race-condition caveat.

===== END OF PER-FINDING RESPONSES =====
