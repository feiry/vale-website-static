# Static News Recreation — Design

**Date:** 2026-07-18
**Status:** Approved design. Implementation to run in a fresh session.
**Author:** Cibo (with Feiry)

## Problem

The Vale static mirror's News section is dynamic Liferay content that cannot be
statically cloned. `site/vale.com/indonesia/all-news.html` mounts a Liferay
`search-web` portlet that renders nothing without the live backend, and its
hardcoded `/w/<slug>/-/categories/5` article links all 404 (no files on disk).

We already exported the underlying data via the Liferay Headless REST APIs into
`vale-export/news.json` (408 articles, bilingual EN + ID, full body HTML).

## Goal

Replace the dead News listing + broken article links with **fully static,
pre-rendered** pages built from the export data, bilingual, matching the existing
site chrome. Users add new articles by editing one JSON file; the deploy script
rebuilds automatically, so from the user's side it stays "edit JSON → deploy".

**v1 scope: News only.** Document Library is a deferred second pass (same pattern,
`documents.json`).

## Decisions (confirmed with user)

- **Add-item mechanism:** edit a JSON data file (not a browser admin, not a CMS).
- **Rendering:** pre-render to static HTML (no runtime-JS list rendering — that is
  the exact fragility we eliminated across this project).
- **Build trigger:** build auto-runs inside the deploy script. User never runs a
  separate build; if build fails, deploy aborts (no partial upload).
- **First scope:** News listing + article pages only.

## Architecture & Data Flow

```
site-data/news.json  ──▶  build-news.py + templates  ──▶  static HTML in site/vale.com/  ──▶  deploy ──▶ Azure $web
```

Four pieces:

1. **Data source** — `site-data/news.json`. Seeded from the export, trimmed to the
   fields the pages need. This is the file a user edits to add an item.
2. **Generator** — `build-news.py`. Reads the JSON + two HTML templates, writes the
   listing pages and per-article pages.
3. **Link fix** — a scoped rewrite pass turning existing `/w/<slug>/-/categories/N`
   links into the new static `.html` paths.
4. **Deploy** — existing deploy script runs the build first, then uploads only
   changed files.

## Data File Shape — `site-data/news.json`

Array of records, both languages together per record:

```json
{
  "slug": "pt-vale-wins-hr-asia-award",
  "date": "2025-10-25",
  "categories": ["Indonesia", "Indonesia news"],
  "cover": "/o/adaptive-media/image/1234/.../cover.png",
  "en": { "title": "…", "subtitle": "…", "body": "<p>…full HTML…</p>" },
  "id": { "title": "…", "subtitle": "…", "body": "<p>…</p>" }
}
```

`body` holds the article HTML already exported (the 810 files in
`vale-export/articles/` collapse into these records). Seed this file by
transforming `vale-export/news.json` (which has `title_en`/`body_en`/`title_id`/
`body_id` flat fields) into this nested per-language shape.

## Add-an-Item Workflow (temporary manual solution)

1. Copy an existing record in `news.json`, paste at the top.
2. Change `slug`, `date`, `title`, `subtitle`, `body`, `categories`.
3. Optional: drop a cover image under `site/vale.com/…`, set its path in `cover`
   (falls back to a default if omitted).
4. Run deploy. Done.

Ship `site-data/TEMPLATE-record.json` + `site-data/README.md` ("How to add news").

## Generator — `build-news.py`

Reads `site-data/news.json` + templates, writes:

- `site/vale.com/indonesia/all-news.html` — EN listing (overwrites dead portlet page)
- `site/vale.com/in/indonesia/all-news.html` — ID listing
- `site/vale.com/indonesia/w/<slug>.html` — EN article, one per record
- `site/vale.com/in/indonesia/w/<slug>.html` — ID article

Article path `/indonesia/w/<slug>.html` matches the site's existing `/w/<slug>`
link pattern (just needs `.html` for static hosting).

**Sort:** listing shows newest first by `date`. Hand-added items with today's date
land at top naturally.

### Templates / look & feel

- Extract header + footer from a real known-good mirror page
  (e.g. `site/vale.com/indonesia/about-pt-vale-indonesia.html`) and wrap generated
  content between them. Guarantees nav, burger menu, logo, footer, CSS/JS includes,
  and `<html lang>` are byte-identical to the rest of the site — no drift.
- **Listing:** grid of news cards (cover, date, title, subtitle, category tags),
  each linking to its article. Reuse existing site CSS classes; minimal scoped
  `<style>` only if a class is missing.
- **Category filter:** client-side All / Indonesia / ESG / … buttons that show-hide
  cards. This is the *only* JavaScript. Degrades gracefully — JS off = all cards
  visible (nothing hidden server-side), so article content never depends on JS.
- **Article page:** same chrome; title → date → subtitle → cover → body HTML, plus
  "← Back to News". EN links to ID counterpart via existing language-switcher pattern.
- **Bilingual paths:** EN under `/indonesia/…`, ID under `/in/indonesia/…`. If a
  record has only one language body, skip the missing-language page and hide that
  switcher option rather than shipping an empty page.

## Existing Broken-Link Fix

After generating article pages, `build-news.py` runs a targeted rewrite over the
mirror:

- `href="/w/<slug>/-/categories/N"` → `/indonesia/w/<slug>.html` (EN page location)
  or `/in/indonesia/w/<slug>.html` (ID page location).
- Only slugs we actually generated get rewritten. Any `/w/` link whose slug is not
  in our data is left alone and **reported**, so we never create new dead ends
  silently.
- Honors the extensionless-link lesson: verify with the click-QA-aware scan (match
  all `href`, resolve against disk), not a `.html`-only scan.

## Build Safety / Idempotence

- Generator is **fully idempotent** — running twice produces identical output.
- Writes only the listing pages + `w/<slug>.html` files it owns; never touches
  unrelated pages except the scoped link-rewrite above.
- Tracks generated article files so a removed record's stale page can be cleaned up
  (warn on orphans rather than leaving ghosts).
- Guardrails on hand-edited JSON:
  - Invalid JSON → build aborts with line/column message, deploy stops.
  - Missing `date`/`title` → skip record with a warning naming its slug.
  - Duplicate slug → warning; last one wins.
- Deploy wiring: build runs first; **build failure aborts deploy** (no partial
  upload). Then incremental upload sends only changed files.

## Testing (before any deploy)

1. **Build test** — run generator; assert 408 EN + N ID pages + 2 listings; exit 0.
2. **Guardrail test** — feed a deliberately broken record (bad JSON, missing date,
   dup slug); assert build aborts / skips-with-warning as designed.
3. **Link test** — run the extensionless-aware broken-link scan over regenerated
   pages; assert 0 broken among rewritten `/w/` links.
4. **Visual spot check** — open one listing + one article locally; confirm chrome
   matches and body renders.
5. Only after all pass: incremental deploy, then live canary on 2–3 URLs.

## Out of Scope (v1)

- Document Library recreation (deferred v2, same pattern with `documents.json`).
- Any server/backend, browser admin form, or CMS.
- Full-text search on the listing (category filter only).

## Key Files

| File | Role |
|------|------|
| `site-data/news.json` | editable data source (seeded from export) |
| `site-data/TEMPLATE-record.json` | copy-paste template for new items |
| `site-data/README.md` | "how to add news" instructions |
| `build-news.py` | generator + scoped link-rewrite |
| `vale-export/news.json` | seed source (408 articles, flat bilingual fields) |
| deploy script | runs build first, then incremental upload |

## Implementation Order (next session)

1. Write `build-news.py` skeleton: load JSON, extract header/footer from a known
   page, render one article page + the listing for EN only. Spot-check visually.
2. Add ID rendering + bilingual path logic + language switcher.
3. Add category-filter JS to the listing.
4. Seed `site-data/news.json` from `vale-export/news.json` (transform flat →
   nested), write `TEMPLATE-record.json` + `README.md`.
5. Add the scoped `/w/` link-rewrite pass + orphan detection.
6. Add JSON guardrails + idempotence.
7. Run the four local tests.
8. Wire build into the deploy script (abort-on-failure).
9. Incremental deploy + live canary.
