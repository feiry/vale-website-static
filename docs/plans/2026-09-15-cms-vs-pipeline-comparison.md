# COMMs Self-Service Publishing — Teams Pipeline vs Git-Backed CMS

**Date:** 2026-09-15
**Question:** Should we add a "little CMS" to the Azure static site so COMMs can publish
without GDI? This compares two ways to get there.

## The goal (agreed)

Let the **COMMs team publish content themselves** — remove GDI from the day-to-day loop.
Note: we already have the *authoring* half built — visual forms (news, docs, vacancies), a
visual page editor, and data-driven builds. **The only thing GDI still does is the deploy.**
So this is really about automating the *publish* step, not building authoring from scratch.

---

## The two options

### Option A — Finish the Teams pipeline (reuse what's built)
COMMs author in the existing forms → drop in the Teams folder → chat "publish" → an
assistant validates, builds, deploys to a preview, and (after their approval) to production.
GDI is out of the loop. *(Full design: `2026-09-15-teams-pipeline-vm-design.md`.)*

### Option B — Add a Git-backed CMS admin UI (Decap / Sveltia CMS)
A login-protected `/admin` on the site where COMMs edit content in a proper UI and click
**Publish**. Publish commits the change to a **Git repo**; a **CI/CD pipeline rebuilds** the
site and **deploys to Azure Blob**. No server, no database — the CMS is static JS + Git + a
build. Decap is the established option (Azure backend + GitHub OAuth proxy exist); Sveltia is
its lighter modern successor.

---

## Head-to-head

| | **A — Teams pipeline** | **B — Git-backed CMS** |
|---|---|---|
| COMMs self-service? | ✅ author + trigger + approve | ✅ login, edit, click Publish |
| Where COMMs work | Teams (already used) + the forms | A new `/admin` web UI on the site |
| Reuses our forms/editor/build | ✅ **entirely** | ⚠️ partly — build yes, but content must move into the CMS's model |
| New content model needed | ❌ none | ✅ **yes — the big cost** (see below) |
| Handles our 9,000-line Liferay HTML pages | ✅ (the page-editor already does) | ❌ **not well** — Git CMSs edit structured Markdown/JSON, not bespoke HTML |
| Infrastructure | 1 VM + Teams bot (GDI tenant) | Git repo + CI/CD build + OAuth proxy + auth provider |
| Auth / access | AD-group check, COMMs-only (designed) | GitHub/OAuth accounts for each COMMs person |
| Deploy trigger | chat "publish" → approve | git commit → CI build → deploy |
| Preview before prod | ✅ dev preview + approve gate | ✅ (PR/branch preview, if wired) |
| Effort from here | **Low–medium** — it's designed; build the pipeline | **High** — new admin, content migration, CI/CD, auth |
| Monthly cost | ~$50–110 (VM + metered AI) | ~$0 for the CMS itself + CI/CD minutes + repo |
| Best fit | Our site *as it is today* | Sites whose content is *already* structured Markdown/JSON |

---

## The decisive issue: our content shape

Git-backed CMSs (Decap/Sveltia/Tina) are built to edit **structured content** — Markdown or
JSON files with defined fields — which a static-site generator then renders into HTML. That is
**not** how our site is built. Our pages are **9,000-line Liferay-exported HTML mirrors**;
there is no "title + body + fields" model behind them.

To adopt a Git CMS properly we would have to:
1. Define a content model for every page/post type,
2. **Migrate existing content out of the HTML** into that model,
3. Build **templates** that re-render the current look from the model,
4. Stand up **CI/CD** (GitHub Actions → Azure Blob) + an **OAuth proxy** + per-user auth.

That is effectively **rebuilding the site as a generated static site** — a large project, and
a different thing from "add a little CMS."

Our **news** and **documents** are the exception: they *are* already data-driven
(`news-indonesia.json`, `documents.json` → generated pages). Those two could plausibly be
fronted by a small CMS UI with modest effort. The bespoke pages (career, ESG, investor, etc.)
are the ones that don't fit.

---

## Recommendation

**Do Option A (finish the Teams pipeline) as the path to COMMs self-service.** It reaches the
goal — COMMs publish without GDI — while reusing everything already built, handling both the
data-driven content *and* the bespoke HTML pages, and needing no content migration.

**Keep Option B in mind as a possible later refinement, scoped narrowly:** if COMMs want a
polished "log in and edit" admin for the **data-driven content only** (news + documents), a
small Git-backed CMS UI over those JSON files is feasible without touching the bespoke pages.
That is an additive enhancement, not a replacement — and a decision for after the pipeline is
proven.

**What we would NOT recommend:** a full Git-CMS rebuild of the whole site. It would discard
the Liferay-fidelity mirror, require migrating every bespoke page into a content model, and
deliver roughly the same COMMs outcome the pipeline already gives — at multiples of the cost.

## Sources
- Decap CMS (Azure backend + GitHub OAuth proxy), Sveltia CMS (lighter successor)
- Azure Blob static-site deploy via GitHub Actions (`$web` container upload)
