# How to Add a News Article

## Files

- `news-indonesia.json` — the editable data source (353 articles, bilingual EN + ID). This is what `build-news.py` reads.
- `news.json` — the full 995-article master export (backup/source). Not read by the build.
- `TEMPLATE-record.json` — the raw record shape (for reference / the manual method).

## Preferred method — the intake converter

For a COMMs-authored request, use `intake-to-news.py` instead of hand-editing JSON. COMMs
fills the visual form (`make-news-editor.py` → `new-article.html`) and Saves a
`news-record.json`; the converter validates it and appends safely — validating date,
category, slug uniqueness, and referenced images, backing up the data file, and
self-checking that the result still parses:

```bash
python3 intake-to-news.py <request-folder>/news-record.json --dry-run   # inspect
python3 intake-to-news.py <request-folder>/news-record.json             # write
python3 build-news.py                                                   # rebuild pages
```

Full operator steps (image placement, deploy) are in `docs/GDI-content-update-runbook.md`.

## Manual method (fallback)

1. Open `news-indonesia.json` in a text editor.
2. Copy the contents of `TEMPLATE-record.json`.
3. Paste it as a new item in the JSON array (position doesn't matter — the build sorts by date).
4. Fill in all fields:
   - `slug` — URL-safe identifier, e.g. `pt-vale-wins-award-2026`. Must be unique. Used as the article URL.
   - `date` — ISO date `YYYY-MM-DD`, e.g. `2026-07-18`. Used for sorting (newest first).
   - `categories` — array of category strings, e.g. `["Indonesia", "Indonesia news"]`. Used for the category filter on the listing page.
   - `cover` — path to a cover image already uploaded to the site, e.g. `/documents/44618/cover.png`. Leave as `""` to use the default placeholder.
   - `en.title`, `en.subtitle`, `en.body` — English content. `body` is full HTML.
   - `id.title`, `id.subtitle`, `id.body` — Indonesian content. `body` is full HTML.
5. If only one language is available, omit the missing language block entirely (remove the `"en"` or `"id"` key). The generator will skip that language's page and hide the language switcher option.
6. Optionally drop a cover image under `site/vale.com/...` and set its path in `cover`.
7. Run `python3 build-news.py`, then deploy the changed files (see the GDI runbook).

## Build only (without deploying)

```bash
python3 build-news.py
```

Output goes to:
- `site/vale.com/indonesia/all-news.html` — English listing
- `site/vale.com/in/indonesia/all-news.html` — Indonesian listing
- `site/vale.com/indonesia/w/<slug>.html` — English article pages
- `site/vale.com/in/indonesia/w/<slug>.html` — Indonesian article pages

## Guardrails

The builder checks for:
- **Invalid JSON** — aborts with a clear error message (line/column).
- **Missing date or title** — skips the record with a warning naming the slug.
- **Duplicate slug** — warns; last occurrence wins.
- **Orphan files** — warns about generated files whose slug is no longer in the data.

## Category filter

The listing page shows only a curated set of filter chips (Option B, per Ibu Sri):
`All`, `IGP Morowali`, `IGP Pomalaa`, `IGP Sorlim`, `People`, `Social`, `Sustainability`
(the `FILTER_CHIP_ALLOWLIST` in `build-news.py`). Articles keep all their categories, so
filtering still works — only the visible chip row is trimmed. The filter is client-side and
degrades gracefully: with JavaScript disabled, all articles are visible.
