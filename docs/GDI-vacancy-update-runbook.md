# GDI Runbook — Job-Vacancy Updates (career.html)

How GDI processes a COMMs request to add/remove job vacancies on
www.valeindonesia.com/indonesia/career.html (and its `/in/` twin).

Tooling (repo root, no external deps — `site/` is gitignored so these scripts ARE the
source of truth): `vacancy_common.py`, `make-vacancy-manager.py`, `intake-to-vacancy.py`.

## The flow

1. **Generate the form FRESH for each request** (⚠️ do NOT reuse an old copy):
   ```
   python3 make-vacancy-manager.py -o vacancy-manager.html
   ```
   The form bakes in the **currently-visible** vacancies at generation time (a
   snapshot — a double-clicked `file://` form cannot fetch the live site because
   valeindonesia.com sends no CORS header). The form carries a "live as of <date>"
   banner so COMMs can spot a stale copy. Because it's a snapshot, **regenerate it
   right before sending to COMMs** so it reflects what's actually live.

   Send `vacancy-manager.html` to COMMs (they have no access to the local repo).
   They **double-click** it, tick expired vacancies to Remove, fill an Add row per
   new vacancy (Title EN, Title ID, Date, PDF filename), click **Save** → it
   downloads `vacancies.json`.

   The form lists ONLY the visible "Recent opportunities" vacancies (currently 2) —
   not the 9 hidden/archived text slots — so COMMs sees exactly what a visitor sees.

2. **COMMs delivers** `vacancies.json` **plus the referenced PDF(s)** in one request
   folder (SharePoint drop, per the COMMs workflow). ⚠️ PDFs must be in that folder —
   do NOT leave them in `~/Downloads` (macOS TCC blocks the CLI from reading Downloads).

3. **Dry-run** (from repo root):
   ```
   python3 intake-to-vacancy.py <folder>/vacancies.json --dry-run
   ```
   Review the plan (which slots add/remove, UUID-reuse decisions, PDF worklist).

4. **Apply**:
   ```
   python3 intake-to-vacancy.py <folder>/vacancies.json
   ```
   Edits BOTH career pages, backs them up (`.bak-<ts>`), self-checks (count + 20px),
   restores automatically on failure. Prints the **PDF copy worklist**.

5. **Place the PDFs** — run the `cp` lines the script printed (copies each PDF to
   `site/vale.com/documents/d/guest/<slug>`, extensionless).

6. **Deploy to dev** (incremental — only the changed files):
   ```
   az account set --subscription <DEV-SUB>
   # 2 career pages (text/html) + each new PDF (application/pdf)
   az storage blob upload --account-name stidstaticsite002 --container-name '$web' \
     --name indonesia/career.html --file site/vale.com/indonesia/career.html \
     --content-type text/html --overwrite --auth-mode login
   # ...in/indonesia/career.html, and each documents/d/guest/<slug> as application/pdf
   ```
   Verify on the dev endpoint: pages 200, new PDF links 200 + `application/pdf`,
   new entries render at 20px (matching others), expired ones gone.

7. **Sign-off → prod.** COMMs-lead (Maman) approves on dev, then deploy the same files
   to `stidstaticsiteprod` (PIM active: activate roles + `rm ~/.azure/msal_token_cache.json`
   + `az login`). Verify on www.valeindonesia.com.

## Undoing a local apply — `rollback-vacancy.py`

Every `intake-to-vacancy.py` apply writes a `<page>.bak-<timestamp>` next to each
career page. To undo the last apply (e.g. wrong title, applied the stale JSON), use:

```
python3 rollback-vacancy.py --dry-run          # preview
python3 rollback-vacancy.py                     # restore both pages from newest backup
python3 rollback-vacancy.py --remove-pdf <slug> # also delete a placed PDF
python3 rollback-vacancy.py --keep-backups      # restore but leave .bak files
```

It restores both pages from their most-recent `.bak-<ts>`, then (by default) removes
the `.bak` files. `--remove-pdf <slug>` (repeatable) also deletes
`site/vale.com/documents/d/guest/<slug>`. This only undoes the **local** files — if you
already deployed, re-deploy the restored pages (and delete the blob if the PDF shipped).

Typical fix-a-mistake loop: `rollback-vacancy.py --remove-pdf <slug>` → correct the
form/JSON → re-run `intake-to-vacancy.py` → place PDF → redeploy.

## Why the script exists (the gotcha it encodes)

Each vacancy slot renders at **20px** because of a per-UUID CSS rule
`.lfr-layout-structure-item-<UUID>{font-size:var(--font-size-lg)}` in the external
layout stylesheet. A hand-added slot with a fresh UUID has no such rule → renders 18px
(visibly thinner — shipped once on 2026-09-10 before being caught). The script:
- **reuses the UUIDs of removed slots** for new slots (they carry the 20px rule); or
- if nothing is removed, adds an inline `style="font-size:var(--font-size-lg)"`.

It also handles EN/ID label + date differences (EN `> MM/DD/YYYY - Job vacancy for …`;
ID `>DD/MM/YYYY - Lowongan Kerja untuk …`), newest-first insertion, slug derivation,
and safety (exactly-one-match on removals, PDF-exists, slug-uniqueness, twin-symmetry,
backup/restore, dry-run).

## Safety notes
- Never edit career.html slots by hand — use the script (the font trick is easy to miss).
- `--dry-run` first, always.
- A re-clone of career.html reverts these edits (`site/` gitignored). Re-apply via the
  same request, or fold into postprocess if it recurs.

See the design: `docs/plans/2026-09-10-vacancy-update-workflow-design.md`.
Related workflow: `docs/GDI-content-update-runbook.md` (news/docs/pages).
