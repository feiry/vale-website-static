"""pagecontent_common.py — shared editable-content scanner for the page-content tools.

Used by extract-page-content.py and inject-page-content.py so both walk a page's
editable elements the SAME way (identical ordering and byte offsets). Keeping this
in one module is what makes the extract→inject round-trip lossless.

A Vale/Liferay page marks its editable content with `data-lfr-editable-type="..."`
attributes inside a single `id="main-content"` region. This scanner finds each such
element in document order and records the byte span of its editable payload:
  - text / rich-text / html / link : the INNER content (between `>` and the matching
    close tag). `link` also exposes its `href` attribute span.
  - image                          : the `src` and `alt` attribute value spans.

We work on raw bytes/offsets and never reserialize the HTML — the 500 KB pages must
stay byte-identical outside the specific spans we choose to change.
"""

import re
import hashlib

EDITABLE_TYPES = {"text", "rich-text", "html", "link", "image"}

# Void elements never have a separate close tag.
_VOID = {"img", "br", "hr", "input", "source", "meta", "link"}

_MAIN_RE = re.compile(r'id="main-content"')
# One editable element: capture the tag name and the attribute-carrying opening tag.
_EDITABLE_RE = re.compile(
    r'<(?P<tag>[a-zA-Z0-9]+)(?P<attrs>[^>]*\sdata-lfr-editable-type="(?P<etype>[a-z-]+)"[^>]*)>'
)
_ATTR_RE = lambda name: re.compile(r'\s' + name + r'="(?P<val>[^"]*)"')


class PageStructureError(Exception):
    """The page doesn't have the expected single main-content region."""


def find_main_content(html):
    """Return (start, end) byte offsets of the main-content region to scan.

    start = just after the main-content opening tag's `>`.
    end   = end of the file (footer chrome lives after, but editables only appear
            inside the content area; the region bound is enforced by only accepting
            editables and by the fingerprint — see the module docstring). We bound at
            the LAST `</div>` before the footer copyright block when present, else EOF.
    """
    m = _MAIN_RE.search(html)
    if not m:
        raise PageStructureError('no id="main-content" found')
    if _MAIN_RE.search(html, m.end()):
        raise PageStructureError('multiple id="main-content" found')
    start = html.index(">", m.end()) + 1
    # Bound before the footer fragment if we can find it (keeps stray editables in
    # footer/menus out); otherwise scan to EOF (editables past content are rare).
    foot = html.find('lfr-layout-structure-item-footer', start)
    end = foot if foot != -1 else len(html)
    return start, end


def _match_close(html, tag, after):
    """Return the offset where the inner content ends (start of the matching close
    tag) for an element of `tag` whose opening tag ended at `after`. Handles nesting
    of same-tag children by depth counting."""
    open_re = re.compile(r'<' + tag + r'(?:\s[^>]*)?>', re.IGNORECASE)
    close_re = re.compile(r'</' + tag + r'\s*>', re.IGNORECASE)
    depth = 1
    pos = after
    while depth:
        no = open_re.search(html, pos)
        nc = close_re.search(html, pos)
        if nc is None:
            raise PageStructureError(f"unterminated <{tag}> at {after}")
        if no is not None and no.start() < nc.start():
            depth += 1
            pos = no.end()
        else:
            depth -= 1
            pos = nc.end()
            if depth == 0:
                return nc.start()
    return pos


def scan_editables(html):
    """Return an ordered list of editable descriptors within main-content.

    Each descriptor is a dict:
      { "type": <etype>, "tag": <tagname>,
        "inner": (s, e)          # for text/rich-text/html/link: inner-content span
        "src":   (s, e),         # for image: src value span
        "alt":   (s, e) or None, # for image: alt value span
        "href":  (s, e) or None, # for link: href value span
        "hint":  <short label>   # human context (from id / nearby heading text)
      }
    Spans are (start, end) byte offsets into `html`.
    """
    cstart, cend = find_main_content(html)
    out = []
    for m in _EDITABLE_RE.finditer(html, cstart, cend):
        etype = m.group("etype")
        tag = m.group("tag").lower()
        attrs = m.group("attrs")
        attrs_off = m.start("attrs")
        desc = {"type": etype, "tag": tag, "inner": None, "src": None,
                "alt": None, "href": None, "hint": ""}

        # element-id hint
        idm = _ATTR_RE("data-lfr-editable-id").search(attrs)
        desc["hint"] = idm.group("val") if idm else ""

        if etype == "image" or tag in _VOID:
            for name in ("src", "alt", "href"):
                am = _ATTR_RE(name).search(attrs)
                if am:
                    desc[name] = (attrs_off + am.start("val"), attrs_off + am.end("val"))
        else:
            inner_start = m.end()
            inner_end = _match_close(html, tag, inner_start)
            desc["inner"] = (inner_start, inner_end)
            if etype == "link":
                am = _ATTR_RE("href").search(attrs)
                if am:
                    desc["href"] = (attrs_off + am.start("val"), attrs_off + am.end("val"))
        out.append(desc)
    return out


def type_sequence(editables):
    return ",".join(e["type"] for e in editables)


def type_sequence_sha(editables):
    return hashlib.sha256(type_sequence(editables).encode("utf-8")).hexdigest()[:16]


def file_sha(html):
    return hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
