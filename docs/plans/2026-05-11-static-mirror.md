# Vale Indonesia Static Mirror — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Mirror vale.com/indonesia as a static site, deploy to S3 + CloudFront via Terraform.

**Architecture:** wget mirror → postprocess (fix Liferay artifacts, strip tracking) → Pagefind search index → S3 sync + CloudFront invalidation. Terraform provisions all AWS infra. Bitbucket Pipelines runs weekly re-crawl.

**Tech Stack:** wget, bash, sed, Node.js (Pagefind), Terraform (AWS provider), Bitbucket Pipelines

---

### Task 1: Scaffold repo structure

**Files:**
- Create: `Makefile`
- Create: `crawl.sh`
- Create: `postprocess.sh`
- Create: `search/inject-pagefind.sh`
- Create: `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`
- Create: `bitbucket-pipelines.yml`
- Create: `.gitignore`
- Create: `README.md`

### Task 2: crawl.sh — wget mirror script

Depth-limited test crawl first (`-l 2`), then full crawl.
Include `/indonesia` and `/documents` directories.
Polite crawling with wait + random-wait.

### Task 3: postprocess.sh — fix Liferay artifacts

- Strip `com.liferay.portal.kernel.util.*` from alt attributes
- Rewrite absolute `https://vale.com/` → root-relative `/`
- Remove GTM noscript iframe (GTM-TXBLVPM)
- Remove/neutralize cookie preference links to Liferay endpoints
- Scan for external form actions and API calls → `MIGRATION_NOTES.md`

### Task 4: Pagefind search injection

- Build Pagefind index against `./site/`
- Inject Pagefind UI CSS+JS into all HTML pages via script
- Replace Liferay search form with Pagefind search

### Task 5: Terraform infrastructure

- S3 bucket (private, OAC)
- CloudFront distribution (OAC, http2and3, PriceClass_200, compress)
- ACM cert in us-east-1
- Route53 records
- Tags: Project=vale-indonesia-static, ManagedBy=terraform

### Task 6: Bitbucket Pipeline

- Weekly schedule: Sunday 19:00 UTC (Monday 02:00 WIB)
- Steps: crawl → postprocess → pagefind → s3 sync → CF invalidation

### Task 7: Makefile

- `make build`: crawl + postprocess + pagefind
- `make deploy`: s3 sync + CF invalidation
- `make serve`: python3 http.server
- `make clean`: rm -rf site/

### Task 8: Initial test crawl + validation

- Run `make build` with depth limit 2
- Browse via `make serve`, verify styles/images/links
- Check no Liferay artifacts remain
- Verify Pagefind search works
