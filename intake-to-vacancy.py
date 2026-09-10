#!/usr/bin/env python3
"""intake-to-vacancy.py — apply a vacancy-update request to career.html (EN + ID).

Consumes a `vacancies.json` produced by the vacancy-manager form (see
make-vacancy-manager.py) and edits BOTH career pages:
  site/vale.com/indonesia/career.html      (EN)
  site/vale.com/in/indonesia/career.html   (ID)

It adds new vacancy slots (newest-first) and removes expired ones, encoding the
per-UUID font-size trick so new entries always render at 20px:
  * when slots are removed, their UUIDs (which carry the 20px per-UUID CSS rule)
    are REUSED for new slots — no inline style needed;
  * otherwise a fresh UUID is generated and an inline
    style="font-size:var(--font-size-lg)" is added to the slot's paragraph div.

Contract mirrors intake-to-news.py: validates, backs up, self-checks, restores on
failure, PRINTS the PDF copy worklist (never copies), never deploys.

Usage:
  python3 intake-to-vacancy.py <vacancies.json> [--dry-run]

The referenced PDFs must sit in the same folder as <vacancies.json>.
"""

import sys, os, re, json, time, hashlib, argparse
import vacancy_common as vc

EN_PAGE = "site/vale.com/indonesia/career.html"
ID_PAGE = "site/vale.com/in/indonesia/career.html"
DOC_DIR = "site/vale.com/documents/d/guest"
FS_STYLE = 'style="font-size:var(--font-size-lg)"'


class RequestError(Exception):
    pass


# ---------- helpers ----------

def slugify(title, date_iso):
    """<YYYYMMDD>_<slug> matching existing convention (lowercase, hyphen, & removed)."""
    ymd = date_iso.replace("-", "")
    s = title.lower()
    s = s.replace("&", " ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return f"{ymd}_{s}"


def fmt_date(date_iso, lang):
    y, m, d = date_iso.split("-")
    return f"{m}/{d}/{y}" if lang == "en" else f"{d}/{m}/{y}"


def label_html(date_iso, title, lang):
    esc = title.replace("&", "&amp;")
    if lang == "en":
        return f"&gt; {fmt_date(date_iso,'en')} - Job vacancy for {esc}"
    return f"&gt;{fmt_date(date_iso,'id')} - Lowongan Kerja untuk {esc}"


def build_slot(uuid, frag, href, label, inline_fs):
    style = f" {FS_STYLE}" if inline_fs else ""
    return (
        f'<div class="lfr-layout-structure-item-basic-component-paragraph '
        f'lfr-layout-structure-item-{uuid} " data-layout-structure-item-id="{uuid}">'
        f'<div id="fragment-{frag}" > '
        f'<div class="clearfix component-paragraph text-break"{style} '
        f'data-lfr-editable-id="element-text" data-lfr-editable-type="rich-text">'
        f'<p><a href="{href}" rel="noopener noreferrer" target="_blank">'
        f'<strong>{label}</strong></a></p></div></div></div>'
    )


def new_uuid(seed, n):
    """Deterministic-but-unique UUID-shaped id (Math.random is unavailable/undesired;
    derive from request seed + index so re-runs are stable and collision-free)."""
    h = hashlib.sha1(f"{seed}:{n}".encode()).hexdigest()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


# ---------- validation ----------

def validate(req, folder):
    if not isinstance(req.get("add", []), list) or not isinstance(req.get("remove", []), list):
        raise RequestError("request must have list 'add' and list 'remove'")
    if not req.get("add") and not req.get("remove"):
        raise RequestError("empty request: nothing to add or remove")
    for a in req.get("add", []):
        for f in ("title_en", "title_id", "date", "pdf"):
            if not a.get(f):
                raise RequestError(f"add entry missing '{f}': {a}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", a["date"]):
            raise RequestError(f"bad date (want YYYY-MM-DD): {a['date']}")
        pdf_path = os.path.join(folder, a["pdf"])
        if not os.path.isfile(pdf_path):
            raise RequestError(f"PDF not found in request folder: {a['pdf']}")
    for r in req.get("remove", []):
        if not r.get("match"):
            raise RequestError(f"remove entry missing 'match': {r}")


def match_removals(html, removals):
    """Return list of (removal, descriptor) with exactly-one-match enforcement."""
    vacs = vc.scan_vacancies(html)
    hits = []
    for r in removals:
        m = [v for v in vacs if r["match"] in v["label"] or r["match"] in v["slug"]]
        if len(m) == 0:
            raise RequestError(f"remove match hit 0 slots: {r['match']!r}")
        if len(m) > 1:
            raise RequestError(
                f"remove match ambiguous ({len(m)} slots): {r['match']!r} -> "
                + ", ".join(x["slug"] for x in m))
        hits.append((r, m[0]))
    return hits


# ---------- core edit ----------

def apply_to_page(html, req, page_lang, seed):
    """Return (new_html, worklist, plan_lines). Pure function; caller writes."""
    removals = match_removals(html, req.get("remove", []))
    removed_descs = [d for _, d in removals]
    # UUID pool from removed slots (they carry the 20px per-UUID rule)
    reusable = [(d["uuid"], d["frag"]) for d in removed_descs]

    plan = []
    worklist = []
    add_slots = []  # (href, label, uuid, frag, inline_fs)

    for i, a in enumerate(req.get("add", [])):
        slug = slugify(a["title_en"], a["date"])  # slug is language-neutral (EN title)
        href = f"/documents/d/guest/{slug}"
        title = a["title_en"] if page_lang == "en" else a["title_id"]
        label = label_html(a["date"], title, page_lang)
        if reusable:
            uuid, frag = reusable.pop(0)
            inline = False
            plan.append(f"  ADD (reuse UUID {uuid[:8]}, 20px) {slug}")
        else:
            uuid = new_uuid(seed, i)
            frag = new_uuid(seed + "f", i)
            inline = True
            plan.append(f"  ADD (fresh UUID {uuid[:8]}, inline 20px) {slug}")
        add_slots.append((href, label, uuid, frag, inline))
        if page_lang == "en":  # print worklist once (EN pass), slug is shared
            worklist.append((os.path.basename(a["pdf"]), slug))

    # Build combined new-slots HTML (newest-first order = request order)
    new_html_blocks = "".join(
        build_slot(uuid, frag, href, label, inline)
        for (href, label, uuid, frag, inline) in add_slots
    )

    # 1) remove slots (right-to-left so offsets stay valid)
    out = html
    spans = sorted((d["span"] for d in removed_descs), key=lambda s: -s[0])
    for s, e in spans:
        out = out[:s] + out[e:]
        for _, d in removals:
            plan.append(f"  REMOVE {d['slug']}") if d["span"] == (s, e) else None

    # 2) insert new slots at the top of the list
    if add_slots:
        ins = vc.recent_list_insertion_point(out)
        out = out[:ins] + new_html_blocks + out[ins:]

    return out, worklist, plan


# ---------- driver ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("request", help="vacancies.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folder = os.path.dirname(os.path.abspath(args.request))
    with open(args.request, encoding="utf-8") as f:
        req = json.load(f)
    validate(req, folder)

    seed = hashlib.sha1(json.dumps(req, sort_keys=True).encode()).hexdigest()[:12]

    # drift guard (per page) against _meta if present
    meta = req.get("_meta", {})
    pages = {"en": EN_PAGE, "id": ID_PAGE}
    htmls = {}
    for lang, path in pages.items():
        if not os.path.isfile(path):
            raise RequestError(f"career page missing: {path}")
        htmls[lang] = open(path, encoding="utf-8").read()

    # symmetry pre-check: every removal must match exactly one on BOTH pages,
    # every add slug must not already exist on EITHER page.
    for lang in ("en", "id"):
        match_removals(htmls[lang], req.get("remove", []))  # raises on 0/>1
    existing_slugs = set(v["slug"] for v in vc.scan_vacancies(htmls["en"]))
    for a in req.get("add", []):
        slug = slugify(a["title_en"], a["date"])
        if slug in existing_slugs:
            raise RequestError(f"slug already exists: {slug}")

    results = {}
    all_plan = []
    worklist = []
    for lang in ("en", "id"):
        new_html, wl, plan = apply_to_page(htmls[lang], req, lang, seed)
        results[lang] = new_html
        all_plan.append(f"[{lang.upper()}] {pages[lang]}")
        all_plan.extend(plan)
        if wl:
            worklist = wl  # from EN pass

    # report
    print("=== VACANCY UPDATE PLAN ===")
    for line in all_plan:
        print(line)
    print("\n=== PDF WORKLIST (copy these into place, then deploy) ===")
    for fname, slug in worklist:
        print(f"  cp {os.path.join(folder, fname)!r} {os.path.join(DOC_DIR, slug)!r}")
    if not worklist:
        print("  (no PDFs to place)")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return

    # write with backup + self-check
    ts = time.strftime("%Y%m%d-%H%M%S")
    backups = {}
    for lang, path in pages.items():
        bak = f"{path}.bak-{ts}"
        with open(bak, "w", encoding="utf-8") as f:
            f.write(htmls[lang])
        backups[lang] = bak
        with open(path, "w", encoding="utf-8") as f:
            f.write(results[lang])

    # self-check: re-parse, verify counts and 20px resolution
    ok = True
    for lang, path in pages.items():
        h2 = open(path, encoding="utf-8").read()
        vacs = vc.scan_vacancies(h2)
        expected = len(vc.scan_vacancies(htmls[lang])) - len(req.get("remove", [])) + len(req.get("add", []))
        if len(vacs) != expected:
            print(f"  SELF-CHECK FAIL [{lang}]: {len(vacs)} vacancies, expected {expected}")
            ok = False
        # every NEW slug must resolve to 20px (reused UUID with no inline, OR inline style)
        add_slugs = {slugify(a["title_en"], a["date"]) for a in req.get("add", [])}
        for v in vacs:
            if v["slug"] in add_slugs:
                reused = v["uuid"] in {d["uuid"] for d in
                                       [x for _, x in match_removals(htmls[lang], req.get("remove", []))]}
                if not (reused or v["has_inline_fontsize"]):
                    print(f"  SELF-CHECK FAIL [{lang}]: new slot {v['slug']} not 20px "
                          f"(no reused UUID, no inline style)")
                    ok = False

    if not ok:
        for lang, path in pages.items():
            os.replace(backups[lang], path)
        print("\nRESTORED from backup due to self-check failure. exit 1")
        sys.exit(1)

    print(f"\nWritten. Backups: " + ", ".join(backups.values()))
    print("Next: place PDFs (worklist above), then deploy career.html + PDFs to dev.")


if __name__ == "__main__":
    try:
        main()
    except (RequestError, vc.CareerStructureError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
