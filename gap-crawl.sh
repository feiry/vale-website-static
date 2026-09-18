#!/usr/bin/env bash
# Targeted gap fetch: each URL fetched INDIVIDUALLY, NO recursion, fresh cookie jar.
# No depth+1 -> no cross-language contamination. Forces each ID page to be saved
# under its real /in/indonesia/ path. --content-disposition off; we trust the URL path.
set -uo pipefail
LIST="${1:?usage: gap-crawl.sh <url-list> <outdir>}"
OUT="${2:?usage: gap-crawl.sh <url-list> <outdir>}"
UA="Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"
mkdir -p "$OUT"
n=0; ok=0; bad=0
while IFS= read -r url; do
  [ -n "$url" ] || continue
  n=$((n+1))
  jar="$(mktemp)"; : > "$jar"
  # --max-redirect=0 would fail on the language 301; instead we follow but the FRESH jar
  # (no prior EN state) means the ID URL resolves to ID. -nH? no, keep host dir.
  # KEY: fetch ONLY this URL (no -r), with requisites, save under URL path.
  set +e
  wget --no-verbose \
    --page-requisites --adjust-extension --convert-links --force-directories \
    --restrict-file-names=windows --domains=vale.com \
    --save-cookies "$jar" --load-cookies "$jar" --keep-session-cookies \
    --user-agent="$UA" --tries=2 --timeout=30 -e robots=off \
    --directory-prefix="$OUT" \
    "$url" 2>>"$OUT/gap.log"
  rc=$?
  set -e
  rm -f "$jar"
  # verify it landed under the ID path
  rel="${url#https://vale.com}"
  if [ -f "$OUT/vale.com${rel}.html" ]; then ok=$((ok+1)); else bad=$((bad+1)); echo "MISS: $url" >> "$OUT/gap-miss.log"; fi
done < "$LIST"
echo "fetched=$n ok=$ok miss=$bad"
