# How to Add a News Article

## Files

- `news.json` — the editable data source (408 articles, bilingual EN + ID).
- `TEMPLATE-record.json` — copy-paste this when adding a new article.

## Steps

1. Open `news.json` in a text editor.
2. Copy the contents of `TEMPLATE-record.json`.
3. Paste it as the **first item** in the JSON array (after the opening `[`).
4. Fill in all fields:
   - `slug` — URL-safe identifier, e.g. `pt-vale-wins-award-2026`. Must be unique. Used as the article URL.
   - `date` — ISO date `YYYY-MM-DD`, e.g. `2026-07-18`. Used for sorting (newest first).
   - `categories` — array of category strings, e.g. `["Indonesia", "Indonesia news"]`. Used for the category filter on the listing page.
   - `cover` — path to a cover image already uploaded to the site, e.g. `/documents/44618/cover.png`. Leave as `""` to use the default placeholder.
   - `en.title`, `en.subtitle`, `en.body` — English content. `body` is full HTML.
   - `id.title`, `id.subtitle`, `id.body` — Indonesian content. `body` is full HTML.
5. If only one language is available, omit the missing language block entirely (remove the `"en"` or `"id"` key). The generator will skip that language's page and hide the language switcher option.
6. Optionally drop a cover image under `site/vale.com/...` and set its path in `cover`.
7. Run the deploy script. It runs `build-news.py` automatically before uploading. If the build fails, the deploy aborts.

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

The listing page has client-side category filter buttons (All / Indonesia / ESG / …). These degrade gracefully: with JavaScript disabled, all articles are visible and nothing is hidden server-side.
