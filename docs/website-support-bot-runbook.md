# Website Support Bot — As-Built Runbook

**Status:** PoC live & in testing (2026-09-23). Design: `docs/plans/2026-09-15-teams-pipeline-vm-design.md`.

A Microsoft Teams bot that lets the COMMs team publish valeindonesia.com updates
(news / documents / vacancies) via chat, with a dev-preview + approval gate. Runs on an
Azure VM in the **PTGDI** tenant; deterministic operator wraps the existing
`intake-to-*.py` / `build-*.py` scripts.

## Architecture (as built)

```
Teams (chat or channel @mention)
  │  Bot Framework (single-tenant app 119b0d4b…)
  ▼
Azure Bot  ──►  VM aiohttp listener (nginx TLS 443 → 127.0.0.1:3978)
                  │  Layer-2 auth: sender AAD id ∈ PTVI-Website-COMMs (Graph, as MI)
                  ▼
                Claude/intent brain (parse_intent) → decides WHEN
                  ▼
                Operator (deterministic): detect → dry-run → apply → build → deploy → verify
                  │  reads request folder from SharePoint (Graph, as MI)
                  ▼
                dev static-website storage  (bot deploys as the VM managed identity)
```

## Live resources (all in PTGDI Sponsorship sub)

| Thing | Value |
|---|---|
| Subscription | `9f6d9916-4ce6-4369-9ebe-c55c1574cc81` (Microsoft Azure Sponsorship) |
| Tenant | `9b861f04-0916-485b-af37-b28a7fa65dc1` (ptgdi.com) |
| Resource group | `rg-ptvi-website-bot` (Southeast Asia) |
| VM | `vm-ptvi-website-bot` — **FX2ms_v2** (see cost note), IP `4.194.68.44` |
| FQDN | `ptvi-webbot-gdi.southeastasia.cloudapp.azure.com` (Let's Encrypt TLS, auto-renew) |
| VM managed identity | principalId `877868e9-fd18-4f8b-9699-58e0d372ffa2` |
| Key Vault | `kv-ptvi-webbot` (secret `bot-app-password`) |
| Dev storage | `stptviwebbot` → `https://stptviwebbot.z23.web.core.windows.net/` |
| Azure Bot | `ptvi-website-support-bot`, app `119b0d4b-3785-4631-860b-e30696ab299c` (single-tenant) |
| Access group | `PTVI-Website-COMMs` = `40c7a9b2-4f7d-4911-a969-192c4670a854` |
| Request library | Teams team `Valeindonesia.com Update - Request`, M365 group `2f4138c3-a317-4e19-a766-80e71e81132f` |
| SSH key | `~/.ssh/ptgdi-website-bot-vm` (user `azureuser`) |

### Managed-identity permissions (the auth model)
The bot authenticates as the VM's system-assigned managed identity — no secrets on disk:
- **Key Vault Secrets User** on `kv-ptvi-webbot` (reads the bot password)
- **Storage Blob Data Contributor** on `stptviwebbot` (deploys the built site)
- **Graph GroupMember.Read.All** (checks PTVI-Website-COMMs membership)
- **Graph Files.ReadWrite.All** (reads the SharePoint request library + moves request folders across stage folders)

## On the VM (`~/ptvi-bot/`)
- `repo/` — this repo's scripts + `operator/` + `bot/` + `site-data/` + `site/` (4.3GB mirror)
- `venv/` — Python venv with the Bot Framework SDK
- `run-bot.sh` — MI login → pull secret from Key Vault → export env → start aiohttp
- systemd unit `ptvi-bot.service` (enabled, auto-restart, auto-start on boot)
- nginx site `ptvi-bot` (TLS terminate → localhost:3978)

## Operations

**Start the VM (it auto-shuts-down 19:00 WIB daily):**
```
az vm start -g rg-ptvi-website-bot -n vm-ptvi-website-bot --subscription 9f6d9916-4ce6-4369-9ebe-c55c1574cc81
```
Bot auto-starts on boot; FQDN/IP persist. ~1 min to live. (Auto-shutdown emails feiry+peter 15 min prior.)

**SSH in:**
```
ssh -i ~/.ssh/ptgdi-website-bot-vm azureuser@4.194.68.44
```

**Health / logs (on VM):**
```
sudo systemctl status ptvi-bot
sudo journalctl -u ptvi-bot -n 50 --no-pager
tail ~/ptvi-bot/repo/operator-audit.log      # one JSON line per run + auth event
```

**Redeploy code changes:** rsync `operator/` and `bot/` from repo → `~/ptvi-bot/repo/`, then
`sudo systemctl restart ptvi-bot`.

**Add a tester:** add their AAD user to group `PTVI-Website-COMMs` (`az ad group member add
--group 40c7a9b2… --member-id <oid>`) AND to the Team; they then use 1:1 chat or channel @mention.

## Bot commands (Teams)
- `help` — list commands
- `what's pending?` — list requests in SharePoint `1-Submitted` (each with a Process button).
  Processed requests move to `2-In-Progress` and drop off this list; rollback moves them back.
- `process the request` — build the pending request + deploy to dev preview (+ preview links).
  Handles all four request types: **news** (article + all-news listings), **vacancy**
  (career.html EN+ID), **awards** (awards/penghargaan pages), **documents** (documents-and-reports
  / dokumen-dan-laporan). News & documents are data-driven (JSON→build); vacancy & awards edit
  the HTML pages directly.
- `rollback` (or `undo`) — undo the LAST processed request. This is the **typo-correction path**:
  process → spot typo on the dev preview → `rollback` → fix the request JSON in SharePoint →
  `process` again (re-publishing is blocked by the duplicate-slug gate WITHOUT a rollback first).
- `rollback <request-id>` (e.g. `rollback sp-demo-news`) — undo a SPECIFIC request regardless of
  order, preserving newer ones. Data-driven types remove only that request's record(s) by slug/id
  (surgical) so other requests survive; HTML-direct types restore that request's page snapshot.
- `approve` — gated in the test build (prod not wired; shows an explanatory message).

Rollback internals: each successful deploy writes a manifest to `.operator-rollback/`
(pre-run snapshot + deployed blob paths). Two restore modes by type: **data-driven** (news,
documents) restore the JSON snapshot + rebuild; **HTML-direct** (vacancy, awards) restore the
edited pages from a page snapshot. Then re-deploy the restored pages (re-upload) or delete
blobs that no longer exist locally (e.g. a rolled-back news article), and archive the manifest
(`.done`) so it can't double-undo. Dev-scoped, COMMs-triggerable, single-writer locked.

## Gotchas (learned the hard way)

- **Sponsored subs block cheap VMs.** B/D/E general-purpose SKUs return `NotAvailableForSubscription`
  on Azure Sponsorship subs (MS policy). Only FX (and DC/EC) families deploy → we run **FX2ms_v2
  ~$225/mo** (from credit). Auto-shutdown halves effective compute cost. A serverless rebuild
  (Container Apps) would be far cheaper if this goes permanent.
- **MI token cache.** After granting a new Graph app-role, the IMDS token is cached (~24h) and a
  *warm reboot doesn't flush it* — must **deallocate + start** the VM. (Fresh VMs are fine.)
- **Graph app-role grants** must be run by a human (GA) — the tooling blocks them as tenant-level
  IAM. `checkMemberGroups` on another user needs User.Read.All; we use `GET /groups/{id}/members`
  instead, which works with just GroupMember.Read.All.
- **Extensionless images** in the site mirror upload as `application/octet-stream` → broken icons.
  After any full-mirror upload, re-set content-type on extensionless `/documents/**` files
  (detect via `file -b --mime-type`). ~871 files, mostly SVG.
- **Incremental deploy** = only the changed article/listing pages upload per request; the rest of
  the site must be uploaded once (done). A fresh article renders unstyled until that's in place.
- **Module name:** the operator file MUST be `operator_svc.py`, not `operator.py` (shadows stdlib).
- **Channel use requires @mention** every message (Teams routing); 1:1 chat does not. Both work.

## Pending / future

- **Vale storage grant (#6):** to publish to Vale's *real* dev site, Vale IT must grant the MI
  (`877868e9…`) **Storage Blob Data Contributor** on `stidstaticsite002`. Then change 2 constants
  in `operator/deployer.py` (`DEV_ACCOUNT`, `DEV_WEB_BASE`) + `bot/app.py` (`DEV_BASE`). Emailed
  Purbayu 2026-09-22, awaiting.
- **Prod deploy** is intentionally gated (dev preview is the end of the flow in the test build).
- **Claude agent brain:** `bot/agent.py` is a deterministic intent parser today; swappable for a
  real Claude agent (needs an Anthropic key in Key Vault) without touching bot/operator wiring.
