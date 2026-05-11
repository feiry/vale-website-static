# Vale Indonesia — Static Mirror

Static HTML mirror of [vale.com/indonesia](https://vale.com/indonesia), deployed to AWS S3 + CloudFront.

## Quick Start

```bash
# Test crawl (depth 2)
make crawl DEPTH=2

# Preview locally
make serve

# Full build (crawl + postprocess + search)
make build

# Deploy to AWS
make deploy
```

## Prerequisites

- `wget` — `brew install wget` (macOS)
- `node` ≥ 18 — for Pagefind
- `aws` CLI — configured with appropriate credentials
- `terraform` ≥ 1.5 — for infrastructure provisioning

## Repository Structure

```
├── Makefile                  # Build/deploy commands
├── crawl.sh                  # wget mirror script
├── postprocess.sh            # Fix Liferay artifacts in HTML
├── search/
│   └── inject-pagefind.sh    # Build + inject Pagefind search
├── infra/                    # Terraform: S3, CloudFront, Route53, ACM
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
├── bitbucket-pipelines.yml   # Scheduled weekly re-crawl + deploy
└── site/                     # Generated mirror output (gitignored)
```

## Infrastructure

Provisioned via Terraform in `infra/`:

```bash
cd infra
terraform init
terraform plan -var="domain_name=indonesia.vale.com" -var="hosted_zone_id=Z1234567890"
terraform apply
```

Resources created:
- **S3 bucket** — private, versioned, encrypted
- **CloudFront** — OAC (not OAI), HTTP/2+3, gzip/brotli compression
- **ACM certificate** — DNS-validated, in us-east-1
- **Route53 A record** — alias to CloudFront

## Pipeline

Bitbucket Pipelines runs weekly (Sunday 19:00 UTC / Monday 02:00 WIB):
1. Crawl source site
2. Post-process HTML (strip Liferay artifacts, fix URLs)
3. Build Pagefind search index
4. Sync to S3
5. Invalidate CloudFront cache

Required Bitbucket repository variables:
- `BUCKET` — S3 bucket name
- `DIST_ID` — CloudFront distribution ID
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` (or OIDC)

## Post-Processing

`postprocess.sh` handles:
- Strips `com.liferay.portal.kernel.util.*` from image alt attributes
- Rewrites absolute `vale.com` URLs to root-relative
- Removes Google Tag Manager (GTM-TXBLVPM)
- Neutralizes cookie preference links
- Generates `MIGRATION_NOTES.md` listing dropped dynamic features
