.PHONY: build crawl postprocess search deploy serve clean

BUCKET ?= $(shell cd infra && terraform output -raw s3_bucket_name 2>/dev/null)
DIST_ID ?= $(shell cd infra && terraform output -raw cloudfront_distribution_id 2>/dev/null)

# Full build: crawl → postprocess → search index
build: crawl postprocess search

# Crawl with optional depth limit: make crawl DEPTH=2
crawl:
	chmod +x crawl.sh
	./crawl.sh $(DEPTH)

postprocess:
	chmod +x postprocess.sh
	./postprocess.sh

search:
	chmod +x search/inject-pagefind.sh
	./search/inject-pagefind.sh

# Deploy to S3 + invalidate CloudFront
deploy:
	aws s3 sync ./site/vale.com s3://$(BUCKET) --delete --cache-control "public, max-age=300"
	aws cloudfront create-invalidation --distribution-id $(DIST_ID) --paths "/*"

# Local preview server
serve:
	@echo "Serving at http://localhost:8000"
	@cd site/vale.com && python3 ../../serve.py 8000

clean:
	rm -rf site/ MIGRATION_NOTES.md
