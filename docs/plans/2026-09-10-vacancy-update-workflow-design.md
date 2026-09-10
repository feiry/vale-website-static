# Job-Vacancy Update Workflow — Design

**Date:** 2026-09-10
**Status:** BUILT & TESTED 2026-09-10 (vacancy_common.py, make-vacancy-manager.py, intake-to-vacancy.py, docs/GDI-vacancy-update-runbook.md). Not yet used on a real request.
**Context:** Fills a gap in the COMMs→GDI content-update workflow. The existing v1/v2 tooling
covers news, documents, page-edits, and new-pages — but **job-vacancy updates on `career.html`
were never a workflow type**. The 2026-09-10 request (add 2 lokers + remove 2 expired) surfaced
this, along with vacancy-specific gotchas (per-UUID font-size, EN/ID date/label differences,
PDF linking, `~/Downloads` TCC block).

Follows the same architecture as the visual page-editor track:
**visual HTML form → `vacancies.json` → GDI-run intake script → dev → sign-off → prod.**
(Markdown intake was explicitly rejected earlier as too cryptic for COMMs.)

---

## 1. Architecture & flow

Two artifacts:

1. **`make-vacancy-manager.py <career.html> -o vacancy-manager.html`**
   Generates a self-contained, double-clickable HTML form. Reads the current vacancy list from
   career.html so COMMs sees what's live; lets them **Add** rows and **check rows to Remove**;
   **Save** downloads `vacancies.json`. COMMs drops the JSON **and** referenced PDF(s) into the
   request folder.

2. **`intake-to-vacancy.py <vacancies.json>`** (GDI-run)
   Consumes the JSON; edits **both** `indonesia/career.html` and `in/indonesia/career.html`;
   builds slot markup; applies the font/UUID logic; inserts newest-first; removes matched slots;
   validates PDFs exist; **prints** the copy-to-`documents/d/guest/<slug>` worklist
   (print-don't-copy). `--dry-run` writes nothing. Never deploys.

Deploy remains GDI/PIM: **dev → COMMs-lead (Maman) sign-off → prod**, per the existing runbook.

---

## 2. `vacancies.json` contract

```json
{
  "_meta": {
    "source_pages": ["indonesia/career.html", "in/indonesia/career.html"],
    "type_sequence_sha": "<fingerprint of current vacancy list>",
    "generated": "2026-09-10"
  },
  "add": [
    {
      "title_en": "National - Head of Government & Institutional Relation",
      "title_id": "Nasional - Head of Government & Institutional Relation",
      "date": "2026-09-09",
      "pdf": "20260909_head-of-govt.pdf"
    }
  ],
  "remove": [
    { "match": "Head of MIS & Digital Transformation" }
  ]
}
```

- `date` stored ISO `YYYY-MM-DD`; script renders per-language: **EN `MM/DD/YYYY`**, **ID `DD/MM/YYYY`**.
- Labels: EN `> DATE - Job vacancy for <title_en>`; ID `>DATE - Lowongan Kerja untuk <title_id>`
  (note: ID uses **no space** after `>`, matching existing entries).
- `pdf` = filename only. Slug derived: `<YYYYMMDD>_<slugified-title>` (lowercase, hyphenated,
  `&`→removed), matching the existing `20260909_national-...` convention.
- `remove.match` = substring matched against the visible vacancy label. Script **aborts** if a
  match hits 0 or >1 slots (prevents deleting the wrong one, e.g. Luwu-Timur vs national HCBP).

**Drift guard:** `_meta.type_sequence_sha` checked against the live vacancy list before editing;
warn/abort if the list changed since the form was generated (same as `inject-page-content.py`).

---

## 3. Font-size / UUID logic (the core trick)

Every vacancy slot renders at 20px via a **per-UUID CSS rule** in the external layout stylesheet:

```css
.lfr-layout-structure-item-<UUID> { font-size: var(--font-size-lg); }  /* 20px */
```

A new slot with a fresh UUID has no such rule → falls back to 18px (the visible bug caught
2026-09-10). Algorithm:

1. Collect UUIDs of all slots being **removed** (they already carry the 20px rule).
2. For each **added** slot, in order:
   - **If a removed UUID is available** → reuse it (UUID + its fragment-id). Inherits 20px
     automatically. No CSS edit, no inline style. *(preferred)*
   - **Else** → fresh UUID **plus** inject `style="font-size:var(--font-size-lg)"` on the slot's
     `component-paragraph` div. *(fallback)*
3. Removed slots whose UUIDs weren't reused → markup deleted outright.

**Examples:** remove 2 / add 2 (today) → both reuse removed UUIDs → zero inline styles.
Add 3 / remove 0 → all 3 get fresh UUIDs + inline fallback.

**Safety:** post-edit, verify every new slot resolves to 20px (matched per-UUID rule OR inline
style present); report it so a font regression can't ship silently.

All of this lives in `intake-to-vacancy.py`; COMMs and the form never see UUIDs.

---

## 4. Visual form (`vacancy-manager.html`)

Self-contained, double-clickable (works on `file://`), Vale teal/yellow styling.

- **Current vacancies** — table read from career.html, one row per slot: date, title, **[Remove]**
  checkbox. COMMs sees exactly what's live.
- **Add new vacancy** — "＋ Add" appends an input row: **Title (EN)**, **Title (ID)**, **Date**
  (date-picker → ISO), **PDF filename** (+ note: "drop this PDF in the request folder"). Repeatable.
- **Toolbar** — **Save changes** (downloads `vacancies.json`) + **Reset**.

On Save: checked rows → `remove[]`, filled add-rows → `add[]`, plus `_meta` fingerprint.

**Deliberately NOT in the form (YAGNI):** no UUID/markup exposure; no PDF upload/embed (filename
reference only); no manual reordering (script inserts newest-first by date); no live slot preview
(fingerprint + GDI dev deploy is the check).

**Shared parser:** the "read current vacancies from career.html" parser is one module, used by both
`make-vacancy-manager.py` (populate table) and `intake-to-vacancy.py` (locate slots, compute drift
fingerprint) — like `pagecontent_common.py` for the page tools.

---

## 5. Validation, safety & testing

**Validations (abort with clear message):**
- Drift guard (`type_sequence_sha` vs live list).
- Date format `^\d{4}-\d{2}-\d{2}$`.
- Each `remove.match` hits **exactly one** slot (0 or >1 → abort).
- Every `add[].pdf` present in the request folder.
- Derived slug not colliding with an existing `documents/d/guest/` slug.
- Every add/remove applies cleanly to **both** EN and ID (twins); abort on asymmetry.

**Safety (mirrors `intake-to-news.py`):**
- Back up each career.html to `.bak-<ts>` before editing.
- Post-edit self-check: re-parse both pages, confirm expected vacancy count, confirm every new
  slot resolves to 20px. On failure → restore from backup, exit 1.
- `--dry-run` prints the full plan (add/remove slots, UUID-reuse decisions, PDF worklist,
  per-language labels); writes nothing.
- Print-don't-copy: prints `cp <pdf> site/vale.com/documents/d/guest/<slug>`; never touches blobs,
  never deploys.

**Testing (acceptance gates):**
- No-op request (empty add/remove) → career.html **byte-identical**.
- Today's scenario (add 2 / remove 2) → matches what shipped (reused UUIDs, 20px, correct order,
  MIS/HCBP gone).
- Negative tests: bad date, ambiguous remove, missing PDF, dup slug, drift mismatch → each exits 1
  with the right message.

---

## Deliverables checklist (when built)

- [ ] `vacancy_common.py` — shared career.html vacancy parser (list + fingerprint + slot spans).
- [ ] `make-vacancy-manager.py` → `vacancy-manager.html` (visual form).
- [ ] `intake-to-vacancy.py` (JSON → edit both career pages, font/UUID logic, PDF worklist, dry-run).
- [ ] `docs/templates/` note (vacancy request = the form, not a markdown template).
- [ ] GDI runbook section: run form → drop JSON+PDF → run script → deploy dev → sign-off → prod.
- [ ] COMMs guide entry + SLA (propose: 1 business day, like news/docs).

## Notes / gotchas to carry in
- `site/` is gitignored → the scripts are the source of truth (like the other intake tools).
- `~/Downloads` is TCC-blocked for the CLI; COMMs/GDI must place PDFs in the request folder
  (project-accessible), not leave them in Downloads.
- Slot markup reference and full 2026-09-10 worked example are in memory
  `project_career_vacancy_update_2026-09-10.md`.
