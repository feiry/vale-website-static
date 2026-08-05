# Production Environment Setup — Requirements & Provisioning Specification
### Vale Indonesia Static Website

**Date:** 2026-08-05
**Prepared by:** Feiry (feiry@valeindonesia.com)
**Audience:** EY / GDS Infrastructure (provisioning) · PT Vale Indonesia management (approval)
**Tenant:** valeindonesia.com · **Subscription:** Production (`34e3dbac-c2c3-4d5b-8c39-f40d69c6f0fe`)

---

## 1. Executive Summary

The Vale Indonesia static website has been built and validated in an EY-provisioned **development** environment on Azure (`rg-staticsite-dev` / `stidstaticsite002`). This document specifies what must be provisioned to stand up a **production** environment, so the site can go live under the corporate domain **valeindonesia.com**.

To reduce risk and defer public-facing spend until content is signed off, production is delivered in **two phases**:

- **Phase 1 — Storage-only production (private validation).** EY provisions a prod-grade storage account with static-website hosting. The site is deployed and validated on the internal Azure web endpoint (`*.web.core.windows.net`) — a functional, prod-shaped environment with **no public URL, no CDN, no WAF, and no DNS change**. Vale QA signs off here.
- **Phase 2 — Public go-live.** EY adds Azure Front Door (CDN + WAF), attaches the `valeindonesia.com` apex domain with Azure-managed TLS, and Vale performs the DNS cutover. Only at this point is the site publicly reachable on the corporate domain.

This phasing lets Vale test the real production content and infrastructure privately, then commit to the public cutover as a separate, well-controlled decision.

**Decisions required for approval** (detailed in §11): confirm the target domain and DNS zone control, approve the two-phase plan and prod-grade tier (ZRS redundancy, Standard Front Door with WAF), and authorize EY to grant the required RBAC role assignments (a known blocker from dev — see §6).

---

## 2. Current State — Development Environment

| Attribute | Dev today |
|---|---|
| Resource group | `rg-staticsite-dev` (Indonesia Central) |
| Storage account | `stidstaticsite002` — StorageV2, **Standard_LRS**, HTTPS-only |
| Hosting | Static-website (`$web`), `index.html` / `404.html` |
| Endpoint | `https://stidstaticsite002.z45.web.core.windows.net/` (raw, no custom domain) |
| CDN / Front Door | **None** |
| Custom domain / TLS | **None** (raw endpoint only) |
| WAF | **None** |
| Redundancy | LRS (single-zone) |
| Deploy | Manual from Mac — `deploy-azure.sh` (`az storage blob upload-batch`) |
| IaC | None (provisioned manually by EY) |
| Access | `feiry@valeindonesia.com` via custom role `CUST-StaticWeb-Admin-Dev` at RG scope |

**Known limitations carried into planning:** the tenant's Conditional Access blocks interactive `az login` from Azure VMs, and `feiry@valeindonesia.com` lacks `roleAssignments/write` — so **role grants are an EY/Owner action** (§6).

---

## 3. Target Production Architecture

**End-state (after Phase 2):**

```
                 valeindonesia.com (apex)
                          │  DNS (A/ALIAS → Front Door)
                          ▼
        ┌─────────────────────────────────────┐
        │   Azure Front Door (Standard)        │
        │   • CDN edge caching                 │
        │   • WAF policy (managed ruleset)     │
        │   • Azure-managed TLS cert           │
        │   • HTTP→HTTPS redirect              │
        └─────────────────────────────────────┘
                          │  origin (private, Front Door only)
                          ▼
        ┌─────────────────────────────────────┐
        │  Storage account (prod)              │
        │  • StorageV2, ZRS, HTTPS-only        │
        │  • Static-website $web               │
        │  • index.html / 404.html             │
        └─────────────────────────────────────┘

  Phase 1  = storage box only, reached directly on *.web.core.windows.net
  Phase 2  = adds the Front Door box + domain + DNS cutover on top
```

**Phase boundary:** Phase 1 provisions and validates only the bottom (storage) box, reached on its raw web endpoint. Phase 2 layers Front Door, WAF, the custom domain, managed TLS, and the DNS cutover on top — with no change to the already-validated storage/content beneath.

---

## 4. Phase 1 — Storage-Only Production (Private Validation)

**Goal:** A prod-grade storage account hosting the static site, deployed and QA-validated on its raw Azure web endpoint. No public URL, no CDN, no WAF, no DNS change.

### 4.1 Resources to provision

| # | Resource | Specification |
|---|---|---|
| 1 | **Resource group** | `rg-staticsite-prod` — region **Indonesia Central** (`indonesiacentral`), matching the valeforms prod convention. *EY to confirm final name.* |
| 2 | **Storage account** | Name per convention, e.g. `ststaticsiteprodid` (≤24 chars, lowercase, globally unique). **StorageV2**, **Standard_ZRS** (zone-redundant — prod minimum), **HTTPS-only = true**, **min TLS = 1.2**, public blob access disabled except via `$web`. |
| 3 | **Static-website hosting** | Enabled on the account. `indexDocument = index.html`, `errorDocument404Path = 404.html` (mirrors dev exactly). |
| 4 | **Private archive container** | `crawl-archive` (private, **not** `$web`) — for the frozen source snapshot/tarball, matching dev practice. Optional but recommended. |

### 4.2 Configuration requirements

- **MIME correctness** — the deploy tooling explicitly sets content-types for `.css` → `text/css`, `.js` → `application/javascript`, and extensionless `documents/d/` files (PDF/PNG/JPEG detected by header). This is handled by `deploy-azure.sh`; no storage-side config needed beyond static-website hosting.
- **Cache-Control** — content uploaded with `public, max-age=300` (5 min), consistent with dev. Longer caching is deferred to the Front Door layer in Phase 2.
- **404 routing** — validated via `GET` (note: `HEAD` misleadingly returns `WebContentNotFound` headers on Azure static hosting — a known quirk, not a defect).

### 4.3 Validation exit criteria (before Phase 2 is authorized)

Deployed on `https://<account>.<zone>.web.core.windows.net/`, confirm:

- Homepage + flattened pages render (EN and ID);
- Bilingual correctness — EN pages `<html lang="en-US">`, ID pages `<html lang="in-ID">`;
- CSS/JS served with correct MIME (not `text/plain`);
- Document downloads and space-in-filename PDFs resolve;
- Extensionless `documents/d/` files serve with correct content-type;
- 404 routing works via GET.

**Vale QA sign-off on this endpoint is the gate to Phase 2.**

---

## 5. Phase 2 — Public Go-Live (Front Door + Domain)

**Goal:** Make the validated site publicly reachable on **valeindonesia.com** with CDN, WAF, and managed TLS. No change to the Phase 1 storage/content beneath.

### 5.1 Resources to provision

| # | Resource | Specification |
|---|---|---|
| 1 | **Azure Front Door profile** | **Standard** tier (includes CDN + WAF; Premium only needed for private-link origin or advanced managed rules — not required here). One profile, e.g. `afd-staticsite-prod`. |
| 2 | **Endpoint** | One AFD endpoint, e.g. `staticsite-prod` → `<name>.z01.azurefd.net`. |
| 3 | **Origin group + origin** | Origin = the Phase 1 storage **static-website endpoint** (`<account>.<zone>.web.core.windows.net`), HTTPS, origin host header set to that hostname. Health probe on `/`. |
| 4 | **Custom domain** | `valeindonesia.com` (apex) attached to the endpoint. Domain-validation TXT record required (see §7). |
| 5 | **TLS certificate** | **Azure Front Door-managed certificate** (auto-issued + auto-renewed). No manual cert handling. Min TLS 1.2. |
| 6 | **Routing rule** | Route `valeindonesia.com/*` → origin group. **HTTP → HTTPS redirect** enabled. Forward `index.html` for directory requests as needed. |
| 7 | **WAF policy** | Associated to the endpoint: **Azure-managed Default Rule Set (DRS)** in **Prevention** mode. Optional rate-limit + geo rules per Vale preference. |

### 5.2 Origin lockdown (recommended)

Once Front Door fronts the site, restrict the storage endpoint so the public reaches content **only through Front Door** (not the raw `*.web.core.windows.net` URL that was public in Phase 1):

- Restrict the storage account's networking to Front Door via the **`AzureFrontDoor.Backend` service tag** + the **`X-Azure-FDID`** header check (verify the incoming Front Door ID), so direct-to-origin requests are refused.
- This closes the Phase-1 "obscure public URL" once the real front door is live.

### 5.3 Caching

- Front Door caching enabled; honor origin `Cache-Control` or set edge TTLs (e.g. long TTL for hashed static assets `/css /js /images`, short for HTML). Tune during go-live.

### 5.4 Go-live exit criteria

- `https://valeindonesia.com/` serves the site with a valid managed cert (no TLS warning);
- HTTP redirects to HTTPS;
- WAF in Prevention mode, legitimate traffic unaffected;
- Direct origin URL no longer serves content publicly (§5.2);
- Spot-check EN/ID pages, a document download, and 404 behavior through the Front Door domain.

---

## 6. Access & Identity Requirements

Two constraints observed in the dev environment directly shape what EY must provision for prod. Both are **EY/Owner actions** — they cannot be self-served by `feiry@valeindonesia.com`.

### 6.1 Known blockers from dev

1. **Conditional Access blocks interactive `az login` from Azure VMs** (error `AADSTS53003` — device not registered). Any deploy or automation that runs *inside* an Azure VM cannot authenticate interactively.
2. **`feiry@valeindonesia.com` lacks `roleAssignments/write`.** The account can read/write blobs (via its assigned custom role) but **cannot grant roles to itself or to a managed identity.** All RBAC assignments must be performed by an EY/Owner.

### 6.2 Required role assignments (EY to grant)

| Principal | Role | Scope | Purpose |
|---|---|---|---|
| `feiry@valeindonesia.com` | **Storage Blob Data Contributor** (or an equivalent custom `CUST-StaticWeb-Admin-Prod` mirroring dev) | `rg-staticsite-prod` (RG scope) | Deploy content to `$web` from the authorized Mac (`az storage blob upload-batch`). |
| `feiry@valeindonesia.com` | **Reader** (minimum) on the Front Door profile | AFD resource / RG | Verify Phase 2 config and run go-live checks. |
| *(Phase 2, optional)* Front Door | — | reads storage static-website endpoint as origin | No storage RBAC needed — origin is the public web endpoint; lockdown is via service tag + `X-Azure-FDID` (§5.2), not RBAC. |

### 6.3 Deploy identity model

- **Chosen model (matches dev, no new blockers):** deploys run **from the authorized Mac** as `feiry@valeindonesia.com`, which is **not** Conditional-Access-blocked. This works today for dev and requires only the Blob Data Contributor grant above for prod. **This is the recommended Phase 1 path — no additional identity to provision.**
- **Optional future hardening (not required for go-live):** if deploys should ever run unattended (CI/scheduled), EY provisions a **managed identity or service principal** with Storage Blob Data Contributor on `rg-staticsite-prod`, exempted from the VM Conditional-Access policy or run from a compliant runner. Flagged as optional; not a launch dependency.

### 6.4 Separation of dev and prod

- Prod is a **distinct resource group and storage account** from dev — no shared credentials or blobs. The prod Blob Data Contributor grant is scoped to `rg-staticsite-prod` only, so dev access and prod access are independent.

---

## 7. DNS & Domain Cutover *(Phase 2)*

**Target:** serve the site at the apex **`valeindonesia.com`**.

### 7.1 Critical dependency — DNS zone control

`valeindonesia.com` is the **live corporate domain**. Whoever operates the current DNS zone (Vale IT or an external registrar/provider) must make the cutover records. **This must be confirmed before Phase 2 is scheduled** — it is the single biggest external dependency and is outside EY's static-site scope unless the zone is also under EY management.

> **Action for Vale:** identify and confirm who controls the `valeindonesia.com` DNS zone and can create/modify records.

### 7.2 Records required

| Step | Record | Purpose |
|---|---|---|
| **Domain validation** | `TXT` `_dnsauth.valeindonesia.com` (value provided by Front Door) | Proves domain ownership so AFD issues the managed cert. **Non-disruptive** — add ahead of cutover; does not affect live traffic. |
| **Apex cutover** | Apex `valeindonesia.com` → Front Door endpoint. At the apex, a plain `CNAME` is not RFC-valid; use the provider's **ALIAS / ANAME / CNAME-flattening** record (Azure DNS: **alias A record** to the AFD resource). | Points live traffic to Front Door. **This is the disruptive step.** |
| *(if `www` in scope)* | `www.valeindonesia.com` → `CNAME` to AFD endpoint | Optional; redirect `www` → apex or serve both. Confirm with Vale. |

### 7.3 Cutover sequence (minimize risk)

1. **Pre-stage everything** — AFD profile, origin, WAF, custom domain **added and validated** (TXT record in place, managed cert issued) while `valeindonesia.com` still points at its current target. Front Door reachable and tested on its `*.azurefd.net` endpoint.
2. **Lower DNS TTL** on the existing apex record 24–48h before cutover (e.g. to 300s) so the switch propagates fast and rollback is quick.
3. **Cutover** — repoint the apex ALIAS/A record to Front Door during a low-traffic window.
4. **Verify** — `https://valeindonesia.com/` serves via Front Door, valid managed cert, HTTP→HTTPS, WAF active, EN/ID + document spot-checks pass.
5. **Lock down origin** (§5.2) once traffic is confirmed flowing through Front Door.
6. **Restore normal TTL** after propagation is confirmed stable.

### 7.4 Rollback

Because only the apex record changed and its TTL was pre-lowered, rollback is a **single DNS revert** to the previous target. Keep the prior record value documented before cutover. No storage/content change is involved, so rollback carries no data risk.

---

## 8. Security & Compliance

| Control | Phase 1 (storage-only) | Phase 2 (public) |
|---|---|---|
| **Transport encryption** | HTTPS-only enforced on storage account; min TLS 1.2 | Front Door enforces HTTPS; **HTTP → HTTPS redirect**; min TLS 1.2 at the edge |
| **Certificate** | N/A (raw Azure endpoint uses Azure's own cert) | **Azure-managed** cert for `valeindonesia.com` — auto-issued, auto-renewed (no manual expiry risk) |
| **WAF** | Not available without Front Door (accepted for private validation) | **Azure-managed Default Rule Set** in **Prevention** mode; optional rate-limit + geo rules |
| **Origin exposure** | Raw `*.web.core.windows.net` URL is technically internet-reachable but unadvertised (accepted) | Origin **locked to Front Door** via `AzureFrontDoor.Backend` service tag + `X-Azure-FDID` header check (§5.2) — raw URL no longer serves content |
| **Storage hardening** | StorageV2, ZRS, HTTPS-only, min TLS 1.2, no anonymous access except `$web`; storage account keys not used for deploy (RBAC/Entra auth only) | unchanged |
| **Content** | Static HTML/CSS/JS/images/PDFs only — **no server-side code, no database, no user input.** Attack surface is limited to content delivery. | unchanged |

**Note on residual Phase 1 exposure:** during private validation the site is reachable by anyone who knows the raw endpoint URL. This is acceptable for QA of non-sensitive public marketing content, and is fully closed at §5.2 once Front Door is live. If Vale requires zero public exposure in Phase 1, that would require bringing Front Door forward or a private-endpoint model — flagged as a decision (§11), not a default.

---

## 9. Deployment Model

- **Mechanism:** content is deployed from the **authorized Mac** as `feiry@valeindonesia.com` using `deploy-azure.sh` (`az storage blob upload-batch` against `$web`), the same tooling validated in dev. The script also builds the static News and Document Library pages, sets correct MIME types for CSS/JS and extensionless documents, and supports `--delete-orphans` for pruning.
- **Target selection:** the deploy script takes the storage account name as an argument, so promoting to prod is `./deploy-azure.sh <prod-account>` — no code change, only a different target.
- **Dev → prod promotion:** dev and prod are separate accounts. Content validated in dev is deployed to prod by pointing the same tooling at the prod account. **Incremental uploads only** (upload-batch `--overwrite` of changed files) — no full re-sync/rebuild as a matter of convention.
- **Phase 2 cache note:** after Front Door is live, content changes may require a **Front Door cache purge** (or short edge TTLs) to appear immediately. Factor this into the post-cutover deploy runbook.
- **Source durability:** the frozen source snapshot is archived to the private `crawl-archive` container; prod content is always reproducible from that snapshot + repo patches without re-crawling.

---

## 10. Open Dependencies & Risks

| # | Item | Impact | Owner / resolution |
|---|---|---|---|
| 1 | **DNS zone control for `valeindonesia.com`** | Blocks Phase 2 go-live entirely | **Vale** — identify who operates the zone; confirm before scheduling cutover (§7.1) |
| 2 | **RBAC role grant on `rg-staticsite-prod`** | Blocks all prod deploys | **EY/Owner** — grant Storage Blob Data Contributor to `feiry@valeindonesia.com` (§6.2); cannot be self-served |
| 3 | **Content QA sign-off** | Gate between Phase 1 and Phase 2 | **Vale** — News rebuild is still pending Peter's QA per current project status; prod go-live should not precede content sign-off |
| 4 | **Naming convention confirmation** | Minor; affects resource names | **EY** — confirm `rg-staticsite-prod` / `ststaticsiteprodid` vs valeforms-style pattern |
| 5 | **Apex ALIAS/ANAME support** | Determines exact cutover record | **Vale/EY** — confirm DNS provider supports apex alias / CNAME-flattening (Azure DNS alias A record if zone is in Azure) |
| 6 | **Front Door cache purge in deploy flow** | Content-update latency post-go-live | **Feiry** — add purge step to Phase 2 runbook |
| 7 | **News listing pagination** | Known content limitation (dynamic `all-news` captured as single snapshot) | Pre-existing; unchanged by prod — noted for completeness |

---

## 11. Decisions Required & Recommended Timeline

### 11.1 Decisions required (for approval)

1. **Approve the two-phase rollout** (private storage validation → public go-live). ✔ recommended
2. **Approve prod-grade tier:** Standard_ZRS storage, Azure Front Door **Standard** with managed WAF (Prevention mode). ✔ recommended
3. **Confirm the target domain** is the apex `valeindonesia.com` (and whether `www` is in scope).
4. **Authorize EY** to provision `rg-staticsite-prod` and grant the RBAC role assignment (§6.2).
5. **Confirm DNS zone owner** and apex-alias capability (§7).
6. **Confirm Phase 1 exposure posture** — obscure public URL acceptable for QA (recommended), or zero-exposure required (would change Phase 1 scope).

### 11.2 Recommended sequence

| Stage | Activity | Owner | Depends on |
|---|---|---|---|
| A | Approve plan & tier; confirm naming | Vale mgmt + EY | §11.1 |
| B | Provision `rg-staticsite-prod` + ZRS storage + static-website; grant RBAC | EY | A |
| C | Deploy content; run Phase 1 validation (§4.3) | Feiry | B |
| D | **Vale QA sign-off** on raw endpoint | Vale | C + content QA |
| E | Provision Front Door + WAF + custom domain; pre-stage TXT validation & managed cert | EY | D |
| F | Lower TTL → apex DNS cutover → verify → lock down origin | Vale DNS + Feiry | E + §7.1 |
| G | Restore TTL; document runbook (incl. cache purge) | Feiry | F |

Phase 1 (stages B–D) can proceed as soon as approval and the RBAC grant land. Phase 2 (E–G) is gated on content sign-off **and** DNS zone confirmation, and can be scheduled independently.

---

*End of specification.*
