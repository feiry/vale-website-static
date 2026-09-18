#!/usr/bin/env bash
set -euo pipefail

# Bilingual per-URL crawl of vale.com/indonesia (EN) + vale.com/in/indonesia (ID).
#
# Why this exists (vs crawl.sh): the live site serves language by COOKIE/SESSION.
# EN and ID must be crawled with SEPARATE fresh cookie jars or the site redirects
# everything to whichever language was opened first. We also have an explicit
# 166-URL list, so we fetch each URL directly (-i) instead of recursive-spidering
# from one seed (which caused the documented crawl gap).
#
# Output lands in <outdir>/vale.com/... so deploy-azure.sh (SITE_DIR=site/vale.com)
# can consume a working copy of it directly.
#
# Usage:
#   ./crawl-site.sh [outdir]                 # full crawl: urls-en.txt + urls-id.txt
#   ./crawl-site.sh --input FILE [outdir]    # canary: single pass over FILE
#
# Default outdir: ./site-raw  (the frozen snapshot; NOT ./site which is the working copy)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

INPUT_OVERRIDE=""
OUTDIR="./site-raw"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) INPUT_OVERRIDE="$2"; shift 2 ;;
    -h|--help)
      sed -n '2,20p' "$0"; exit 0 ;;
    *) OUTDIR="$1"; shift ;;
  esac
done

UA="Mozilla/5.0 (compatible; StaticMirrorBot/1.0)"

# Shared wget args. -l 1 + -r = follow HTML links exactly one level deep (depth+1),
# then stop. --page-requisites grabs CSS/JS/img/fonts at any depth.
#
# Scoping (learned the hard way in canary): do NOT use --no-parent. It scopes
# recursion to the SEED's directory, so a deep seed (e.g. /in/indonesia/esg/foo)
# can't reach its siblings while a shallow seed can — depth+1 becomes inconsistent.
# Instead, --include-directories pins recursion to the dirs we want (EN /indonesia,
# ID /in/indonesia, plus /documents + /o assets), and --exclude-directories blocks
# the 13 foreign-language locale trees (/ar/indonesia, /de/indonesia, ... — but NOT
# /in which is our Bahasa).
#
# --reject-regex: drop ONLY the all-news pagination explosion. The earlier broad
# pattern '(delta=|start=|[?@])' was a canary-caught bug: it also rejected every
# document IMAGE, because Liferay image requisites legitimately use
# '/documents/.../img.jpg/<uuid>?version=1.0&t=...'. Rejecting on '?' or '@' killed
# all those images (broken hero images on every page). The fix: reject only URLs that
# carry the pagination params delta=/start=/cur=, which are unique to the news listing.
COMMON_ARGS=(
  --recursive
  --level=1
  --page-requisites
  --convert-links
  --adjust-extension
  --force-directories
  --restrict-file-names=windows
  --domains=vale.com
  --include-directories=/indonesia,/in/indonesia,/documents,/o,/-
  --exclude-directories=/ar/indonesia,/ca/indonesia,/de/indonesia,/es/indonesia,/fi/indonesia,/fr/indonesia,/hu/indonesia,/ja/indonesia,/nl/indonesia,/pt/indonesia,/sv/indonesia,/zh/indonesia
  --reject-regex='([?&](delta|start|cur|resetCur|_com_)=)'
  --user-agent="$UA"
  --wait=1 --random-wait
  --tries=2 --timeout=30
  -e robots=off
  --directory-prefix="$OUTDIR"
)

# Run one language pass with its OWN fresh cookie jar.
#   $1 = label (en|id|canary)   $2 = url list file
run_pass() {
  local label="$1" list="$2"
  local jar; jar="$(mktemp -t "vale-cookies-${label}.XXXXXX")"
  : > "$jar"   # fresh empty jar — no cross-language contamination

  echo ">>> [$label] crawling $(grep -c . "$list") URL(s) with fresh cookie jar"
  set +e
  wget "${COMMON_ARGS[@]}" \
    --save-cookies "$jar" --load-cookies "$jar" --keep-session-cookies \
    -i "$list"
  local rc=$?
  set -e
  rm -f "$jar"

  if [[ $rc -ne 0 && $rc -ne 8 ]]; then
    echo ">>> [$label] wget failed with exit code $rc"
    return $rc
  fi
  [[ $rc -eq 8 ]] && echo ">>> [$label] wget exit 8 (some 404s during mirror) — continuing"
  echo ">>> [$label] pass complete"
}

mkdir -p "$OUTDIR"

if [[ -n "$INPUT_OVERRIDE" ]]; then
  [[ -f "$INPUT_OVERRIDE" ]] || { echo "ERROR: input file not found: $INPUT_OVERRIDE"; exit 1; }
  # Canary / ad-hoc: split the override by language so each gets a clean jar,
  # preserving the cookie-separation guarantee even in a mixed list.
  EN_TMP="$(mktemp)"; ID_TMP="$(mktemp)"
  grep    '/in/indonesia' "$INPUT_OVERRIDE" > "$ID_TMP" || true
  grep -v '/in/indonesia' "$INPUT_OVERRIDE" > "$EN_TMP" || true
  [[ -s "$EN_TMP" ]] && run_pass "canary-en" "$EN_TMP"
  [[ -s "$ID_TMP" ]] && run_pass "canary-id" "$ID_TMP"
  rm -f "$EN_TMP" "$ID_TMP"
else
  [[ -f urls-en.txt && -f urls-id.txt ]] || { echo "ERROR: urls-en.txt / urls-id.txt missing"; exit 1; }
  run_pass "en" urls-en.txt
  run_pass "id" urls-id.txt
fi

# ---- Summary ----
echo ""
echo ">>> Crawl summary ($OUTDIR)"
if [[ -d "$OUTDIR/vale.com" ]]; then
  en_pages=$(find "$OUTDIR/vale.com/indonesia" -maxdepth 6 -name '*.html' 2>/dev/null | grep -v '/in/indonesia' | wc -l | tr -d ' ')
  id_pages=$(find "$OUTDIR/vale.com/in/indonesia" -name '*.html' 2>/dev/null | wc -l | tr -d ' ')
  total_files=$(find "$OUTDIR" -type f | wc -l | tr -d ' ')
  echo "    EN html pages : $en_pages"
  echo "    ID html pages : $id_pages"
  echo "    Total files   : $total_files"
  echo "    Size          : $(du -sh "$OUTDIR" | cut -f1)"
else
  echo "    WARNING: $OUTDIR/vale.com not created — nothing crawled?"
fi
echo "    Output path   : $OUTDIR/vale.com"
