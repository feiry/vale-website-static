#!/usr/bin/env python3
"""make-news-editor.py — a visual, browser-based form for writing a news article.

Produces ONE self-contained .html file COMMs double-clicks to open. Instead of the
cryptic news-request.md, they get proper fields: Title/Subtitle/Body in EN + ID, a
category dropdown, a date picker, and a cover-image picker with live preview. The
Body areas are rich-text (bold / italic / heading / link / inline image). Clicking
"Save article" downloads a `news-record.json` that GDI feeds straight to
`intake-to-news.py --record-json`, which validates it and appends to
site-data/news-indonesia.json for build-news.py.

Usage:
    python3 make-news-editor.py -o new-article.html
    python3 make-news-editor.py --from <existing-slug> -o new-article.html   # pre-fill

Design: the form mirrors the news record schema exactly
    {slug, date, categories[], cover, en:{title,subtitle,body(html)}, id:{...}}
so its output needs no re-parsing — intake-to-news just validates + appends.
The category list + baseline tags come from build-news.py so they never drift.
"""

import os
import sys
import json
import html as htmllib

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("build_news", os.path.join(SCRIPT_DIR, "build-news.py"))
_bn = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bn)
FILTER_CHIP_ALLOWLIST = _bn.FILTER_CHIP_ALLOWLIST
DATA_FILE = _bn.DATA_FILE

# Order the chips the way build-news lists them (stable, human order).
CATEGORY_OPTIONS = ["IGP Morowali", "IGP Pomalaa", "IGP Sorlim", "People", "Social", "Sustainability"]
# keep only allow-listed (guards against drift)
CATEGORY_OPTIONS = [c for c in CATEGORY_OPTIONS if c in FILTER_CHIP_ALLOWLIST]


def _load_prefill(slug):
    """Return a record dict to pre-fill the form, or None."""
    if not slug:
        return None
    with open(DATA_FILE, encoding="utf-8") as fh:
        for rec in json.load(fh):
            if rec.get("slug") == slug:
                return rec
    raise SystemExit(f"ERROR: no article with slug {slug!r} in {os.path.basename(DATA_FILE)}")


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>New news article — PT Vale</title>
<style>
:root{--teal:#00795e;--teald:#00533f;--yellow:#F2A900;--grey:#5a5a5a;--line:#dce3e0;}
*{box-sizing:border-box}
body{margin:0;font-family:Calibri,-apple-system,Arial,sans-serif;color:#222;background:#eef2f0;}
#bar{position:sticky;top:0;z-index:10;background:var(--teald);color:#fff;padding:12px 20px;
  display:flex;align-items:center;gap:16px}
#bar b{color:var(--yellow)}
#bar .sp{flex:1}
#bar button{background:var(--yellow);color:#111;border:0;border-radius:5px;padding:9px 18px;font-weight:bold;font-size:14px;cursor:pointer}
.wrap{max-width:1100px;margin:22px auto;padding:0 18px 60px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin-bottom:20px}
.row{display:flex;gap:20px;flex-wrap:wrap}
.col{flex:1;min-width:280px}
label{display:block;font-weight:bold;font-size:13px;color:var(--teald);margin:14px 0 5px}
input[type=text],input[type=date],select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:6px;font-size:15px;font-family:inherit}
.hint{font-size:12px;color:var(--grey);margin-top:3px}
h2.sec{margin:0 0 4px;color:var(--teald)}
.langtag{display:inline-block;background:var(--teal);color:#fff;font-size:12px;font-weight:bold;padding:3px 10px;border-radius:4px;margin-bottom:6px}
.rt-toolbar{display:flex;gap:4px;margin:5px 0;flex-wrap:wrap}
.rt-toolbar button{background:#f0f3f2;border:1px solid var(--line);border-radius:4px;padding:5px 10px;font-size:13px;cursor:pointer}
.rt{min-height:170px;border:1px solid var(--line);border-radius:6px;padding:12px;font-size:15px;line-height:1.5;background:#fff}
.rt:focus{outline:2px solid var(--teal);outline-offset:-1px}
.rt img{max-width:100%;height:auto;display:block;margin:8px 0}
.cover-preview{margin-top:8px;max-width:320px;border:1px solid var(--line);border-radius:6px;display:none}
.note{background:#fff8e6;border:1px solid var(--yellow);border-radius:8px;padding:12px 16px;font-size:13px;color:#5a4a00}
</style></head>
<body>
<div id="bar"><span>📰 <b>PT Vale</b> — write a news article</span><span class="sp"></span>
  <span id="status" style="opacity:.85;font-size:13px"></span>
  <button onclick="saveArticle()">Save article ⤓</button></div>
<div class="wrap">
  <div class="note">Fill in both English and Indonesian. Use the <b>B</b> / <i>I</i> / heading / link / image
  buttons above each body box. Add photos with the <b>Image</b> button (they’re embedded here; attach the
  same files in the folder). When done, click <b>Save article</b> and send the downloaded file (plus images)
  back to GDI. Everything is previewed on the dev site and approved before it goes live.</div>

  <div class="card">
    <div class="row">
      <div class="col">
        <label>Publish date</label>
        <input type="date" id="date">
        <div class="hint">Controls sort order (newest first).</div>
      </div>
      <div class="col">
        <label>Category</label>
        <select id="category"></select>
        <div class="hint">Pick the one operational / ESG area this story belongs to.</div>
      </div>
    </div>
    <label>Cover image</label>
    <input type="file" id="cover" accept-hint="image">
    <div class="hint">Optional. The card + article header image. Blank = default placeholder.</div>
    <img id="coverPrev" class="cover-preview">
  </div>

  <div class="card">
    <span class="langtag">ENGLISH</span>
    <label>Title</label><input type="text" id="en_title">
    <label>Subtitle</label><input type="text" id="en_subtitle">
    <label>Body</label>__RT_EN__
  </div>

  <div class="card">
    <span class="langtag">BAHASA INDONESIA</span>
    <label>Judul (Title)</label><input type="text" id="id_title">
    <label>Subjudul (Subtitle)</label><input type="text" id="id_subtitle">
    <label>Isi (Body)</label>__RT_ID__
  </div>
</div>

<script>
const CATEGORIES = __CATEGORIES__;
const PREFILL = __PREFILL__;   // record or null
const imgFiles = {};           // objectURL/dataURL bookkeeping -> filename to attach
let imgSeq = 0;

// populate category dropdown
const sel=document.getElementById('category');
CATEGORIES.forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); });

// rich-text helpers
function rtCmd(id,cmd,val){ document.getElementById(id).focus(); document.execCommand(cmd,false,val||null); }
function rtLink(id){ const u=prompt('Link URL (https://… or /indonesia/…):'); if(u) rtCmd(id,'createLink',u); }
function rtHeading(id){ rtCmd(id,'formatBlock','H2'); }
function rtImage(id){
  const inp=document.createElement('input'); inp.type='file';
  inp.onchange=()=>{ const f=inp.files[0]; if(!f) return;
    if(!/\.(jpe?g|png|webp|gif)$/i.test(f.name)){ alert('Please choose an image file.'); return; }
    const rd=new FileReader(); rd.onload=()=>{
      // embed preview; mark with the real filename so GDI knows what to attach
      const el=document.getElementById(id); el.focus();
      document.execCommand('insertHTML',false,
        '<img src="'+rd.result+'" data-filename="'+f.name+'">');
      imgFiles[f.name]=true;
    };
    rd.readAsDataURL(f);
  };
  inp.click();
}

// cover preview
document.getElementById('cover').addEventListener('change',function(){
  const f=this.files[0]; const p=document.getElementById('coverPrev');
  if(f){ const rd=new FileReader(); rd.onload=()=>{p.src=rd.result;p.style.display='block';}; rd.readAsDataURL(f); window.__coverName=f.name; }
});

// clean the rich-text HTML into the record body form:
//  - drop the data-url on images, replace with the served path /documents/d/guest/<slug>-<n>-<ext>
//  - keep only <p><strong><em><a><h2><h3><ul><li><img>
function cleanBody(el, slug){
  const clone=el.cloneNode(true);
  const imgs=[...clone.querySelectorAll('img')];
  const attach=[];
  imgs.forEach(im=>{
    const fn=im.getAttribute('data-filename')|| ('image-'+(++imgSeq)+'.jpg');
    const ext=(fn.split('.').pop()||'jpg').toLowerCase();
    const served='/documents/d/guest/'+slug+'-'+(attach.length+1)+'-'+ext;
    const np=document.createElement('p'); const ni=document.createElement('img'); ni.setAttribute('src',served);
    np.appendChild(ni); im.replaceWith(np);
    attach.push(fn);
  });
  return { html: clone.innerHTML, images: attach };
}

function slugify(t){ return (t||'').toLowerCase().normalize('NFKD').replace(/[^\w\s-]/g,'').trim().replace(/[\s_]+/g,'-').replace(/-+/g,'-').slice(0,240); }

function saveArticle(){
  const en_title=document.getElementById('en_title').value.trim();
  const id_title=document.getElementById('id_title').value.trim();
  const date=document.getElementById('date').value.trim();
  const category=document.getElementById('category').value;
  if(!date){ alert('Please set the publish date.'); return; }
  if(!en_title && !id_title){ alert('Please enter at least one title.'); return; }
  const slug = (PREFILL&&PREFILL.slug) ? PREFILL.slug : slugify(en_title||id_title);

  const enBody=cleanBody(document.getElementById('en_body'), slug);
  const idBody=cleanBody(document.getElementById('id_body'), slug);
  const attachAll=[...new Set([...enBody.images, ...idBody.images, ...(window.__coverName?[window.__coverName]:[])])];

  const rec={
    slug, date, category,           // intake will fold baseline tags + validate category
    cover_filename: window.__coverName || "",
    en:{ title:en_title, subtitle:document.getElementById('en_subtitle').value.trim(), body:enBody.html },
    id:{ title:id_title, subtitle:document.getElementById('id_subtitle').value.trim(), body:idBody.html }
  };
  // drop an empty language entirely
  if(!rec.en.title && !rec.en.body) delete rec.en;
  if(!rec.id.title && !rec.id.body) delete rec.id;

  const blob=new Blob([JSON.stringify(rec,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='news-record.json'; a.click();
  alert('Saved news-record.json to Downloads.\n\n'+
    (attachAll.length? ('Also attach these image files in the folder:\n- '+attachAll.join('\n- ')) : 'No images.')+
    '\n\nSend the folder back to GDI.');
}

// pre-fill from an existing article, if provided
(function prefill(){
  if(!PREFILL) { document.getElementById('date').value=""; return; }
  document.getElementById('date').value=PREFILL.date||"";
  // pick the operational category (first allow-listed one on the record)
  const cat=(PREFILL.categories||[]).find(c=>CATEGORIES.includes(c));
  if(cat) document.getElementById('category').value=cat;
  ['en','id'].forEach(l=>{ if(PREFILL[l]){
    document.getElementById(l+'_title').value=PREFILL[l].title||"";
    document.getElementById(l+'_subtitle').value=PREFILL[l].subtitle||"";
    document.getElementById(l+'_body').innerHTML=PREFILL[l].body||"";
  }});
})();
</script>
</body></html>
"""


def _rt(area_id):
    tb = ("<div class=\"rt-toolbar\">"
          f"<button type=button onclick=\"rtCmd('{area_id}','bold')\"><b>B</b></button>"
          f"<button type=button onclick=\"rtCmd('{area_id}','italic')\"><i>I</i></button>"
          f"<button type=button onclick=\"rtHeading('{area_id}')\">Heading</button>"
          f"<button type=button onclick=\"rtCmd('{area_id}','insertUnorderedList')\">• List</button>"
          f"<button type=button onclick=\"rtLink('{area_id}')\">Link</button>"
          f"<button type=button onclick=\"rtImage('{area_id}')\">Image</button>"
          "</div>")
    return tb + f'<div class="rt" id="{area_id}" contenteditable="true"></div>'


def build(prefill):
    page = (PAGE
            .replace("__RT_EN__", _rt("en_body"))
            .replace("__RT_ID__", _rt("id_body"))
            .replace("__CATEGORIES__", json.dumps(CATEGORY_OPTIONS))
            .replace("__PREFILL__", json.dumps(prefill) if prefill else "null"))
    return page


def main():
    argv = sys.argv[1:]
    out = None; frm = None
    if "-o" in argv:
        i = argv.index("-o"); out = argv[i + 1]; del argv[i:i + 2]
    if "--from" in argv:
        i = argv.index("--from"); frm = argv[i + 1]; del argv[i:i + 2]
    if not out:
        print("usage: python3 make-news-editor.py -o new-article.html [--from <existing-slug>]", file=sys.stderr)
        sys.exit(2)
    prefill = _load_prefill(frm)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(prefill))
    print(f"✓ news editor written -> {out}" + (f"  (pre-filled from {frm})" if frm else ""))
    print("  COMMs double-clicks it, fills the fields, clicks Save article → news-record.json")


if __name__ == "__main__":
    main()
