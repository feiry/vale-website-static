#!/usr/bin/env python3
"""intake-to-news.py — convert a COMMs news request into a validated news record.

Primary input is the `news-record.json` saved by the visual news form
(make-news-editor.py). A `.md` front-matter request is also accepted as a legacy
path. Either way it produces a JSON record appended to site-data/news-indonesia.json,
which build-news.py then renders into the EN + ID listings and article pages.

This script NEVER deploys. It only validates and mutates the data file, self-checking
that the result still parses so it can never hand build-news.py a file that aborts the
build (build-news.py exits 1 on invalid JSON).

Usage:
    python3 intake-to-news.py path/to/request.md
    python3 intake-to-news.py path/to/request.md --dry-run   # validate + print, don't write

Design notes:
- No external dependencies (no pyyaml / markdown package). The front-matter is a simple
  `key: value` block and the body is a small, purpose-built Markdown subset, so the tool
  runs on any machine with Python 3.
- Slug, category allowlist and the data-file path are imported from build-news.py so the
  two stay in lock-step (same slug normalization, same chip allowlist).
- Body images use the mirror convention /documents/d/guest/<name> where <name> ends in
  `-png` / `-jpg` (no dot), matching fetch-body-images.py and the existing records.
"""

import os
import re
import sys
import json
import html
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Reuse the exact slug logic, chip allowlist, and data-file path from the builder.
# build-news.py has a hyphen so it isn't importable by name — load it via importlib.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "build_news", os.path.join(SCRIPT_DIR, "build-news.py")
)
_bn = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_bn)
sanitize_slug = _bn.sanitize_slug
FILTER_CHIP_ALLOWLIST = _bn.FILTER_CHIP_ALLOWLIST
DATA_FILE = _bn.DATA_FILE

# Baseline region/scope tags every published Indonesia article carries (matches the
# existing data set). COMMs picks ONE operational/ESG chip; GDI/this tool adds these.
BASELINE_CATEGORIES = ["Indonesia", "Indonesia news"]


def resolve_categories(raw):
    """Normalize a category input into the final list (baseline + validated picks).

    Accepts `categories` (list, from the visual form's multi-select), a comma-separated
    string, or a single `category` string (legacy / markdown). One OR MORE picks
    allowed; empty is allowed (baseline tags only). Raises IntakeError on any pick not
    in the allowlist.
    """
    if isinstance(raw, str):
        raw = [c.strip() for c in raw.split(",") if c.strip()]
    picked = [str(c).strip() for c in (raw or []) if str(c).strip()]
    bad = [c for c in picked if c not in FILTER_CHIP_ALLOWLIST]
    if bad:
        raise IntakeError(
            f"category {bad!r} not allowed. Choose from: "
            f"{', '.join(sorted(FILTER_CHIP_ALLOWLIST))}."
        )
    categories = list(BASELINE_CATEGORIES)
    for c in picked:
        if c not in categories:
            categories.append(c)
    return categories

# Body images are served extensionless under this prefix (fetch-body-images.py convention).
BODY_IMAGE_PREFIX = "/documents/d/guest/"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IMG_MARKER_RE = re.compile(r"\[IMG:\s*([^\]]+?)\s*\]")

# Image extensions we accept for cover + body images.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def strip_inline_font_family(html_body):
    """Remove inline `font-family:` declarations from pasted body HTML so the site's
    Vale Sans applies. COMMs authors in Word/Outlook/Docs, whose paste injects
    `font-family: "Segoe UI"|Calibri|Aptos|…` on wrapper divs, overriding Vale Sans
    (COMMs flagged this on the DEN article, 2026-09-17). We drop ONLY the font-family
    declaration, leaving other inline style (color/size/line-height) untouched, and
    clean up any now-empty `style=""`. Handles both raw `"` and HTML-escaped `&quot;`.
    """
    if not html_body:
        return html_body
    # A font-family value runs until the next REAL ';' (declaration end) or the closing '"'
    # of the style attribute. The trap: `&quot;` contains a ';', so we must consume `&quot;`
    # as an atomic unit and only stop on a bare ';' or '"'. Each token is either a `&quot;`
    # entity or any char that is not ';' or '"'. Trailing ';' (and surrounding space) eaten.
    body = re.sub(r'font-family\s*:\s*(?:&quot;|[^;"])*\s*;?\s*', '', html_body)
    # tidy leftovers from removed declarations
    body = re.sub(r'style="\s*;\s*', 'style="', body)   # `style="; …"` -> `style="…"`
    body = re.sub(r';\s*;', ';', body)                    # doubled semicolons
    body = re.sub(r'\s+style="\s*"', '', body)            # now-empty style attr (with leading space)
    body = re.sub(r'style="\s*"', '', body)               # empty style attr (no leading space)
    return body


class IntakeError(Exception):
    """A validation/parse failure with a message meant for the GDI operator."""


# ─── Front-matter + section parsing ───────────────────────────────────────────

def _split_front_matter(text):
    """Return (front_matter_dict, body_text) from a `--- ... ---` prefixed file."""
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        raise IntakeError(
            "Missing front-matter. A .md request must start with a `---` block "
            "(or use the news form's news-record.json instead)."
        )
    fm_block, body = m.group(1), m.group(2)
    fm = {}
    for raw in fm_block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise IntakeError(f"Front-matter line is not `key: value`: {raw!r}")
        key, val = line.split(":", 1)
        # Strip trailing inline `# comment` and surrounding quotes/whitespace.
        val = re.sub(r"\s+#.*$", "", val).strip().strip('"').strip("'")
        fm[key.strip().lower()] = val
    return fm, body


def _parse_lang_sections(body):
    """Split the body into EN and ID field blocks.

    Expects two `# EN` / `# ID` headings, each followed by
    `Title:` / `Subtitle:` / `Body:` (EN) or `Judul:` / `Subjudul:` / `Isi:` (ID).
    Returns {'en': {...}, 'id': {...}} with only the languages present.
    """
    # Locate the language headers (order-independent, case-insensitive).
    headers = list(re.finditer(r"(?im)^\#\s*(EN|ID)\s*$", body))
    if not headers:
        raise IntakeError("No `# EN` or `# ID` language section found in the body.")

    langs = {}
    for i, h in enumerate(headers):
        lang = h.group(1).lower()
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
        block = body[start:end]
        langs[lang] = _parse_one_lang_block(lang, block)
    return langs


# Field label -> canonical key, per language.
_LANG_LABELS = {
    "en": {"title": "title", "subtitle": "subtitle", "body": "body"},
    "id": {"judul": "title", "subjudul": "subtitle", "isi": "body"},
}


def _parse_one_lang_block(lang, block):
    labels = _LANG_LABELS[lang]
    # Build a regex matching any label at the start of a line.
    label_alt = "|".join(re.escape(k) for k in labels)
    field_re = re.compile(rf"(?im)^({label_alt})\s*:\s*", re.MULTILINE)

    matches = list(field_re.finditer(block))
    if not matches:
        raise IntakeError(f"`# {lang.upper()}` section has no recognised fields.")

    out = {}
    for i, m in enumerate(matches):
        label = m.group(1).lower()
        key = labels[label]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        raw = block[start:end].strip()
        # Support the YAML block-scalar `|` on the Body/Isi line.
        if raw.startswith("|"):
            raw = raw[1:].lstrip("\n")
            raw = _dedent(raw)
        out[key] = raw.strip()
    return out


def _dedent(text):
    lines = text.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    if not indents:
        return text
    cut = min(indents)
    return "\n".join(l[cut:] if len(l) >= cut else l for l in lines)


# ─── Markdown subset → sanitized HTML ─────────────────────────────────────────

def _inline_md(text):
    """Convert inline Markdown (bold/italic/links) with everything HTML-escaped first."""
    text = html.escape(text, quote=False)
    # links [text](url) — url restricted to http(s)/relative to avoid javascript: etc.
    def _link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"^(https?:|/|#|mailto:)", url):
            url = "#"
        return f'<a href="{html.escape(url, quote=True)}">{label}</a>'
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_html(md, slug, folder, image_registry):
    """Convert the body Markdown subset to the <p>/<h2>/<h3>/<ul>/<img> HTML the site uses.

    Supported: blank-line-separated paragraphs, `## h2`, `### h3`, `- ` bullet lists,
    inline **bold** / *italic* / [links](url), and `[IMG: file.jpg]` markers on their
    own line. Every referenced image is recorded in image_registry (filename -> on-disk
    dest path) for the caller to verify + place.
    """
    # Normalise line endings, split on blank lines into blocks.
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", md.strip())
    out_parts = []
    img_counter = [0]

    def emit_image(fname):
        img_counter[0] += 1
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_EXTS:
            raise IntakeError(
                f"[IMG: {fname}] has an unsupported extension {ext!r}. "
                f"Allowed: {', '.join(sorted(IMAGE_EXTS))}."
            )
        # Mirror serves body images extensionless: name ends `-png`/`-jpg` (no dot).
        served_name = f"{slug}-{img_counter[0]}{ext}".replace(".", "-")
        src = BODY_IMAGE_PREFIX + served_name
        dest = os.path.join(
            "site", "vale.com", "documents", "d", "guest", served_name
        )
        image_registry[fname] = dest
        return f'<p><img src="{src}"></p>'

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # A block that is exactly one image marker.
        only_img = IMG_MARKER_RE.fullmatch(block.strip())
        if only_img:
            out_parts.append(emit_image(only_img.group(1)))
            continue
        # Headings.
        if block.startswith("### "):
            out_parts.append(f"<h3>{_inline_md(block[4:].strip())}</h3>")
            continue
        if block.startswith("## "):
            out_parts.append(f"<h2>{_inline_md(block[3:].strip())}</h2>")
            continue
        # Bullet list (all lines start with `- `).
        lines = block.split("\n")
        if all(l.strip().startswith("- ") for l in lines):
            items = "".join(
                f"<li>{_inline_md(l.strip()[2:].strip())}</li>" for l in lines
            )
            out_parts.append(f"<ul>{items}</ul>")
            continue
        # Paragraph — inline images inside it become their own <p><img></p>.
        # Replace markers, then wrap remaining text.
        if IMG_MARKER_RE.search(block):
            # Split the paragraph around image markers.
            pos = 0
            for m in IMG_MARKER_RE.finditer(block):
                pre = block[pos:m.start()].strip()
                if pre:
                    out_parts.append(f"<p>{_inline_md(pre)}</p>")
                out_parts.append(emit_image(m.group(1)))
                pos = m.end()
            tail = block[pos:].strip()
            if tail:
                out_parts.append(f"<p>{_inline_md(tail)}</p>")
            continue
        paragraph = _inline_md(" ".join(l.strip() for l in lines))
        out_parts.append(f"<p>{paragraph}</p>")

    return "".join(out_parts)


# ─── Record assembly + validation ─────────────────────────────────────────────

def build_record(request_path):
    request_path = os.path.abspath(request_path)
    folder = os.path.dirname(request_path)
    with open(request_path, encoding="utf-8") as fh:
        text = fh.read()

    fm, body = _split_front_matter(text)

    rtype = fm.get("request_type", "news").lower()
    if rtype != "news":
        raise IntakeError(f"request_type is {rtype!r}, expected 'news'.")

    # Date.
    date = fm.get("date", "").strip()
    if not DATE_RE.match(date):
        raise IntakeError(f"date {date!r} is not in YYYY-MM-DD form.")

    # Categories — one or more chips from the allowlist; baseline tags added automatically.
    categories = resolve_categories(fm.get("categories", fm.get("category", [])))

    # Language sections.
    langs = _parse_lang_sections(body)
    if not langs:
        raise IntakeError("No EN or ID content parsed.")
    for lang, fields in langs.items():
        if not fields.get("title"):
            raise IntakeError(f"`# {lang.upper()}` section is missing a title.")

    # Slug: explicit suggestion, else derive from an available title.
    suggestion = fm.get("slug_suggestion", "").strip()
    if not suggestion:
        suggestion = (langs.get("en") or langs.get("id"))["title"]
    slug = sanitize_slug(suggestion)
    if not slug:
        raise IntakeError(f"slug {suggestion!r} normalises to empty.")

    # Cover.
    image_registry = {}  # attached filename -> on-disk dest
    cover_file = fm.get("cover_image", "").strip()
    cover = ""
    if cover_file:
        ext = os.path.splitext(cover_file)[1].lower()
        if ext not in IMAGE_EXTS:
            raise IntakeError(f"cover_image {cover_file!r} has unsupported extension {ext!r}.")
        # Covers keep their extension under /documents/44618/<slug>/.
        cover = f"/documents/44618/{slug}/{cover_file}"
        image_registry[cover_file] = os.path.join(
            "site", "vale.com", "documents", "44618", slug, cover_file
        )

    # Bodies (converts markdown, registers body images).
    rec = {"slug": slug, "date": date, "categories": categories, "cover": cover}
    for lang in ("en", "id"):
        if lang in langs:
            f = langs[lang]
            rec[lang] = {
                "title": f.get("title", "").strip(),
                "subtitle": f.get("subtitle", "").strip(),
                "body": markdown_to_html(
                    f.get("body", ""), slug, slug, image_registry
                ),
            }

    # Verify every referenced image exists in the request folder.
    missing = [fn for fn in image_registry if not os.path.isfile(os.path.join(folder, fn))]
    if missing:
        raise IntakeError(
            "These referenced images are not in the request folder "
            f"({folder}): {', '.join(missing)}"
        )

    return rec, image_registry, folder


def check_slug_unique(slug, records):
    for r in records:
        if sanitize_slug(r.get("slug", "")) == slug:
            raise IntakeError(
                f"slug {slug!r} already exists in news-indonesia.json. "
                "Set a different slug_suggestion in the request."
            )


def build_record_from_json(path):
    """Build a validated record from the visual news editor's news-record.json.

    The form already produced HTML bodies + a single `category` + a `cover_filename`,
    so this mirrors build_record()'s validation without the Markdown conversion:
    validate date + category, fold in baseline tags, sanitize slug, and map the
    referenced image filenames to their on-disk destinations. Returns the same
    (rec, image_registry, folder) tuple as build_record()."""
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    date = str(data.get("date", "")).strip()
    if not DATE_RE.match(date):
        raise IntakeError(f"date {date!r} is not in YYYY-MM-DD form.")

    # Categories — form sends `categories` (list); accept legacy single `category` too.
    categories = resolve_categories(data.get("categories", data.get("category", [])))

    if not (data.get("en") or data.get("id")):
        raise IntakeError("no EN or ID content in the record.")
    en_title = (data.get("en") or {}).get("title", "").strip()
    id_title = (data.get("id") or {}).get("title", "").strip()

    slug = sanitize_slug(data.get("slug") or en_title or id_title)
    if not slug:
        raise IntakeError("slug is empty after sanitization.")

    image_registry = {}  # filename -> on-disk dest
    cover = ""
    cover_file = str(data.get("cover_filename", "")).strip()
    if cover_file:
        cover = f"/documents/44618/{slug}/{cover_file}"
        image_registry[cover_file] = os.path.join(
            "site", "vale.com", "documents", "44618", slug, cover_file)

    rec = {"slug": slug, "date": date, "categories": categories, "cover": cover}
    for lang in ("en", "id"):
        blk = data.get(lang)
        if blk and (blk.get("title") or blk.get("body")):
            rec[lang] = {
                "title": blk.get("title", "").strip(),
                "subtitle": blk.get("subtitle", "").strip(),
                "body": strip_inline_font_family(blk.get("body", "")),  # HTML from editor; drop pasted font-family so Vale Sans wins
            }
            # body <img> served-paths → the filenames the editor listed to attach.
            for m in re.finditer(r'/documents/d/guest/([^"\']+)', blk.get("body", "")):
                served = m.group(0)
                # the editor names attachments by their ORIGINAL filename; we can't
                # recover it from the served path, so we only verify by served name
                # existing on disk at deploy — record the served path for the operator.
                image_registry.setdefault("(body image) " + served, served)

    return rec, image_registry, folder


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if len(args) != 1:
        print("usage: python3 intake-to-news.py path/to/request.md|news-record.json [--dry-run]", file=sys.stderr)
        sys.exit(2)

    is_json = args[0].lower().endswith(".json")
    try:
        rec, image_registry, folder = (build_record_from_json(args[0]) if is_json
                                       else build_record(args[0]))

        with open(DATA_FILE, encoding="utf-8") as fh:
            records = json.load(fh)
        if not isinstance(records, list):
            raise IntakeError(f"{DATA_FILE} is not a JSON array.")

        check_slug_unique(rec["slug"], records)
    except IntakeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    langs_present = [l for l in ("en", "id") if l in rec]
    print(f"✓ Parsed OK — slug: {rec['slug']}  date: {rec['date']}")
    print(f"  categories: {rec['categories']}")
    print(f"  languages: {', '.join(langs_present)}")
    print(f"  cover: {rec['cover'] or '(placeholder)'}")
    print(f"  output URLs:")
    if "en" in rec:
        print(f"    EN: /indonesia/w/{rec['slug']}.html")
    if "id" in rec:
        print(f"    ID: /in/indonesia/w/{rec['slug']}.html")
    if image_registry:
        print("  images to place on disk (copy from the request folder):")
        for fn, dest in image_registry.items():
            print(f"    {os.path.join(folder, fn)}  ->  {dest}")

    if dry_run:
        print("\n--dry-run: no changes written.")
        return

    # Back up, append, write.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{DATA_FILE}.bak-{stamp}"
    shutil.copy2(DATA_FILE, backup)
    records.append(rec)
    with open(DATA_FILE, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)

    # Self-check: the file we just wrote must parse.
    try:
        with open(DATA_FILE, encoding="utf-8") as fh:
            json.load(fh)
    except json.JSONDecodeError as e:
        shutil.copy2(backup, DATA_FILE)
        print(
            f"ERROR: wrote invalid JSON ({e}); restored from backup. No changes applied.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"\n✓ Appended record to {os.path.relpath(DATA_FILE, SCRIPT_DIR)}")
    print(f"  backup: {os.path.relpath(backup, SCRIPT_DIR)}")
    print("  Next: copy the images above onto disk, then run  python3 build-news.py")


if __name__ == "__main__":
    main()
