# ValeForms — Detailed Execution Plan (PM: Cibo)

Companion to `2026-08-03-valeforms-qa-catalog.md`. This is the buildable plan the
subagents execute. PM (me) owns dispatch + review; subagents do the edits.

Ground rules (from memory + CLAUDE.md):
- Patch in place; regenerate via builders. NO recrawl / full rebuild.
- Deploy incrementally to Azure dev later (not part of these tasks unless asked).
- Verify with real output before claiming done. Match surrounding code style.

Builders & data:
- `build-doc-library.py` → site/vale.com/{indonesia,in/indonesia}/documents-and-reports.html
- `build-news.py` → all-news.html (EN+ID) + homepage highlight + /w/ article pages
- Data: `site-data/documents.json`, `site-data/news.json` (408 records)

Hero assets confirmed IN CLONE (no fetch needed):
- Doc Library: `/documents/44618/1276840/press-releases-header.png` (+ `-mobile.png`)
  alt "A Vale employee holds a notebook as she walks through the machine area…"
- News: `/documents/44618/9161766/news-header-mining.jpg`
Hero component reference (markup + CSS): `indonesia-growth-projects.html`
  → `<section class="vale-fragmento-header-interno">` with
  `.img-desktop{height:37.5rem;object-fit:cover}`, `<h1 class="h1 font-weight-medium text-branco">`.

---

## TASK 0 — Hero header on Doc Library + News list pages  [subagent: hero]

Adopt the vale.com `vale-fragmento-header-interno` hero on both list pages so the
title sits over a full-bleed image and clears the fixed top menu.

Deliverables:
1. `build-news.py`: inject hero block ABOVE `.news-listing-header` inside
   `build_listing_page` main_content (~L414-419). Add hero CSS to `LISTING_STYLES`.
   - Image: `/documents/44618/9161766/news-header-mining.jpg`
   - Eyebrow "PT Vale Indonesia" + white `<h1>` = heading ("All News"/"Semua Berita").
   - Keep existing `.news-listing-header`? Replace its role: the hero now carries the
     H1. Remove/ް empty the old plain H1 block to avoid a duplicate heading.
2. `build-doc-library.py`: same, above `.doclib-header` (~L371-374). Add hero CSS to
   `STYLES`. Image: `/documents/44618/1276840/press-releases-header.png`.
   - Keep the intro `<p>` as a subheading BELOW the hero (in a section head), not lost.
3. Simplify the ported hero to a self-contained block (drop the Liferay breadcrumb
   portlet markup; keep image + overlay + eyebrow + h1). Full-bleed, ~24-30rem tall,
   dark gradient scrim so white text is legible, responsive (mobile image variant).
4. EN + ID both. Same image; localized eyebrow/title.
Acceptance: run both builders (real run), diff shows hero present on all 4 pages
(en/id × news/doc), H1 not duplicated, title visually clears menu. Spot-check the
generated HTML for the `<img src=…press-releases-header.png>` / `news-header-mining.jpg`.

## TASK 1 — Doc Library UI fixes  [subagent: doclib-ui]

From Ibu Sri (verbatim): compact Library; remove PDF box; "Bahasa (BH)"→"Indonesia (IN)".

1a. COMPACT: reduce vertical rhythm in `build-doc-library.py STYLES` so page scrolls
    less: `.doclib-section{margin-bottom}` 3rem→~1.75rem; `.doclib-cards gap` 1rem→0.6rem;
    card `padding` 1rem→0.7rem; `.doclib-section-head margin-bottom` 1.25rem→0.8rem;
    chipbar margin 2.5rem→1.5rem. Keep readable; don't crush.
1b. REMOVE PDF box: delete the `.doclib-card-icon` element from `render_card` (the
    green "PDF"/ext badge left of the title) and its now-unused CSS. Re-flow card so
    title starts at the left edge.
1c. RELABEL "Bahasa (BH)" → "Indonesia (IN)":
    - Press-release sub-filter labels (~L299-301): "Bahasa"→"Indonesia".
    - Per-card lang tag: render "IN" instead of "BH" (render_card ~L261-262). Keep the
      data-lang attribute value consistent with the sub-filter's data-lang so filtering
      still works — i.e. change BOTH the button data-lang and the tag together, or map
      display "IN" while keeping internal key. Simplest: display text IN, internal BH
      key unchanged → change only the visible label text, not the filter keys. VERIFY
      the language sub-filter still filters after the change.
    - Keep "EN"/"English" as-is.
Acceptance: run builder; generated doc pages show no PDF badge, tighter layout, tags/
labels read "IN"/"Indonesia"; EN/Indonesia press-release sub-filter still works.

## TASK 2 — News scope: Vale-Indonesia only  [subagent: news-scope]  ⚠ NEEDS PM REVIEW

Ibu Sri: include only Vale Indonesia news; exclude Vale Global. CSV of 346 target
EN slugs provided. PROBLEM (verified): CSV slugs are raw vale.com slugs; our
news.json uses custom slugs → only 213/346 match directly. Category filter yields
~209 (Indonesia-local tag) to ~220 (no-global-cat). These don't fully agree.

Approach (DO NOT silently drop articles):
1. Build a reconciliation report (script under scratchpad or a one-off), matching
   news.json ↔ CSV by: (a) direct slug, (b) normalized title, (c) fuzzy fallback.
2. Produce 3 buckets: KEEP (in CSV or Indonesia-tagged), DROP (clearly global, not in
   CSV), UNCERTAIN (no confident match). Write counts + the UNCERTAIN list to a report
   file. Do NOT edit news.json yet for UNCERTAIN.
3. Recommend a filter rule. Implement as a FLAG or a separate filtered data file so
   it's reversible — do not destroy the master news.json. (e.g. add `"indonesia": true`
   field, or write news-indonesia.json; builder reads the filtered set.)
4. Categories from Ibu Sri still PENDING — do not invent categories.
Acceptance: reconciliation report exists with counts + uncertain list; a reversible
filter mechanism implemented but NOT applied to prod data until PM approves the
uncertain bucket. Report back to PM with the numbers.

## TASK 3 — General UI tidy  [folded into 0/1]
No separate work; covered by hero (0) + compact/clean (1). Data & Reports "already
fine" per Peter. Subagents should keep visual polish consistent.

## TASK 4 — Bilingual one-link  [HELD — do not build]
Ibu Sri wants EN+ID under one link; says "belum memungkinkan… terbuka untuk diskusi."
PM action only: verify whether the top-right EN/ID toggle currently 404s, write up the
current behavior + 2-3 options for a future discussion. No code changes.

---

## Dispatch strategy
- Tasks 0 and 1 both edit `build-doc-library.py` → SERIALIZE those two (or one agent
  does both doc-library changes) to avoid edit conflicts. Task 0 also edits
  `build-news.py` (separate file) → can parallelize the news half.
- Task 2 edits `site-data`/adds a script → independent file, parallel-safe, but gated
  on PM review before any data mutation.
- After each agent: PM reviews diff, runs the builder, checks generated HTML.
