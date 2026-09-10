# GDI Runbook — Job-Vacancy Updates (career.html)

How GDI processes a COMMs request to add/remove job vacancies on
www.valeindonesia.com/indonesia/career.html (and its `/in/` twin).

Tooling (repo root, no external deps — `site/` is gitignored so these scripts ARE the
source of truth): `vacancy_common.py`, `make-vacancy-manager.py`, `intake-to-vacancy.py`.

## The flow

1. **Generate the form for COMMs** (only needed to reflect the current live list):
   ```
   python3 make-vacancy-manager.py -o vacancy-manager.html
   ```
   Send `vacancy-manager.html` to COMMs. They **double-click** it, tick expired
   vacancies to Remove, fill an Add row per new vacancy (Title EN, Title ID, Date,
   PDF filename), click **Save** → it downloads `vacancies.json`.

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
