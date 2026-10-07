# Website Support Bot — PTVI-Tenant Deployment Design

**Date:** 2026-10-07
**Status:** Design (for Vale IT review)
**Requested by:** Purbayu — deploy the proven bot natively in the **PTVI (valeindonesia.com)** tenant.

> **Context.** The bot is already **built, live, and proven** as a PoC in the **PTGDI** tenant
> (as-built: `docs/website-support-bot-runbook.md`; original design:
> `docs/plans/2026-09-15-teams-pipeline-vm-design.md`). That PoC spans two tenants: the bot +
> Teams + request library in PTGDI, COMMs as **guests**, deploying to a **PTGDI-owned
> workaround storage** because the cross-tenant Vale storage grant never landed.
>
> **This design moves the entire solution into the PTVI tenant.** Everything — VM, Azure Bot,
> app registration, Key Vault, the COMMs AAD group, and the deploy target — lives in PTVI.
> **There is no cross-tenant component.** This removes every cross-tenant seam that caused
> pain in the PoC.
>
> **Scope: pure Azure Bot, no third-party LLM.** This phase uses **only Microsoft/Azure
> services** — the bot runs the deterministic intent parser (`bot/agent.py`, as the PoC
> already does). **No Anthropic / Claude API is wired in this phase** (no Anthropic key, no
> `api.anthropic.com` egress, no Anthropic commercial/data-egress review). The intent parser
> is the brain; swapping in an LLM later is a separate, optional phase.

---

## 1. What changes vs. the PoC

The *shape* is identical to the proven PoC; only the tenancy collapses from two tenants into one.

```
COMMs (native PTVI users) ──> Existing Vale Teams/SharePoint intake library
       "Valeindonesia.com Update - Request"  (1-Submitted / 2-In-Progress / 3-Done-Deployed)
          │
          │  Microsoft Graph (same-tenant, as VM managed identity)       Bot Framework
          ▼                                                                    ▲
   ┌──────────────────── Azure VM (PTVI tenant) ────────────────────────────┴──────┐
   │  nginx TLS 443 → aiohttp :3978  →  intent parser  →  operator (deterministic)  │
   │     detect → dry-run → apply → build → deploy dev → verify                     │
   └───────────────────────────────┬────────────────────────────────────────────────┘
                                    │  az blob (SAME-tenant, as MI — no cross-tenant RBAC)
                                    ▼
                    Vale dev storage  stidstaticsite002   (prod gated/manual for now)
```

**What disappears vs. the PoC:**

| PoC pain point | Status in PTVI deployment |
|---|---|
| Cross-tenant storage RBAC grant (the #6 blocker — never landed) | **Gone** — MI and storage are in the same tenant |
| B2B guest invites + the Teams **org-switch** stumbling block | **Gone** — COMMs are native PTVI members |
| Flaky cross-tenant MI→Graph app-role token propagation (forced app-reg client-creds fallback) | **Gone** — same-tenant MI tokens carry app-roles reliably |
| Guest-object-ID churn silently locking users out of auth | **Gone** — native users, stable object IDs |
| Sponsorship-sub VM-SKU restriction → FX2ms_v2 **~$225/mo** | **Gone** — cheap **B-series** VM (~$30/mo) |
| PTGDI-owned workaround storage `stptviwebbot` | **Gone** — deploy straight to Vale's real dev storage |

**What stays identical (reused unchanged):** the bot/operator code, the four request types
(news / vacancy / awards / documents), the dry-run → dev → approve → prod flow, rollback
(plain + targeted), the ops dashboard, and Layer-2 AAD-group authorization.

---

## 2. Identity & auth — one managed identity, all same-tenant

**A single system-assigned managed identity on the VM is the whole auth story.** Because
everything is now same-tenant, this is dramatically simpler than the PoC (which needed
app-registration client-credentials as a workaround for flaky cross-tenant MI token
propagation — commit `e1142d8`).

The VM's managed identity gets four grants, **all within PTVI**:

| Grant | Scope | Purpose |
|---|---|---|
| **Storage Blob Data Contributor** | `stidstaticsite002` (dev) | Deploy the built site — *same-tenant now, no cross-tenant RBAC* |
| **Key Vault Secrets User** | `kv-vale-webbot` (new, PTVI) | Read the bot app-password at startup |
| **Graph `Sites.Selected`** (or `Files.ReadWrite.All`) | existing Vale intake SharePoint site | Read request folders + move them across stage folders |
| **Graph `GroupMember.Read.All`** | tenant | Check sender ∈ `Vale-Website-COMMs` AAD group |

**Key simplification:** in a single tenant, Graph app-role propagation into MI tokens is
reliable, so the MI performs both the SharePoint **reads** and the **folder moves**. The
PoC's `_app_token()` client-creds path is kept as a defensive fallback but is **not
load-bearing** here.

**Sender authorization (Layer 2, unchanged, load-bearing).** Every Teams message carries the
sender's verified AAD object ID. The operator checks membership in the PTVI AAD group
**`Vale-Website-COMMs`** via Graph, and **refuses non-members** for both *process* and
*approve*. Native users mean **no guest-object-ID churn** — another PoC lockout gotcha that
disappears.

**Token-cache gotcha still applies.** After granting a new Graph app-role to the MI, you must
**deallocate + start** the VM — a warm reboot does *not* flush the IMDS token cache (~24h).

---

## 3. Azure Bot, Teams app & scoped distribution

**Azure Bot + app registration, both single-tenant to PTVI.** COMMs reach the bot as native
members — the supported happy path for single-tenant Bot Framework (vs. the PoC's guest
workaround).

- **App registration** `vale-website-support-bot` in PTVI Entra, `signInAudience:
  AzureADMyOrg`. **PoC lesson baked in:** after `az ad app create` you *must* also
  `az ad sp create --id <appId>` — otherwise the bot receives messages but cannot reply (the
  201-then-401 reply-token failure, AADSTS7000229).
- **Azure Bot resource** `vale-website-support-bot` (F0 free tier), MS Teams channel enabled,
  messaging endpoint `https://<vm-fqdn>/api/messages`. The app-password secret goes straight
  into `kv-vale-webbot` — never on disk.

**Teams app distribution — scoped to COMMs, NOT org-wide.** The PoC pinned the app via the
**Global (org-wide default)** setup policy. That is **deliberately not used here**: PTVI is
Vale's real corporate tenant, and the Global policy would pin the bot in *every* employee's
Teams bar. Instead:

1. Package the manifest (reuse `deploy/teams-app/`, swap `externalId` / bot app ID to the new
   PTVI appId).
2. Vale Teams admin uploads it to the **org catalog** (status Unblocked).
3. **Create a dedicated custom Teams app setup policy** (not Global) that pins the bot, and
   **assign that policy to the `Vale-Website-COMMs` group** (or the COMMs members
   individually).
4. Result: the bot auto-appears in the Teams bar **for COMMs only**; every other PTVI
   employee never sees it.

Distribution/discovery scoping is layered on top of — and independent from — the Layer-2
auth, which already refuses any non-COMMs sender regardless of how they discover the bot.

---

## 4. VM, hosting & operations

A small Linux VM in PTVI — a lift-and-shift of the proven PoC host, but on a cheap B-series
(no Sponsorship-sub SKU restriction).

| Piece | Spec |
|---|---|
| VM | `vm-vale-website-bot`, Ubuntu 22.04, **B2s** (2 vCPU / 4 GB, ~$30/mo), system-assigned managed identity |
| Resource group | new **`rg-vale-website-bot`** (dedicated, so GDI's delegated rights scope to it) |
| TLS | nginx terminates 443 → aiohttp `127.0.0.1:3978`; Let's Encrypt on the VM FQDN (auto-renew) |
| Service | systemd `vale-bot.service` (enabled, auto-restart, auto-start on boot) |
| Startup | `run-bot.sh`: MI login → pull `bot-app-password` from Key Vault → export env → start |
| Secrets | **none on disk** — Key Vault + managed identity only |
| On the VM | `~/vale-bot/` : `repo/` (scripts + `operator/` + `bot/` + `site-data/` + ~4.3 GB `site/` mirror), `venv/`, `run-bot.sh` |

**Networking (NSG):** inbound 80 + 443 (public, for Teams/Bot Framework + Let's Encrypt),
SSH 22 restricted to GDI's IP(s). No other ingress. Outbound to Microsoft Graph and the Vale
storage endpoints only (no third-party API egress in this phase).

**Cost posture: always-on.** On a real (non-sponsored) subscription the B2s cost is trivial
(~$30/mo), so the VM runs **24/7** — no auto-shutdown, removing the PoC's "start the VM each
morning" operational quirk that the expensive FX VM had forced.

**Ops (same as the runbook):** `systemctl status/restart vale-bot`,
`journalctl -u vale-bot`, `operator-audit.log` (one JSON line per run + auth event), the
token-gated `/dashboard`. **Redeploy code:** rsync `operator/` + `bot/` → `~/vale-bot/repo/`
→ `systemctl restart vale-bot`.

---

## 5. Request flow, failure handling & prod gate

The flow is unchanged from the PoC, now reading the **existing** Vale intake SharePoint
library (no new team, no re-bookmarking for COMMs):

1. COMMs (native PTVI members) drop a request folder in the existing `1-Submitted/`.
2. COMMs: **`what's pending?`** → bot lists `1-Submitted` items, each with a **Process** button.
3. **`process the request`** → operator reads via Graph → detect type → dry-run → apply →
   build → **deploy dev** → verify (HTTP 200 + content grep on **each** changed URL) → folder
   moves `1-Submitted → 2-In-Progress`. Bot posts a card with dev preview links.
4. COMMs reviews on dev; spot a typo → **`rollback`** → fix the JSON → **`process`** again
   (re-publishing is blocked by the duplicate-slug gate *without* a rollback first).
5. **`approve`** → **gated/stubbed for now** — prod is wired later (see below).

**Four request types (all working from the PoC):** news (article + all-news listings,
data-driven), vacancy (career.html EN+ID, HTML-direct), awards (awards/penghargaan,
HTML-direct), documents (documents-and-reports, data-driven). Bespoke page edits
(`content-*.json`) remain a **manual GDI step** — not auto-handled.

**Guardrails (carried over):** dev automatic / prod explicit-approval-only; dry-run before
every apply; deterministic deploy path (no LLM writes); single-writer lock (one request at a
time); verify-after-deploy surfaced never hidden; Layer-2 group auth on both *process* and
*approve*.

**Failure path (dev):** on dev-verify failure the bot **alerts and stops** (reports the
failing URL), leaving the request in `2-In-Progress` for GDI to inspect — no silent partial
state. Rollback is the correction path: data-driven types surgically remove the record(s) by
slug/id + rebuild; HTML-direct types restore the page snapshot; manifests in
`.operator-rollback/`.

**Prod — dev-first, deferred.** Per decision, this deployment wires **dev only**
(`stidstaticsite002`). Prod (`stidstaticsiteprod`) stays manually deployed by GDI/Feiry until
the flow is trusted; the MI gets dev-only RBAC. Wiring prod later requires: MI
`Storage Blob Data Contributor` on `stidstaticsiteprod`, two constants in
`operator/deployer.py` (`PROD_ACCOUNT`, `PROD_WEB_BASE` — already present), un-stubbing
`approve` in `bot/app.py`, and resolving the **prod verify-failure policy** (auto-rollback vs.
alert-only — an open decision from the original design, resolved at prod-wiring time, not now).

---

## 6. What PTVI (Vale) must provide to GDI

GDI provisions the stack under **delegated rights** (same operational model as the PoC build).
So the PTVI-side work is a list of **grants, consents, and admin actions** Vale performs;
everything else GDI builds. Grouped by privilege level / owner:

### A. Azure subscription / RBAC — *Vale subscription Owner or UAA holder*
1. **Create (or designate) a resource group** `rg-vale-website-bot` in the Vale subscription.
2. Grant **Feiry/GDI `Contributor` + `User Access Administrator`** scoped to **that RG only** —
   lets GDI build the VM / Key Vault / NSG and self-assign the MI's roles without tenant-wide
   power. *(Likely review point.)*
3. Grant the **VM managed identity `Storage Blob Data Contributor` on `stidstaticsite002`**
   (dev storage) — the one grant outside the dedicated RG. (Doable by GDI if the storage
   account is in scope of the UAA grant; otherwise Vale assigns it directly.)

### B. Entra / Identity — *Global Admin or Privileged Role Admin*
4. Allow GDI to **create the app registration + service principal**
   `vale-website-support-bot`, or create it and assign GDI as owner.
5. **Admin-consent** the Graph application permissions: `GroupMember.Read.All`, and
   `Sites.Selected` (or `Files.ReadWrite.All`) on the intake site. *App-role grants are
   GA-only — can't be self-consented.* *(Likely review point.)*
6. **Create the AAD group `Vale-Website-COMMs`** and populate it with the COMMs members —
   this is the authorization roster.

### C. Teams Admin
7. **Upload the Teams app** to the org catalog (status Unblocked).
8. **Create a custom Teams app setup policy** that pins the bot, **assigned to
   `Vale-Website-COMMs` only** (NOT the Global default policy).

### D. SharePoint / Graph
9. **Grant the MI/app `Sites.Selected` to the existing intake SharePoint site** (the
   `Valeindonesia.com Update - Request` library) — read + move-folder across stage folders.

### E. Networking / egress
10. Confirm the VM subnet allows **outbound** to Microsoft Graph and the Vale storage
    endpoints. (No third-party API egress in this phase.) Inbound limited to 80/443
    (public) + 22 (GDI IP).

**Everything else — VM, nginx/TLS, systemd, Key Vault contents, bot/operator code, the site
mirror, the Teams manifest packaging — GDI does.**

**Two most likely Vale-review points:** item **#2** (`User Access Administrator` on the RG)
and item **#5** (Graph admin-consent). If Vale security declines standing UAA for GDI, the
fallback is **co-owned provisioning** — Vale assigns the MI's roles itself and GDI gets plain
`Contributor` — at the cost of a few more Vale-IT round-trips during build.

---

## 7. Migration from the PoC

- **Code is done and proven** — `operator/`, `bot/`, the `intake-to-*` / `build-*` scripts,
  rollback, and the dashboard move to the PTVI VM **unchanged**.
- **New build = infra + wiring only:** stand up the PTVI VM / Key Vault / NSG, create the
  PTVI app registration + Azure Bot, point `deployer.py` (`DEV_ACCOUNT`, `DEV_WEB_BASE`) and
  `bot/app.py` (`DEV_BASE`) at `stidstaticsite002`, set the env for the new
  `Vale-Website-COMMs` group + the existing intake SharePoint site, upload + scope the Teams
  app.
- **The PTGDI PoC can be decommissioned** once PTVI is verified live (or kept briefly as a
  fallback).

## 8. What stays the same for COMMs

Same forms, same folder structure (`1-Submitted` → review → done), same approve-the-preview
step, and — because we **reuse the existing Vale intake SharePoint** — the **same library
location** (no re-bookmarking). The visible improvements vs. the PoC: COMMs work entirely in
**their own Vale Teams** as native members (no guest invite, no org-switch), and the bot
appears automatically in the Teams bar for the COMMs group.
