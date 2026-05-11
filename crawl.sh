#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="./site"
SOURCE="https://vale.com/indonesia"
DEPTH_LIMIT="${1:-0}"  # Pass depth as first arg, 0 = unlimited

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

WGET_ARGS=(
  --mirror
  --convert-links
  --adjust-extension
  --page-requisites
  --no-parent
  --restrict-file-names=windows
  --user-agent="Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
  --wait=1 --random-wait
  -e robots=off
  --domains=vale.com
  --include-directories=/indonesia,/documents,/o
  --directory-prefix="$OUTPUT_DIR"
)

if [[ "$DEPTH_LIMIT" -gt 0 ]]; then
  echo ">>> Crawling with depth limit: $DEPTH_LIMIT"
  WGET_ARGS+=(-l "$DEPTH_LIMIT")
else
  echo ">>> Full crawl (no depth limit)"
fi

wget "${WGET_ARGS[@]}" "$SOURCE" || {
  # wget exits 8 on some 404s during mirror — that's expected
  exit_code=$?
  if [[ $exit_code -eq 8 ]]; then
    echo ">>> wget exited with code 8 (some 404s during mirror) — continuing"
  else
    echo ">>> wget failed with exit code $exit_code"
    exit $exit_code
  fi
}

echo ">>> Crawl complete. Output in $OUTPUT_DIR"
