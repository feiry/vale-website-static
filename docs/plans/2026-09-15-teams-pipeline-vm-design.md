# Website Update Pipeline — Azure VM + Teams Design

> **Built & live (2026-09-23).** This is the original design; for the AS-BUILT state
> (actual resource IDs, ops commands, gotchas, cost notes), see
> **`docs/website-support-bot-runbook.md`**. Notable deviations from this plan: hosted on a
> PTGDI **Sponsorship** subscription (not a fresh VM in Vale's tenant), running an **FX2ms_v2**
> VM because sponsored subs block cheap B/D SKUs, deploying to **PTGDI** dev storage until the
> Vale cross-tenant grant lands.


**Date:** 2026-09-15 (updated 2026-09-21)
**Status:** Design (approved in principle by Feiry; for Sandy / IT / EY review)

> **Hosting update (2026-09-21):** Both the **Azure Bot AND the Teams channel** now live
> in the **PTGDI tenant**. COMMs users are **invited as guests into a PTGDI Team** rather
> than the bot being sideloaded into a Vale-owned Team. This keeps the bot single-tenant
> (PTGDI-only), removes the cross-tenant Teams-app-install dependency on Vale IT, and means
> the request channel + SharePoint library are PTGDI-owned. Access control and several open
> questions below are revised accordingly.
**Supersedes:** the earlier Mac + Telegram + OneDrive-mirror sketch (rejected — Telegram
is not company-standard, and macOS TCC blocks a background process from reading
`~/Library/CloudStorage` reliably).

## Why this shape

Moving the operator to an **Azure VM in the PTGDI tenant** and talking over **Microsoft
Teams** removes every constraint we hit on the Mac and matches company standards:

- No macOS TCC / OneDrive file-access problem — a VM reads files via Microsoft Graph.
- A real always-on host with a public HTTPS endpoint (required by the Teams Bot Framework).
- One PTGDI Azure AD identity for the bot and the file reads; the storage deploys use a
  cross-tenant grant onto Vale's storage (the one Vale-side dependency — see Q2).
- Company-standard (Teams, Azure), IT-approvable.

## Architecture

```
COMMs (guests) ──> PTGDI Teams channel "Valeindonesia.com Update - Request"
          SharePoint doc library (PTGDI): _Templates / 1-Submitted / 2-In-Progress / 3-Done-Deployed
             │
             │  Microsoft Graph API (app identity)         Teams Bot Framework
             ▼                                                    ▲
     ┌────────────────────────── Azure VM (PTGDI tenant) ────────┴──────────┐
     │  Teams Bot endpoint  ──►  Claude agent (conversation only)           │
     │                              │ decides WHEN                          │
     │                              ▼                                       │
     │  Operator service (deterministic):                                   │
     │    read request (Graph) → detect type → intake → build → deploy      │
     │    dev  →  (await approval)  →  deploy prod                          │
     │    workflow scripts: intake-to-*, build-*, vacancy tools (this repo) │
     └───────────────────────────────┬──────────────────────────────────────┘
                                      │ az / Graph (cross-tenant RBAC onto Vale storage)
                                      ▼
        Vale tenant:  dev storage (stidstaticsite002)   prod storage (stidstaticsiteprod)
```

### Components

1. **Teams Bot** (Azure Bot registration; endpoint on the VM). Carries the conversation:
   COMMs/GDI type "process the loker request", "what's pending?", "deploy prod". Posts
   status + preview links back into the Teams channel (Adaptive Cards with an Approve button).

2. **Claude agent (conversation brain).** Interprets messages, decides which request and
   when to act, confirms the prod gate, writes the human replies. **Does not deploy itself**
   — it calls the operator service. Runs headless via Claude Code / Agent SDK on the VM.

3. **Operator service (deterministic, auditable).** A Python service exposing
   `process(request_id, target=dev|prod)`:
   - reads the request folder from SharePoint via **Graph** (JSON + attachments),
   - detects type (`*-news.json` / `*-doc.json` / `*-vacancy.json` / `content-*.json`),
   - runs the matching **existing** workflow (dry-run → apply → build),
   - deploys to dev or prod storage (az / Graph), verifies (HTTP 200 + content check),
   - returns a structured result. No LLM in this path.

4. **Workflow scripts** — unchanged from this repo (intake-to-news/doc/vacancy,
   build-news/doc-library, page inject, rollback-vacancy). They already validate,
   back up, self-check, and are dry-run-first.

### Identity & auth (one Azure AD app)

- **Graph**: `Sites.Selected` scoped to the one **PTGDI-owned** request library to
  list/read/`3-Done` move. Consent is granted by a **PTGDI admin** (same tenant as the app)
  — no cross-tenant Vale grant needed.
- **Storage**: Storage Blob Data Contributor on dev + prod accounts (prod via PIM or a
  dedicated deploy identity — TBD with IT; PIM's human-MFA model may not suit an unattended
  VM, so a scoped managed identity for prod deploys is likely cleaner. This is the **one
  remaining cross-tenant grant**: the PTGDI principal still needs RBAC on Vale's storage
  accounts. **Open question.**)
- **Bot**: Azure Bot resource in PTGDI; **single-tenant** (PTGDI-only) is now sufficient
  since COMMs join as PTGDI guests. VM holds the app password / cert.

## Flow

1. COMMs (as PTGDI guests) drop a request folder in the PTGDI Teams `1-Submitted/`
   (unchanged authoring; same forms).
2. COMMs/GDI: **"process the loker request"** in the Teams channel.
3. Agent → operator: read via Graph → detect → dry-run → apply → build → **deploy dev** →
   verify. Agent posts an Adaptive Card: *"On dev: <preview links>. [Approve for prod]"*.
4. **Requester approves** (card button or "deploy prod"). Agent → operator: **deploy prod**
   → verify. Agent posts *"Live: <urls>"*.
5. Folder moved to `3-Done-Deployed/` (Graph move, or human — TBD).

## Guardrails (autonomous, shared VM, touches prod)

- **Dev automatic; prod only on explicit human approval** (card button / message).
- **Dry-run before every apply**; any validation error stops and reports.
- **Deploy path is deterministic** (operator service), not the LLM — full audit log per action.
- **Verify after every deploy** (200 + content grep); failures surfaced, never hidden.
- **Authorized approvers only** — verified by `PTVI-Website-COMMs` AD-group membership
  (not merely channel presence) — can trigger prod.
- **One request at a time**, tracked; no double-deploy.
- **Least-privilege identity**; prod deploy credential scoped and logged.

## Access control — only the COMMs team can use the bot

The `ptvi-website-support` bot must be usable **only by the COMMs team**, not anyone in
the Vale tenant. Enforced in two independent layers (defense in depth):

**Layer 1 — Teams-side scoping (PTGDI controls).**
- The bot lives in a **single PTGDI Team/channel** ("Valeindonesia.com Update – Request");
  COMMs join that Team as **guests (B2B)**. Only members + invited guests of that Team can
  message the bot; the bot is single-tenant to PTGDI and isn't exposed to Vale's tenant at
  large. **PTGDI (not Vale IT)** now controls who is invited as a guest.
- Guest invitations are the roster control: only the specific COMMs people PTGDI invites
  get into the channel. This replaces the previous "Vale Teams admin sideloads the app +
  app-permission policy" step.
- **Note:** guests cannot install Teams apps themselves, so a **PTGDI member** (team owner)
  installs the `ptvi-website-support` app into the team once; guests then message it normally.
  Also requires **guest access enabled** in the PTGDI Teams admin center + **external
  collaboration** allowing the invites (see Q4).

**Layer 2 — Operator-side verification (our code enforces — the load-bearing layer).**
Even inside the channel, the operator **verifies the sender's identity on every message**
before acting — Teams/Bot Framework supplies each message's **verified Azure AD identity**
(sender AAD object ID / email, including the guest identity), which cannot be spoofed. The
operator:
- Checks the sender against an **authorized-COMMs allowlist** — implemented as membership
  of a **PTGDI-side Azure AD group** (`PTVI-Website-COMMs`) that lists the invited COMMs
  guests, checked via Graph. Because the group lives in PTGDI (same tenant as the app), the
  membership read is **same-tenant** — no cross-tenant Graph consent needed. GDI manages the
  roster in one place with no code change.
- **Refuses** any sender not in the group ("You're not authorized to submit website requests").
- Applies the check to **both** actions: **submitting/processing** a request AND
  **approving prod** — a non-member can neither trigger a build nor authorize go-live.

**Why both layers:** Layer 1 can be misconfigured (a wrong guest invited, someone added to
the channel by mistake); Layer 2 is an independent, code-level gate so an LLM-driven agent
never processes or deploys on an unverified request. Every accepted and refused request is
logged with the sender identity for audit.

## Runtime & cost model

The three components have different lifecycles — this matters for cost and sizing:

| Component | Runs | Notes |
|-----------|------|-------|
| **Teams Bot endpoint** | **Always on (idle)** | A small HTTPS listener must be up 24/7 so Teams can reach the bot. Near-zero CPU when no one is messaging — it just waits. This is the only true always-on process. |
| **Claude agent** | **Triggered per message** | Spun up when a Teams message arrives, handles that request, then stops. Not a persistent "thinking" process. |
| **Operator service** | **Triggered on demand** | Runs only when the agent calls it to process/deploy. Idle otherwise. |

**Key point: the VM is always on, but Claude is NOT always running.** Claude is invoked
by Teams messages, does its work, and stops. It consumes tokens (= cost) **only while
actually processing a request** — idle time is free.

**Cost shape:**
- **VM** — the only fixed 24/7 cost. A small Linux VM is sufficient (the workload is light,
  bursty, mostly idle). Est. ~US$15–40/mo depending on size (confirm with IT).
- **Anthropic API** — **pay-per-use**, billed only on real request-processing. A handful of
  news/document/vacancy requests a day is a small, usage-proportional cost; no idle charge.
- **Graph / Azure Storage** — negligible (a few API calls + small blob uploads per request).

**Trigger model (two viable options, decide at build time):**
- **Ephemeral** — each Teams message launches a fresh Claude agent that reads state, acts,
  and exits. Zero idle Claude footprint; each request starts "cold" (re-reads context).
- **Warm session** — a lightweight Claude session stays resident for conversational
  continuity. The process is alive but only spends tokens when a message is actually handled.

Either way, **you pay for Claude only when it processes a request, never for waiting.**

## Open questions (for IT / EY / Sandy)

> **Note on hosting (updated 2026-09-21):** the VM, Azure Bot, app registration, **and the
> Teams channel + SharePoint request library** all live in the **PTGDI tenant**. COMMs are
> invited as **guests** into the PTGDI Team. Vale no longer installs a Teams app; the only
> remaining Vale-side grant is cross-tenant **storage RBAC** for prod/dev deploys (Q2). This
> removes both the Anthropic-egress-in-Vale-tenant blocker Sandy raised and the cross-tenant
> Teams-app-install + cross-tenant Graph-consent dependencies.

1. **VM (PTGDI tenant)**: size, OS (Linux preferred), subscription/RG, network egress to
   valeindonesia.com + Anthropic API + Graph. Light/bursty/mostly-idle (see Runtime & cost
   model) — a small VM suffices; confirm monthly budget.
2. **Prod deploy identity (cross-tenant)**: the GDI VM/service principal needs
   Storage Blob Data Contributor on Vale's `stidstaticsiteprod` / `stidstaticsite002`.
   Options: Vale grants the GDI principal cross-tenant RBAC on those accounts, or reuse the
   existing GDI-authorized deploy path. PIM (human-MFA) doesn't fit an unattended VM —
   **recommend a scoped service principal; needs Vale IT sign-off.**
3. **Azure Bot registration** in PTGDI (**single-tenant** bot + single-tenant app
   registration — cross-tenant messaging no longer needed since COMMs join as PTGDI guests)
   + who owns it.
4. **PTGDI Team + guest invitations**: create the PTGDI Team/channel
   "Valeindonesia.com Update – Request" and its SharePoint library; PTGDI invites the COMMs
   members as **guests (B2B)**. Confirm Vale allows its users to accept PTGDI guest invites
   (Vale outbound / PTGDI inbound cross-tenant-access / external-collaboration settings).
5. **Access-control AD group**: create `PTVI-Website-COMMs` **in PTGDI AAD** listing the
   invited COMMs guests; the operator checks membership via Graph. Because it's same-tenant,
   **no cross-tenant Graph consent needed** — GDI owns the roster.
6. **Graph `Sites.Selected` consent** for the **PTGDI** request SharePoint library
   (**PTGDI admin grant** — same tenant, no Vale involvement).
7. **Anthropic API** — GDI-owned account/key (billing + commercial terms on GDI's side);
   data-egress note for the review.
8. **`3-Done` move**: automated via Graph or left to the human.

## Review notes (2026-09-21) — resolve before build

Design-review pass. Verified against current Microsoft docs; the tenancy model is sound.
Items below are gaps to close, not blockers:

- **Failure path is under-specified.** Guardrails cover *verify after deploy*, but not what
  the bot does when a **prod deploy fails verification**: does it auto-rollback (we have
  `rollback-vacancy.py` but no general rollback), leave prod half-updated, or just alert?
  Deploys are incremental (per memory: never full-sync), so a partial failure can leave prod
  inconsistent. **Decide: alert-only + manual GDI recovery, or automated rollback per type.**
- **Concurrency lock is asserted, not designed.** "One request at a time" needs a real lock
  (the operator is the single writer; a file/DB lock or single-worker queue). Name the
  mechanism.
- **Secrets on a shared VM.** The Anthropic key, bot app-password/cert, and the prod deploy
  credential all sit on one host. Specify storage (Azure Key Vault + managed identity,
  not files on disk) and who can SSH in.
- **Guest churn breaks Layer 2 silently.** If a COMMs guest's PTGDI object is recreated
  (re-invited), their `aadObjectId` changes and they're locked out until re-added to the
  group. Note the re-invite runbook step.
- **Not every request maps to a workflow script.** `content-*.json` (bespoke page edits)
  has no `intake-to-*` — the page-editor is manual today. The operator can auto-handle
  news/doc/vacancy/awards; **bespoke page edits still need a human step** — say so, don't
  imply full automation.
- **Verify claim scope.** "HTTP 200 + content grep" is fine for a known URL, but a news/doc
  build touches an index + a new detail page + JSON; the verify step should check **each**
  changed URL, not just one.

## Migration from today

- Authoring (the forms) and the workflow scripts are **done and in production use** — they
  move to the VM unchanged.
- New build = the VM host, the Graph read layer, the operator service wrapper, the Teams bot,
  and the auth. The Mac stops being in the loop.

## What stays the same for COMMs

Same forms, same folder structure, same approve-the-preview step. The one change COMMs will
notice: they now work in a **PTGDI-hosted Teams channel they join as guests**, and the
request library **moves from the Vale-owned OneDrive/SharePoint to the PTGDI SharePoint
library** (decided 2026-09-21 — single source of truth in PTGDI keeps the Graph read
same-tenant; the tradeoff is COMMs re-bookmark the new location as a one-time change).
Authoring itself (the forms, the drop-in-`1-Submitted` flow) is unchanged; the operator
moves from "Feiry runs it on the Mac" to "the VM does it, driven from Teams."
```
