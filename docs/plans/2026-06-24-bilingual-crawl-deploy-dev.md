# Bilingual Crawl → Patch → Deploy to Azure Dev

**Date:** 2026-06-24
**Scope source:** `Website-Sitemap-update.xlsx` (Rohman, 2026-06-24) → `urls-en.txt` (83) + `urls-id.txt` (83) = **166 URLs**
**Target:** Azure Blob static-website **dev** — account `stidstaticsite002`, container `$web` (per spec received today)

## Guiding constraints (non-negotiable)

1. **Crawl is one-shot and costly.** Crawl ONCE into a frozen, read-only snapshot. Never re-crawl to fix a downstream bug.
2. **The snapshot must outlive the crawl host.** Crawl runs on a disposable VM; the snapshot is archived to durable Blob storage so deleting the VM never loses it.
3. **All fixes happen downstream of the snapshot** — on a disposable working copy. If the deploy/patch process needs changing, we re-copy from the snapshot and re-run the cheap steps, never the crawl.
4. **Bilingual & language-cookie aware.** The live site serves language by cookie/session (Rohman's warning). EN and ID must be fetched in separate sessions or they cross-contaminate.
5. **Incremental deploy.** Only upload changed files; never full re-sync/rebuild. (Per project convention.)

## Why a fully fresh crawl (existing crawl is unusable)

- **The live site has changed since the last crawl** (confirmed by Vale) — so `site/` and `site-backup/` are both **stale** and cannot be reused, not even for the EN half.
- Existing `site/` is also **English only** — `find site -path '*/in/indonesia*'` returns **0**; the entire ID half is absent regardless.
- Decision: **fresh crawl of all 166 URLs**, both languages, into a new snapshot. Old `site/` and `site-backup/` are **retired** (kept on disk only until the new run is verified live, then deleted to reclaim ~3.3 GB). No merge.

## What gets crawled per spec page (scope of "links")

For every one of the 166 spec pages:
- **Always grab page requisites** — CSS, JS, images, fonts (`--page-requisites`).
- **Always grab linked documents/files** — PDFs, docx, anything under `/documents/...` linked from a spec page (a page is broken without its report/policy downloads).
- **Follow HTML links one level deep (depth +1), then STOP** — any vale.com HTML page directly linked from a spec page is also crawled, even if not in the 166 (catches orphan pages the spec missed). Their onward links are NOT followed.
- **Bounds on depth+1:** restrict to `vale.com`; exclude the `all-news@delta=...&start=...` pagination permutations (documented junk explosion) and other query-string listing variants, so depth+1 doesn't drag in hundreds of news-listing pages.

## Why per-URL direct fetch (not `crawl.sh --mirror`)

- `crawl.sh` is a recursive spider from a single `/indonesia` seed with `--include-directories`. That caused the documented **crawl gap** (missed root-level / `/in/` pages) and would follow links across languages.
- We now have an **explicit 166-URL list**. Fetch each URL directly, EN batch with an EN cookie jar, ID batch with an ID jar. Deterministic, complete, language-correct.

---

## Crawl host (VM) + durability

**Host:** small **Azure B2s Linux VM** in the existing dev RG `rg-staticsite-dev` (fits EY-provisioned footprint; same-network upload to `stidstaticsite002` runs at datacenter speed; `tmux`/`nohup` survive iPad/Termius disconnects).

**VM lifecycle — three distinct states (chosen: #1 + #3):**

1. **During the project (between fix cycles): deallocate, keep the disk.**
   - `az vm deallocate` releases compute (billing stops) but **keeps the OS + data disks intact** — `site-raw/` stays exactly where it is.
   - To re-fix: `az vm start` (~30–60s) → disk and `site-raw/` are right there → re-copy/patch/deploy → `az vm deallocate` again.
   - **This is the fast daily re-fix path. No re-crawl, no re-download.**
   - ⚠️ **Always stop via `az vm deallocate`, never `sudo poweroff` from inside the OS.** A guest-OS shutdown leaves the VM "Stopped (allocated)" — compute keeps billing. Only `deallocate` → "Stopped (deallocated)" → compute billing stops.

2. **Right after the crawl: archive to Blob (insurance).**
   - `tar czf site-raw-2026-06-24.tar.gz site-raw/` + `az storage blob upload` → **private** container `crawl-archive` on `stidstaticsite002` (NOT `$web`).
   - Do this **immediately**, not at teardown — if the data disk is ever corrupted/deleted or the VM won't restart, this tarball is the only surviving copy of the costly crawl. The persisted disk handles day-to-day; the tarball handles disaster + post-project.

3. **Only at the very end (Phase 6): delete the VM.**
   - After verification is green and no more fixes are expected: `az vm delete` + disks/NIC/public-IP (stops even the disk pennies).
   - The `crawl-archive` tarball remains forever; any later re-patch pulls it from Blob and extracts.

Mental model: **deallocate-and-keep-disk = working storage during the project; tarball-in-Blob = permanent archive; delete = only when fully done.**

**Auth split (revised 2026-06-24 — VM cannot auth to Azure):** Vale's tenant **Conditional Access blocks interactive `az login` from the VM** (error 53003, unregistered device). And `feiry@valeindonesia.com` **lacks `roleAssignments/write`**, so we cannot grant the VM's managed identity a blob role ourselves (that's an EY/Owner action). Resolution that unblocks immediately:
- **VM does ONLY the crawl** (no Azure auth needed) → `site-raw/` → `tar`.
- **Mac does deploy + archive-upload**: `scp` the tarball down, then run `postprocess.sh` + `deploy-azure.sh` + the `crawl-archive` upload locally, where `feiry@valeindonesia.com`'s existing blob read/write role works (the Mac is not Conditional-Access-blocked).
- This keeps the costly, disconnect-prone crawl on the VM and the auth-dependent steps on the authorized Mac. (Optional future cleanup: ask EY to grant the VM identity `Storage Blob Data Contributor` so it can `az login --identity` and self-deploy — not needed for this run.)

## Folder model

```
crawl-archive/ (Blob)     <- site-raw-2026-06-24.tar.gz — PERMANENT frozen snapshot, offboard
site-raw/      (on VM)    <- CRAWL ONCE, then freeze (chmod -R a-w). Local source of truth.
   vale.com/indonesia/...        (EN, 83 pages + requisites + docs + depth-1)
   vale.com/in/indonesia/...     (ID, 83 pages + requisites + docs + depth-1)
site/          (working)  <- cp -a from site-raw (or extracted tarball). ALL patching here.
   vale.com/...
site-backup/ + old site/  <- RETIRED stale EN-only crawl; delete after new run verified
```

`deploy-azure.sh` expects `site/vale.com` — working folder matches that path, so the deploy script needs no path change.

---

## Phases

### Phase 0 — Pre-flight (cheap, local, before any VM)
- **0a. Confirm blob role** — verify Storage Blob Data Contributor on `stidstaticsite002` is granted (chase EY via Pak Purbayu if still pending). Blocks both upload and archive.
- **0b. HEAD sweep** all 166 URLs → confirm every one returns 200 (no 404/redirect surprises). ✅ **DONE 2026-06-24** (results: `docs/crawl-prep/headsweep-2026-06-24.tsv`): all 166 → 200, all `text/html`. Found + fixed 1 mislisted ID URL (`/indonesia/sejarah-vale-di-indonesia` → `/in/indonesia/sejarah-vale-di-indonesia`; the EN-locale path was bouncing it to the EN page). 0 remaining language drift. Confirms the rule: **ID pages live under `/in/indonesia/` only**.
- **0c. Build a new `crawl-site.sh`** — per-URL bilingual fetcher with depth+1. ✅ **DONE 2026-06-24, canary-tested.**
  - Two passes (EN then ID), **each with its own fresh cookie jar** → canary proved correct language per pass: EN page `<html lang="en-US">`, ID page `<html lang="in-ID">`. **Cookie separation works** (mitigates Rohman's language-cookie warning).
  - `wget -i <list> -r -l 1 --page-requisites --adjust-extension --convert-links --force-directories --restrict-file-names=windows` into `site-raw/`.
  - **Scoping (canary bug found + fixed):** dropped `--no-parent` (it scoped recursion to each seed's *directory*, making depth+1 inconsistent — deep ESG seeds got 1 page, shallow seeds got 58). Replaced with `--include-directories=/indonesia,/in/indonesia,/documents,/o,/-` + `--exclude-directories=` for the 13 foreign locales (`/ar/indonesia` … `/zh/indonesia`, NOT `/in`). After fix, ID seed expanded 1→14 pages, zero foreign-locale leakage.
  - `--reject-regex='(delta=|start=|[?@])'` drops the all-news pagination explosion + query-string variants.
  - `--wait=1 --random-wait`, polite UA, `-e robots=off`, tolerates wget exit 8.
  - Canary requisites confirmed: 18 CSS / 2 JS / 13 images fetched. Test artifacts cleaned up; `crawl-site.sh` + `canary-urls.txt` kept.
- **0d. Fix `postprocess.sh` root cause** — ✅ **DONE 2026-06-24.** Root cause found: section 9b's UUID-collapse did `mv one file; rm -rf parent_dir` per versioned file. When a human-filename dir (e.g. `image.png/`) held MULTIPLE versioned UUID files, it moved the first out then `rm -rf`'d the whole dir — **silently destroying the siblings.** The EN-only crawl hid it (every dir had 1 file); a bilingual crawl (ID+EN docs) makes multi-version dirs likely. NOTE: the "guest/global" framing in the old memory was imprecise — those dirs were never the direct target; the loss was in `documents/44618/...` multi-version dirs. **Fix:** extracted the logic to `collapse-documents.sh` (portable bash 3.2+), which keeps the highest version, preserves losing versions as `<name>.v<ver>`, and never `rm -rf`s a dir holding non-versioned content. Wired into postprocess.sh §9b. Regression test `docs/crawl-prep/test-collapse.sh` (multi-version → no data loss) PASSES; validated on real 1,178-file backup slice (542 `@version` collapsed, total preserved, guest/global intact).
- **0e. Provision VM** — B2s Linux in `rg-staticsite-dev`; install `wget`, `az`; clone repo / copy scripts + url lists; start work inside `tmux`.

### Phase 1 — Canary RESULTS (2026-06-24/25) — 3 bugs caught before the costly crawl
The canary did its job. Issues found + fixed while crawl was still cheap:
1. **crawl-site.sh `--no-parent`** scoped depth+1 to each seed's dir → deep ID seeds under-fetched (1 page vs 58). Fixed with `--include-directories`/`--exclude-directories`. ✅
2. **postprocess.sh was EN-only** — its flatten (§11) + `/[a-z]{2}/` strip (§2b) destroyed the ID `/in/indonesia/` structure. Created **`postprocess-bilingual.sh`**: no flatten (EN at /indonesia/, ID at /in/indonesia/), foreign-locale strip preserves `/in/`, `.html` append for both langs, root `index.html` → /indonesia.html. ✅
3. **crawl-site.sh reject-regex `(delta=|start=|[?@])` was too broad** — the `?`/`@` rejected EVERY document image (`/documents/.../img.jpg/<uuid>?version=1.0&t=...`), giving broken hero images sitewide. Canary deploy showed a hero image 404. Narrowed to `([?&](delta|start|cur|resetCur|_com_)=)` (pagination params only). Re-test: `documents/44618` went 0 → 175 files, the 404'd image now present. ✅

Canary deploy verified live on Azure dev `canary` container (private, via user-delegation SAS): EN page 200 `lang=en-US`, ID page 200 `lang=in-ID`, CSS `text/css`, both languages render. NOTE: the canary was deployed BEFORE fix #3, so its doc images were missing — the fix is validated by re-crawl, and the full Phase-2 crawl will include images from the start.

### Phase 1 (original plan) — Canary (validate the WHOLE pipeline on 2 pages, crawl still cheap)
Pick 1 EN + 1 ID page (e.g. an ESG flagship that exists in both).
1. Crawl just those 2 (real `crawl-site.sh`, tiny input) → temp snapshot.
2. Copy → working → run fixed `postprocess.sh` → `fix-filenames.sh` / `fix-mimetypes.sh` as needed.
3. Deploy to Azure dev (`deploy-azure.sh stidstaticsite002`).
4. **Verify live:** both pages render, correct language each, CSS/JS MIME correct (no `text/plain`), images load, an ESG page is the canary (per prod-deploy-checklist memory).
5. Fix any process bug NOW. Repeat canary until clean. **Only then** proceed.

### Phase 2 — Full crawl (the one costly run, on the VM in tmux) — DONE w/ gap 2026-06-25 00:16 UTC
- Ran `crawl-site.sh ./site-raw` over 166 URLs in tmux `fullcrawl` on vm-crawl-tmp (70.153.139.33). EXIT:0, 1815 files, 1.8 GB, 131 EN + 65 ID html, 907 doc images. site-raw preserved (NOT frozen — incomplete).
- **⚠️ ID GAP: 21 of 83 ID seeds incomplete.** EN = 0 missing. Cause: **language-cookie redirect contaminated the recursive ID pass** — depth+1 cross-links flip session language, so some ID seeds 301'd to EN. Breakdown: **15 saved under EN path** (`vale.com/indonesia/...`) + **6 truly absent**. List on VM: `~/vale/id-gap-21.txt`. (Canary missed this — only showed with depth+1 cross-contamination at scale.)
- **FIX APPLIED ✅ (2026-06-25):** `gap-crawl.sh` on VM — fetched the 21 URLs individually, NO recursion, fresh cookie jar each → all 21 landed under correct `/in/indonesia/` paths, all `lang="in-ID"` (verified 0 not-Bahasa). Removed 13 mis-filed EN-path copies, merged into site-raw. **Re-verify: 83/83 EN + 83/83 ID seeds present, 0 missing.** Totals: 1837 files, 1.8 GB, 907 doc images, 210 HTML. The no-recursion/fresh-jar approach is the reliable bilingual fetch (recursion is what flips the language).
- **⚠️⚠️ BIGGER BUG FOUND at patch time (2026-06-25): 82 of 83 EN pages contained BAHASA content.** My earlier "EN 0 missing" was a FALSE POSITIVE — I checked path-presence, not language-content. Root cause: the SAME cookie-via-recursion flip, but it hit the EN pass too. The EN pass ran first with a fresh jar, but depth+1 recursion followed `/in/indonesia/` language-switcher links early, the server set a Bahasa cookie, and every subsequent EN fetch redirected to ID content. (ID pass came second and stayed in-ID — lucky asymmetry.)
- **DECISIVE LESSON: this site cannot be recursively crawled bilingually.** Recursion follows the language-switcher links and flips the cookie. The ONLY reliable method is **per-URL, NO recursion, fresh cookie jar each** (`gap-crawl.sh`). The whole `crawl-site.sh` recursive/depth+1 design is unsafe here for language — depth+1 should be abandoned or done as a separate same-language-only pass.
- **FIX APPLIED:** re-fetched all 83 EN URLs with `gap-crawl.sh` (no recursion) → 83/83 now `en-US`. Merged over site-raw. **Full re-verify: EN 83/83 en-US, ID 83/83 in-ID, 0 bad.** 1855 files, 1.8 GB.
- **Frozen + archived (v2):** `site-raw-2026-06-25-v2.tgz` (1.7 GB, sha256 `86b94f90…46eb22be`). The earlier `-v1` (`82c5763f…`) on Mac is STALE (Bahasa EN) — discard it. Re-scp v2 to Mac.
- Resume/check: `ssh -i ~/.ssh/vale-crawl azureuser@70.153.139.33; tail ~/vale/crawl.log`
- Sanity: HTML count ≥ 166 (+ depth-1 extras + requisites); `find site-raw -path '*/in/indonesia*'` non-zero; both language trees present; documents present.
- **Freeze + archive immediately:** `chmod -R a-w site-raw`, then `tar czf site-raw-2026-06-24.tar.gz site-raw/` and `az storage blob upload` to private container `crawl-archive`. **This is the durability step — once the tarball is in Blob, the crawl can never be lost.** Snapshot is never touched again.

### Phase 3 — Patch (on working copy only)
- `cp -a site-raw/ site/` (re-copyable any time).
- Run fixed `postprocess.sh site/` (link rewriting, drop neutralization).
- Verify file counts: `site/` documents match `site-raw/` (postprocess fix held).
- Apply known patches from prior deploys: extensionless-link fixes, root-level links, Liferay burger-menu polyfill, learn-more button width — pull verified fixes already in repo history; don't re-derive.
- `fix-filenames.sh`, then deploy-time MIME handling.

### Phase 4 — Deploy to Azure dev (incremental)
- `./deploy-azure.sh stidstaticsite002 --fix-mime`
- First run uploads everything; thereafter **incremental** (upload-batch `--overwrite` only changes; do NOT `--delete-orphans` unless intentionally pruning).
- Explicit `--content-type` for CSS/JS (script already does this) and extensionless docs (`--fix-mime`).

### ✅ Phases 3–5 COMPLETE (2026-06-25) — bilingual site LIVE on Azure dev
- **Phase 3 patch:** v2 snapshot (checksum-verified, EN 83/83 en-US + ID 83/83 in-ID confirmed BEFORE patching) → `postprocess-bilingual.sh`: 871 doc names collapsed (0 loss), 0 leftover @version dirs, structure intact (118 EN + 86 ID html), 1857 files. Language re-verified AFTER patch: still 83/83 + 83/83.
- **Phase 4 deploy:** `deploy-azure.sh stidstaticsite002 --fix-mime` → `$web`. ~3400+ blobs.
- **Phase 5 verify LIVE** (https://stidstaticsite002.z45.web.core.windows.net):
  - EN `/indonesia/our-purpose-and-values.html` → 200, lang=en-US ✅
  - ID `/in/indonesia/esg/pengobatan-tradisional.html` → 200, lang=in-ID ✅
  - Landing pages: `/indonesia.html` en-US, `/in/indonesia.html` in-ID ✅; career both langs correct ✅
  - CSS → 200 text/css ✅; guest CSS → 200 text/css ✅
  - Doc images (the previously-404 hero) → 200 image/jpeg, both EN + ID pages ✅
  - index.html → meta-redirect to /indonesia.html ✅; bogus path → 404 ✅
- **VM can now be deallocated** (snapshot safe: v2 tarball on Mac `crawl-archive/`, sha `86b94f90…`). Delete VM after you're satisfied with the live site.

### Phase 5 (original plan) — Verify live on Azure dev
- Spot-check a sample across both languages: home (EN + ID), one deep ESG flagship each language, a doc download, news listing.
- Confirm: correct language served, MIME correct, images/CSS/JS load, internal links resolve within the mirror.
- Record the dev URL + checked pages. Report to user (and, if asked, to Vale).

### Phase 6 — Teardown
- Once Phase 5 is green: **delete the VM** (`az vm delete` + its disk/NIC/public-IP). The `crawl-archive` tarball in Blob remains as the permanent snapshot.
- Delete stale `site-backup/` and old `site/` locally to reclaim ~3.3 GB.
- Confirm `crawl-archive/site-raw-2026-06-24.tar.gz` is present and listed before deleting any local copy.

---

## Re-fix loop (the efficiency guarantee)
If Phase 4/5 surfaces a process bug:
```
fix the script  ->  restore working copy from snapshot  ->  re-patch  ->  re-deploy
```
- While VM still alive/deallocated: `rm -rf site && cp -a site-raw/ site/`.
- After VM deleted: pull `crawl-archive/site-raw-*.tar.gz` from Blob, extract, `cp -a` → `site/`.
The crawl is never re-run. Cost of any fix = copy/extract + patch + incremental upload only.

## VM cost & teardown discipline
- B2s ≈ a few cents/hour running; deallocated = disk-only (~pennies/day). Deallocate as soon as the crawl+archive finish; delete after verification. Do not leave it running idle.

## Open items / risks
- **News listing** (`all-news`) is dynamic/paginated — single-page snapshot only (documented limitation). Confirm with Vale whether paginated archive is in scope or Opsi-B.
- **Content-restructuring instructions** in the sheet (merge Investor Publications, combine Karier sub-pages) — treated as Opsi-B (post-live), not this clone. Confirm if challenged.
- Asset requisites may live on non-`vale.com` hosts; canary will reveal if `--domains` needs widening.
- Disk: `site-raw` + `site` ≈ 3+ GB alongside existing `site`/`site-backup` (~3.3 GB). Ensure headroom; retire `site-backup` after validation.

## Deliverables
- `crawl-site.sh` (new per-URL bilingual fetcher)
- Fixed `postprocess.sh`
- `site-raw/` frozen snapshot
- Deployed bilingual site on Azure dev (`stidstaticsite002`)
- Verification record
