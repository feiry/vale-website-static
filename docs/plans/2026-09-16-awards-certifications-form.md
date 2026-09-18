# Awards & Certifications Form + Intake Tool — Implementation Plan

**Goal:** Give COMMs a self-service visual form to add Awards / Certifications to the
awards-and-certifications page, plus a GDI intake tool that injects the items directly
into both the EN and ID pages — matching the existing news/doc self-service pipeline.

**Architecture:** Two scripts mirroring the `make-*-editor.py` + `intake-to-*.py`
pattern. Unlike news/docs, there is **no data file + rebuild** — awards content lives
directly in the cloned Liferay HTML, so the intake tool does **direct row injection**
into the two bilingual pages, with a per-page backup + HTML-parse self-check.

**Tech Stack:** Python 3 stdlib only (no deps), client-side HTML/JS form (no build step).

---

## Target pages
- EN: `site/vale.com/indonesia/awards-and-certifications.html`
- ID: `site/vale.com/in/indonesia/penghargaan-dan-sertifikasi.html`

## Page structure (verified 2026-09-16)
- Two sections, each mirrored EN+ID:
  - **Certification** (`<h2>Certification</h2>`, EN line ~4417): rows of **5 columns** —
    standard name · validity period · scope · issuing body · cert image (image col may be empty).
  - **Awards** (`<h2>Awards</h2>`, EN line ~4795): a set of **per-year accordion panels**
    (`<span class="lead">YYYY</span>`, years 2011–2026, newest first). Each panel holds
    rows of **3 columns** — description · awarding body · image (image optionally wrapped
    in an `<a target="_blank" href="/…/w/<news>.html">` link). First row per year also
    carries a header row of `<h6>` labels.
- Award/cert images live under `/documents/44618/<folderid>/<file>`; new ones go to a new
  shared folder `/documents/44618/awards/<file>` (keep extension; `+` for spaces per the
  site's encoding convention — see intake-to-doc `_encode`).

## Record shape (what the form saves — `awards-record.json`)
```json
{
  "items": [
    { "type": "award", "year": "2026",
      "en": {"description": "...", "awarding_body": "..."},
      "id": {"description": "...", "awarding_body": "..."},
      "image": "MyAward2026.jpg", "link": "/indonesia/w/optional-news.html" },
    { "type": "certification",
      "en": {"standard": "...", "validity": "...", "scope": "...", "issuer": "..."},
      "id": {"standard": "...", "validity": "...", "scope": "...", "issuer": "..."},
      "image": "MyCert.jpg" }
  ]
}
```
- One submission can carry multiple items (a batch), mixed types.
- `link` optional (awards only). `image` optional (renders empty image col if blank).

## Injection rules
- **award** → find the accordion panel whose `<span class="lead">` == `year`; insert the
  new 3-col row as the **first data row** of that panel's `conteudo-montado` (after the
  header-label row if present). If no panel for that year exists → **auto-create** a new
  `accordion-item` panel in correct descending-year sort position, then insert.
- **certification** → insert the new 5-col row as the first row under `<h2>Certification</h2>`.
- Every generated row uses **fresh unique ids** for `data-layout-structure-item-id` /
  `id="fragment-…"` (uuid4) so it never collides with existing Liferay ids.
- Apply the **same item to both EN and ID** pages, using each language's text block.

## Safety
- Back up each page to `<page>.bak-awards-<stamp>` before writing.
- After writing, parse the file with `html.parser` (HTMLParser subclass that never raises
  is not enough — use a well-formedness check: parse + verify tag balance heuristic, and
  verify the new image `src` + row markers are present). If parse/verify fails, restore
  the backup and exit non-zero (never leave a half-written page). Mirrors the JSON
  self-check in intake-to-news/doc.
- `--dry-run`: print what would be inserted + where (line anchors) + image dest paths,
  write nothing.
- Verify every referenced image exists on disk (or in the request folder) and print the
  `/documents/44618/awards/<file>` dest each must be copied to.

## Tasks
1. Extract exact award (3-col) + cert (5-col) + year-panel row **templates** from the live
   EN page into python string templates with `{placeholders}`; confirm an injected sample
   renders identically (add sample row → open in browser/grep → revert).
2. `make-awards-editor.py`: bilingual form, type toggle (award/cert), per-type fields,
   multi-item "add another", image file pickers, Save → `awards-record.json`. Model styling
   + save/download flow on `make-doc-editor.py`.
3. `intake-to-awards.py`: parse record → validate → locate anchors in both pages → build
   rows with fresh ids → inject → backup + self-check + `--dry-run`. Print image dests.
4. Test end-to-end with a throwaway 1-award + 1-cert record against copies of both pages;
   verify rows land in the right year panel / cert section, both languages, HTML still
   well-formed; then revert test artifacts.
5. Wire into deploy: images to `/documents/44618/awards/`, incremental upload of the 2
   changed pages + images (same pattern as the news deploy).

## Notes / gotchas (from memory)
- Reclone of either page would wipe injected rows (site/ is gitignored, not rebuilt from a
  data file) — awards live only in the HTML. Document this; a future improvement is to
  externalize awards to a data file + builder, but out of scope now.
- Filename encoding: spaces → `+` in links/paths; watch `&`/`%2C` traps (see deploy MIME
  memory) — sanitize/warn on odd chars in image filenames.
- Deploy content-type: award images keep extension (.jpg/.png) so normal MIME; only force
  types if any come in extensionless.
