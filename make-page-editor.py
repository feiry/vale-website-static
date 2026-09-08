#!/usr/bin/env python3
"""make-page-editor.py — turn a page into a COMMs-friendly VISUAL editor.

Produces a single self-contained .html file that COMMs opens by double-clicking.
It shows the REAL, styled page (assets pulled from the live site) with ONLY the
editable text/images made editable in the browser. COMMs edits on top of the real
design, then clicks "Save changes" to download a small `content-*.json` file that
GDI feeds to inject-page-content.py — no «VAL» sentinels, no code, no jargon.

Usage:
    python3 make-page-editor.py <source-page.html> -o <page-editor.html> [--lang en|id]

How it stays safe + consistent with the injector:
  - We reuse pagecontent_common.scan_editables, so the editor tags exactly the same
    editable elements, in the same document order (index i here == index i in inject).
  - Only those elements become editable; all chrome/layout is view-only.
  - Save exports { "index": {type, value...} } which inject reads via --editor-json.
"""

import os
import re
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from pagecontent_common import (  # noqa: E402
    scan_editables, type_sequence_sha, file_sha, find_main_content, PageStructureError,
)

LIVE = "https://www.valeindonesia.com"


def _rewrite_assets(html):
    """Point root-relative assets at the live site so a double-clicked file renders."""
    # href="/..." and src="/..." -> live absolute. Leave anchors (#), data:, http(s) alone.
    html = re.sub(r'(\b(?:href|src))="/(?!/)', rf'\1="{LIVE}/', html)
    # srcset entries "/foo 1x, /bar 2x"
    html = re.sub(r'(\bsrcset=")(/[^"]*)"',
                  lambda m: m.group(1) + re.sub(r'(^|,\s*)/', rf'\1{LIVE}/', m.group(2)) + '"',
                  html)
    return html


def _strip_scripts(html):
    """Remove <script>…</script> and the meta-refresh redirect — the editor is a static
    view; the page's dynamic JS would fight the editing overlay."""
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<meta[^>]+http-equiv="refresh"[^>]*>', '', html, flags=re.IGNORECASE)
    return html


# The editor chrome (toolbar + logic) injected before </body>.
EDITOR_JS_TEMPLATE = r"""
<style>
/* `.animacao-item.bg-branco` is a decorative full-size WHITE panel that the page's JS
   animates away on scroll to reveal the content beneath it. With the JS stripped for
   editing it just sits there as an opaque white cover, masking a whole section (looks
   "empty"). It carries no editable content, so hide it in the editor. */
.animacao-item.bg-branco{ display:none !important; }
/* Reveal any other scroll-animation blocks that start hidden (opacity/transform), so
   nothing is invisible in the editor. NARROW: does not touch Bootstrap d-none or
   carousel .fade (avoids revealing hidden responsive twins / inactive slides). */
[class*="animacao"]:not(.bg-branco){
  opacity:1 !important; visibility:visible !important; transform:none !important;
  animation:none !important; transition:none !important;
}
/* Editable elements themselves must always be visible so COMMs can edit them. */
[data-gdi-edit]{ opacity:1 !important; visibility:visible !important; }
#gdi-bar{position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#00533f;color:#fff;
  font-family:Calibri,Arial,sans-serif;padding:10px 16px;display:flex;align-items:center;gap:14px;
  box-shadow:0 2px 8px rgba(0,0,0,.3)}
#gdi-bar b{color:#F2A900}
#gdi-bar .sp{flex:1}
#gdi-bar button{background:#F2A900;color:#111;border:0;border-radius:4px;padding:8px 16px;
  font-weight:bold;font-size:14px;cursor:pointer}
#gdi-bar button.ghost{background:transparent;color:#fff;border:1px solid #fff}
body{padding-top:52px !important}
[data-gdi-edit]{outline:2px dashed rgba(0,122,94,.0);transition:outline .15s;cursor:text}
[data-gdi-edit]:hover{outline:2px dashed #007a5e;outline-offset:2px}
[data-gdi-edit].gdi-img{cursor:pointer}
[data-gdi-changed]{outline:2px solid #F2A900 !important;outline-offset:2px}
#gdi-note{position:fixed;bottom:14px;left:14px;z-index:2147483647;background:#111;color:#fff;
  font-family:Calibri;font-size:13px;padding:8px 12px;border-radius:6px;opacity:.9;max-width:360px}
</style>
<div id="gdi-bar">
  <span>✏️ <b>PT Vale</b> — editing: <span id="gdi-page">__PAGE__</span> (<span id="gdi-lang">__LANG__</span>)</span>
  <span class="sp"></span>
  <span id="gdi-count" style="opacity:.85"></span>
  <button class="ghost" onclick="gdiReset()">Undo all</button>
  <button onclick="gdiSave()">Save changes ⤓</button>
</div>
<div id="gdi-note">Click any highlighted text to edit it. Click a highlighted image to replace it.
When done, click <b>Save changes</b> and send the downloaded file back to GDI.</div>
<script>
const GDI_META = __META__;              // {page, lang, count, type_sequence_sha, source_page_sha}
const GDI_TYPES = __TYPES__;            // ordered list of editable types
const gdiOrig = {};                     // index -> original serialized value
const gdiImgFiles = {};                 // index -> chosen filename (for images)

function gdiEls(){ return document.querySelectorAll('[data-gdi-edit]'); }

function gdiInit(){
  gdiEls().forEach(el=>{
    const i = +el.getAttribute('data-gdi-index');
    const type = el.getAttribute('data-gdi-type');
    if(type==='image'){
      el.classList.add('gdi-img');
      gdiOrig[i] = el.getAttribute('src')||'';
      el.addEventListener('click', ()=>gdiPickImage(el,i));
    }else{
      el.setAttribute('contenteditable','true');
      gdiOrig[i] = el.innerHTML;
      el.addEventListener('input', ()=>{ el.setAttribute('data-gdi-changed','1'); gdiCount(); });
    }
  });
  gdiCount();
}
function gdiPickImage(el,i){
  const inp=document.createElement('input'); inp.type='file'; inp.accept='image/*';
  inp.onchange=()=>{ const f=inp.files[0]; if(!f)return;
    gdiImgFiles[i]=f.name;
    const rd=new FileReader(); rd.onload=()=>{ el.src=rd.result; }; rd.readAsDataURL(f);
    el.setAttribute('data-gdi-changed','1'); gdiCount();
  };
  inp.click();
}
function gdiCount(){
  const n=document.querySelectorAll('[data-gdi-changed]').length;
  document.getElementById('gdi-count').textContent = n? (n+' change'+(n>1?'s':'')) : '';
}
function gdiReset(){
  gdiEls().forEach(el=>{
    const i=+el.getAttribute('data-gdi-index');
    if(el.getAttribute('data-gdi-type')==='image'){ el.src=gdiOrig[i]; delete gdiImgFiles[i]; }
    else el.innerHTML=gdiOrig[i];
    el.removeAttribute('data-gdi-changed');
  });
  gdiCount();
}
function gdiSave(){
  const out={ _meta: GDI_META, values:{} };
  gdiEls().forEach(el=>{
    const i=+el.getAttribute('data-gdi-index');
    const type=el.getAttribute('data-gdi-type');
    if(type==='image'){
      if(el.hasAttribute('data-gdi-changed') && gdiImgFiles[i]) out.values[i]={type:'image', new:gdiImgFiles[i]};
    }else{
      if(el.hasAttribute('data-gdi-changed')) out.values[i]={type:type, inner:el.innerHTML};
    }
  });
  const blob=new Blob([JSON.stringify(out,null,2)],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob);
  a.download='content-'+GDI_META.lang+'.json';
  a.click();
  const imgs=Object.values(gdiImgFiles);
  alert('Saved content-'+GDI_META.lang+'.json to your Downloads.\n\n'
    + (imgs.length? ('Also attach these image files to the folder:\n- '+imgs.join('\n- ')) : 'No image changes.')
    + '\n\nSend the folder back to GDI.');
}
document.addEventListener('DOMContentLoaded', gdiInit);
</script>
"""


def build_editor(path, lang):
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    find_main_content(html)
    editables = scan_editables(html)

    # Tag each editable element in place (right-to-left so offsets stay valid).
    # We insert  data-gdi-edit data-gdi-index=i data-gdi-type=t  into the opening tag.
    # For text/rich-text/html/link we tag the element itself; for image the <img>.
    # Opening tag start = we need the '<tag ... >' start offset. Recompute via a scan of
    # the element start: the editable regex in common matched the opening tag; re-find it.
    edits = []
    for i, e in enumerate(editables):
        # locate this element's opening-tag start: for text the inner span start is just
        # after '>', so search backwards for the last '<tag' before it. For image use src.
        if e["type"] == "image":
            anchor = e["src"][0] if e["src"] else None
        else:
            anchor = e["inner"][0] if e["inner"] else None
        if anchor is None:
            continue
        tag_open = html.rfind("<", 0, anchor)
        # insert attributes right after the tag name
        m = re.match(r'<([a-zA-Z0-9]+)', html[tag_open:])
        ins_at = tag_open + m.end()
        attrs = f' data-gdi-edit data-gdi-index="{i}" data-gdi-type="{e["type"]}"'
        edits.append((ins_at, attrs))
    edits.sort(key=lambda x: x[0], reverse=True)
    for pos, attrs in edits:
        html = html[:pos] + attrs + html[pos:]

    html = _strip_scripts(html)
    html = _rewrite_assets(html)

    meta = {
        "page": os.path.basename(path),
        "lang": lang,
        "count": len(editables),
        "type_sequence_sha": type_sequence_sha(editables),
        "source_page_sha": file_sha(open(path, encoding="utf-8").read()),
    }
    js = (EDITOR_JS_TEMPLATE
          .replace("__PAGE__", meta["page"])
          .replace("__LANG__", lang)
          .replace("__META__", json.dumps(meta))
          .replace("__TYPES__", json.dumps([e["type"] for e in editables])))
    if "</body>" in html:
        html = html.replace("</body>", js + "\n</body>", 1)
    else:
        html += js
    return html


def main():
    argv = sys.argv[1:]
    out = None; lang = None
    if "-o" in argv:
        i = argv.index("-o"); out = argv[i + 1]; del argv[i:i + 2]
    if "--lang" in argv:
        i = argv.index("--lang"); lang = argv[i + 1]; del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("-")]
    if len(args) != 1 or not out:
        print("usage: python3 make-page-editor.py <source.html> -o <editor.html> [--lang en|id]",
              file=sys.stderr)
        sys.exit(2)
    src = args[0]
    if lang is None:
        lang = "id" if "/in/" in os.path.abspath(src).replace(os.sep, "/") else "en"
    try:
        out_html = build_editor(src, lang)
    except PageStructureError as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(out_html)
    print(f"✓ editor written -> {out}  (lang={lang}) — COMMs double-clicks this to edit visually")


if __name__ == "__main__":
    main()
