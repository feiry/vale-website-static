# Website Support Bot — PTVI-Tenant Deployment

**Date:** 2026-10-07
**For:** Vale IT

A Microsoft Teams bot that lets the COMMs team publish valeindonesia.com updates (news,
vacancies, awards, documents) via chat, with a dev-preview and approval step. Everything runs
inside the PTVI (valeindonesia.com) tenant.

## Architecture

```
COMMs (PTVI users)
      │  drop request
      ▼
SharePoint intake library
  1-Submitted / 2-In-Progress / 3-Done
      │ Graph            Teams
      ▼                    │
┌──── Azure VM (PTVI) ─────▼────┐
│  bot → operator:             │
│  detect → build → deploy dev │
└──────────────┬───────────────┘
               │ managed identity
               ▼
   Vale dev storage (stidstaticsite002)
```

**Components**

- **Azure VM** (Ubuntu, B2s, always-on): hosts the bot listener, nginx/TLS, and the operator.
- **Azure Bot** (single-tenant) + **app registration**: the Teams messaging endpoint.
- **Managed identity**: the one identity the bot uses for storage, Key Vault, and Graph.
- **Key Vault**: holds the bot secret (nothing on disk).
- **AAD group `Vale-Website-COMMs`**: the authorization roster — only its members can use the bot.
- **Deploy target**: Vale dev storage `stidstaticsite002`. Prod is manual for now.

**Flow**

1. COMMs drops a request in the existing SharePoint `1-Submitted/`.
2. COMMs messages the bot: `what's pending?` → `process the request`.
3. Bot builds and deploys to dev, posts preview links, moves the folder to `2-In-Progress`.
4. COMMs reviews on dev. Typo → `rollback`, fix, reprocess.
5. COMMs **approves** → bot publishes to production (Phase 2).

**Pure Azure** — no third-party AI service, no external API egress.

## Phase 1 — Dev deployment (what PTVI must do)

GDI builds and operates the stack. The steps run in order: Vale grants access, GDI builds the
VM and its managed identity, then Vale completes the grants that depend on that identity.

### Step 1 — Vale sets up access (before GDI builds anything)

*Subscription Owner / User Access Administrator:*

1. Create a resource group `rg-vale-website-bot`.
2. Grant Feiry/GDI **Contributor + User Access Administrator** on that resource group.

*Global Admin:*

3. Allow GDI to create the app registration + service principal `vale-website-support-bot` (or create it and make GDI owner).
4. Admin-consent the Graph app permissions: **GroupMember.Read.All** and **Sites.Selected** on the intake site.
5. Create AAD group **Vale-Website-COMMs** and add the COMMs members.

*SharePoint:*

6. Grant the app **Sites.Selected** on the existing "Valeindonesia.com Update - Request" library (read + move folders).

*Networking:*

7. Allow the VM outbound to Microsoft Graph and Vale storage; inbound 80/443 (public) + SSH from GDI's IP.

### Step 2 — GDI builds

8. GDI creates the VM (with its system-assigned managed identity), Key Vault, nginx/TLS, the bot, and the operator.

### Step 3 — Vale completes the identity-dependent grant (after the VM exists)

*Subscription Owner / User Access Administrator:*

9. Grant the VM's managed identity **Storage Blob Data Contributor** on `stidstaticsite002` (dev storage).

### Step 4 — Teams rollout

*Teams Admin:*

10. Upload the Teams app to the org catalog.
11. Create a Teams app setup policy that pins the bot, assigned to **Vale-Website-COMMs only** (not the org-wide default).

## Phase 2 — Production publish (after Phase 1 is validated)

Once the dev flow is proven, prod publishing is enabled. COMMs reviews the dev preview, then
approves; the bot deploys the approved content to production and verifies it.

**Flow:** `process` (dev) → COMMs reviews preview → COMMs clicks **Approve** → bot deploys to
production (`stidstaticsiteprod`) → bot verifies and posts the live links.

**What PTVI must do:**

1. Grant the VM's managed identity **Storage Blob Data Contributor** on `stidstaticsiteprod` (prod storage).

GDI enables the prod deploy path and the approval gate in the bot. No other Vale action is
required — the app registration, COMMs group, Teams app, and SharePoint access from Phase 1
are reused unchanged.
