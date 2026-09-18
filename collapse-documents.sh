#!/usr/bin/env bash
# Collapse Liferay UUID document filenames safely. Portable to bash 3.2 (macOS) and 4+.
#
# Liferay stores documents as:  documents/.../image.png/<UUID>@version=X&t=NNN
# i.e. the human filename ("image.png") is a DIRECTORY and the real bytes live in a
# UUID-named child. S3/CloudFront/Azure can't serve @,=,& in URL keys, so we collapse
# the bytes up to the human filename: documents/.../image.png
#
# ROOT-CAUSE FIX (was: silent data loss). The previous version did, per versioned file:
#     mv <file> tmp ; rm -rf <parent_dir> ; mv tmp <parent_name>
# When a human-filename dir held MORE THAN ONE versioned file, it moved the first out
# then `rm -rf`'d the whole dir — destroying the remaining siblings. Single-file dirs
# hid the bug; multi-version dirs (more likely once ID + EN docs are both crawled) lose
# data. This version groups by parent dir, keeps the highest version as the canonical
# name, PRESERVES losing versions as <name>.v<ver>, and never `rm -rf`s a dir that
# could hold unrelated content (e.g. documents/d/guest/* is never touched — those files
# are not @version/&t entries).
#
# Usage: collapse-documents.sh <SITE_DIR>   (SITE_DIR contains documents/)

set -uo pipefail
SITE_DIR="${1:?usage: collapse-documents.sh <SITE_DIR>}"
DOCS="$SITE_DIR/documents"
[ -d "$DOCS" ] || { echo "  (no documents/ dir, skipping collapse)"; exit 0; }

# version sort key from a basename "NAME@version=X&t=Y" → "<ver>|<t>", zero-padded.
vkey() {
  ver=$(printf '%s' "$1" | sed -nE 's/.*@version=([0-9.]+).*/\1/p'); [ -n "$ver" ] || ver=0
  t=$(printf '%s' "$1" | sed -nE 's/.*[&?]t=([0-9]+).*/\1/p'); [ -n "$t" ] || t=0
  printf '%020s|%020s' "$ver" "$t"
}

# List of distinct parent dirs that contain versioned UUID files (NUL-safe, then unique).
parent_list=$(mktemp)
find "$DOCS" -type f \( -name '*@version=*' -o -name '*&t=*' \) -print0 2>/dev/null \
  | while IFS= read -r -d '' fp; do dirname "$fp"; done | sort -u > "$parent_list"

collapsed=0; preserved=0
while IFS= read -r parent_dir; do
  [ -n "$parent_dir" ] || continue
  grandparent=$(dirname "$parent_dir")
  parent_name=$(basename "$parent_dir")          # e.g. image.png
  # target == parent_dir by construction: we collapse the human-filename DIRECTORY
  # into a FILE at the same path (moving the winning UUID file up to replace the dir).
  target="$parent_dir"

  # Versioned files directly in this dir.
  members_file=$(mktemp)
  find "$parent_dir" -maxdepth 1 -type f \( -name '*@version=*' -o -name '*&t=*' \) -print0 2>/dev/null \
    | while IFS= read -r -d '' m; do printf '%s\t%s\n' "$(vkey "$(basename "$m")")" "$m"; done \
    | sort > "$members_file"   # ascending by version key; last line = winner
  [ -s "$members_file" ] || { rm -f "$members_file"; continue; }

  winner=$(tail -n1 "$members_file" | cut -f2-)

  # Does the dir hold anything OTHER than versioned files? If so, never remove it.
  other_count=$(find "$parent_dir" -mindepth 1 ! \( -name '*@version=*' -o -name '*&t=*' \) 2>/dev/null | wc -l | tr -d ' ')

  tmp="$grandparent/.tmp_collapse_$$_$RANDOM"
  if mv -- "$winner" "$tmp" 2>/dev/null; then
    # Preserve losing siblings as <target>.v<ver> (no data loss).
    while IFS=$'\t' read -r _ m; do
      [ -n "$m" ] && [ "$m" != "$winner" ] && [ -e "$m" ] || continue
      ver=$(basename "$m" | sed -nE 's/.*@version=([0-9.]+).*/\1/p'); [ -n "$ver" ] || ver=x
      keep="$target.v$ver"
      while [ -e "$keep" ]; do keep="$keep~"; done
      mv -- "$m" "$keep" 2>/dev/null && preserved=$((preserved+1))
    done < "$members_file"

    # Remove the UUID dir ONLY if it now holds nothing else.
    remaining=$(find "$parent_dir" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')
    if [ "$remaining" -eq 0 ] && [ "$other_count" -eq 0 ]; then
      rmdir -- "$parent_dir" 2>/dev/null || true
    fi

    # Put the winner in place. If the human-filename dir still exists (had other
    # content), park the winner inside it rather than clobbering.
    if [ -d "$target" ]; then
      mv -- "$tmp" "$target/_collapsed_$parent_name" 2>/dev/null || rm -f -- "$tmp"
    else
      mv -- "$tmp" "$target" 2>/dev/null || rm -f -- "$tmp"
    fi
    collapsed=$((collapsed+1))
  fi
  rm -f "$members_file"
done < "$parent_list"
rm -f "$parent_list"

echo "  collapsed $collapsed document name(s); preserved $preserved extra version(s)"
