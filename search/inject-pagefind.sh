#!/usr/bin/env bash
set -euo pipefail

SITE_DIR="./site/vale.com"

if [[ ! -d "$SITE_DIR" ]]; then
  echo "ERROR: $SITE_DIR not found. Run crawl.sh first."
  exit 1
fi

# Build the Pagefind index
echo ">>> Building Pagefind index..."
npx pagefind --site "$SITE_DIR"

echo ">>> Injecting Pagefind UI into HTML files..."

# Pagefind CSS and JS references (relative to site root)
PAGEFIND_CSS='<link href="/pagefind/pagefind-ui.css" rel="stylesheet">'
PAGEFIND_JS='<script src="/pagefind/pagefind-ui.js"></script>'
PAGEFIND_INIT='<script>window.addEventListener("DOMContentLoaded",function(){if(document.getElementById("search")){new PagefindUI({element:"#search",showSubResults:true})}});</script>'

# Inject into all HTML files: add CSS before </head>, add JS before </body>
find "$SITE_DIR" -name '*.html' -print0 | while IFS= read -r -d '' f; do
  # Skip pagefind's own files
  [[ "$f" == *"/pagefind/"* ]] && continue

  # Add Pagefind CSS before </head>
  if ! grep -q 'pagefind-ui.css' "$f"; then
    if sed --version 2>/dev/null | grep -q GNU; then
      sed -i "s|</head>|${PAGEFIND_CSS}\n</head>|" "$f"
    else
      sed -i '' "s|</head>|${PAGEFIND_CSS}\\
</head>|" "$f"
    fi
  fi

  # Add Pagefind JS + init before </body>
  if ! grep -q 'pagefind-ui.js' "$f"; then
    if sed --version 2>/dev/null | grep -q GNU; then
      sed -i "s|</body>|${PAGEFIND_JS}\n${PAGEFIND_INIT}\n</body>|" "$f"
    else
      sed -i '' "s|</body>|${PAGEFIND_JS}\\
${PAGEFIND_INIT}\\
</body>|" "$f"
    fi
  fi
done

# Replace existing Liferay search forms with Pagefind UI widget
echo ">>> Replacing Liferay search forms with Pagefind widget..."
find "$SITE_DIR" -name '*.html' -print0 | while IFS= read -r -d '' f; do
  [[ "$f" == *"/pagefind/"* ]] && continue

  # Replace search-bar-simple form with a Pagefind search div
  if grep -q 'search-bar-simple' "$f"; then
    if sed --version 2>/dev/null | grep -q GNU; then
      sed -i 's|<form[^>]*class="[^"]*search-bar-simple[^"]*"[^>]*>.*</form>|<div id="search"></div>|g' "$f"
    else
      sed -i '' 's|<form[^>]*class="[^"]*search-bar-simple[^"]*"[^>]*>.*</form>|<div id="search"></div>|g' "$f"
    fi
  fi
done

echo ">>> Pagefind injection complete."
