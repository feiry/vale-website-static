# Website Update Pipeline — Azure VM + Teams Design

**Date:** 2026-09-15
**Status:** Design (approved in principle by Feiry; for Sandy / IT / EY review)
**Supersedes:** the earlier Mac + Telegram + OneDrive-mirror sketch (rejected — Telegram
is not company-standard, and macOS TCC blocks a background process from reading
`~/Library/CloudStorage` reliably).

## Why this shape

Moving the operator to an **Azure VM in Vale's tenant** and talking over **Microsoft
Teams** removes every constraint we hit on the Mac and matches company standards:

- No macOS TCC / OneDrive file-access problem — a VM reads files via Microsoft Graph.
- A real always-on host with a public HTTPS endpoint (required by the Teams Bot Framework).
- One Azure AD identity for the bot, the file reads, and the storage deploys.
- Company-standard (Teams, Azure), IT-approvable, next to the existing dev/prod storage.

## Architecture

```
COMMs ──> Teams channel "Valeindonesia.com Update - Request"
          SharePoint doc library: _Templates / 1-Submitted / 2-In-Progress / 3-Done-Deployed
             │
             │  Microsoft Graph API (app identity)         Teams Bot Framework
             ▼                                                    ▲
     ┌────────────────────────── Azure VM (Vale tenant) ─────────┴──────────┐
     │  Teams Bot endpoint  ──►  Claude agent (conversation only)           │
     │                              │ decides WHEN                          │
     │                              ▼                                       │
     │  Operator service (deterministic):                                   │
     │    read request (Graph) → detect type → intake → build → deploy      │
     │    dev  →  (await approval)  →  deploy prod                          │
     │    workflow scripts: intake-to-*, build-*, vacancy tools (this repo) │
     └───────────────────────────────┬──────────────────────────────────────┘
                                      │ az / Graph
                                      ▼
                 dev storage (stidstaticsite002)   prod storage (stidstaticsiteprod)
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

- **Graph**: `Sites.Selected` (scoped to the one request library) to list/read/`3-Done` move.
- **Storage**: Storage Blob Data Contributor on dev + prod accounts (prod via PIM or a
  dedicated deploy identity — TBD with IT; PIM's human-MFA model may not suit an unattended
  VM, so a scoped managed identity for prod deploys is likely cleaner. **Open question.**)
- **Bot**: Azure Bot resource; VM holds the app password / cert.

## Flow

1. COMMs drops a request folder in Teams `1-Submitted/` (unchanged authoring; same forms).
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
- **Authorized approvers only** (named COMMs/GDI in the channel) can trigger prod.
- **One request at a time**, tracked; no double-deploy.
- **Least-privilege identity**; prod deploy credential scoped and logged.

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

1. **VM**: size, OS (Linux preferred), which subscription/RG, network egress to
   valeindonesia.com + Anthropic API + Graph. Workload is light/bursty/mostly-idle
   (see Runtime & cost model) — a small VM suffices; confirm monthly budget with IT.
2. **Prod deploy identity**: PIM (human-MFA, awkward unattended) vs a scoped managed
   identity / service principal for the VM. **Recommend the latter — needs IT sign-off.**
3. **Azure Bot registration** approval + who owns it.
4. **Graph `Sites.Selected` consent** for the request library.
5. **Anthropic API** on a Vale-tenant VM — key management + data-egress review.
6. **`3-Done` move**: automated via Graph or left to the human.

## Migration from today

- Authoring (the forms) and the workflow scripts are **done and in production use** — they
  move to the VM unchanged.
- New build = the VM host, the Graph read layer, the operator service wrapper, the Teams bot,
  and the auth. The Mac stops being in the loop.

## What stays the same for COMMs

Nothing changes in how COMMs works — same forms, same Teams folder, same approve-the-preview
step. Only the operator moves from "Feiry runs it on the Mac" to "the VM does it, driven from
Teams."
```
