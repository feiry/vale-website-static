#!/usr/bin/env python3
"""make-doc-editor.py — a visual, browser-based form for adding a Document Library item.

Produces ONE self-contained .html file COMMs double-clicks to open. Instead of the
cryptic document-request.md, they get proper fields: a Section dropdown, Title, a
Publish-date picker, a PDF file picker (captures the filename), and a Language
selector (only relevant for Press Releases). Clicking "Save document" downloads a
`doc-record.json` GDI feeds to `intake-to-doc.py`, which validates it and appends a
full record to site-data/documents.json for build-doc-library.py.

Usage:
    python3 make-doc-editor.py -o new-document.html

Design: the form captures only the fields COMMs actually knows —
    {section, title, date_published, pdf_file, lang}
GDI/intake derives the plumbing (folder id, link, fsPath, sizeBytes, description).
The section list comes from build-doc-library.py so it never drifts.
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("build_doc_library", os.path.join(SCRIPT_DIR, "build-doc-library.py"))
_bd = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_bd)
SECTION_ORDER = _bd.SECTION_ORDER
PRESS_SECTION = _bd.PRESS_SECTION


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Add a document — PT Vale</title>
<style>
:root{--teal:#00795e;--teald:#00533f;--yellow:#F2A900;--grey:#5a5a5a;--line:#dce3e0;}
*{box-sizing:border-box}
body{margin:0;font-family:Calibri,-apple-system,Arial,sans-serif;color:#222;background:#eef2f0;}
#bar{position:sticky;top:0;z-index:10;background:var(--teald);color:#fff;padding:12px 20px;
  display:flex;align-items:center;gap:16px}
#bar b{color:var(--yellow)}
#bar .sp{flex:1}
#bar button{background:var(--yellow);color:#111;border:0;border-radius:5px;padding:9px 18px;font-weight:bold;font-size:14px;cursor:pointer}
.wrap{max-width:820px;margin:22px auto;padding:0 18px 60px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin-bottom:20px}
.row{display:flex;gap:20px;flex-wrap:wrap}
.col{flex:1;min-width:260px}
label{display:block;font-weight:bold;font-size:13px;color:var(--teald);margin:14px 0 5px}
input[type=text],input[type=date],select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:6px;font-size:15px;font-family:inherit}
.hint{font-size:12px;color:var(--grey);margin-top:3px}
.pdfname{margin-top:8px;font-size:13px;color:var(--teald);font-weight:bold;display:none}
.note{background:#fff8e6;border:1px solid var(--yellow);border-radius:8px;padding:12px 16px;font-size:13px;color:#5a4a00;margin-bottom:20px}
#langRow{display:none}
</style></head>
<body>
<div id="bar"><span>📄 <b>PT Vale</b> — add a document</span><span class="sp"></span>
  <button onclick="saveDoc()">Save document ⤓</button></div>
<div class="wrap">
  <div class="note">Pick the section, type the document title, choose the publish date, and select the
  PDF file (then attach that same PDF in the folder). When done, click <b>Save document</b> and send the
  downloaded file plus the PDF back to GDI. Everything is previewed on the dev site and approved before it goes live.</div>

  <div class="card">
    <label>Section</label>
    <select id="section"></select>
    <div class="hint">Which library shelf this document belongs on.</div>

    <label>Document title</label>
    <input type="text" id="title" placeholder="e.g. PT Vale Indonesia Tbk - Annual Report 2026">
    <div class="hint">The title shown on the download card, exactly as it should read.</div>

    <div class="row">
      <div class="col">
        <label>Publish date</label>
        <input type="date" id="date">
        <div class="hint">Controls sort order within the section (newest first).</div>
      </div>
      <div class="col" id="langRow">
        <label>Language of this file</label>
        <select id="lang">
          <option value="EN">English</option>
          <option value="BH">Indonesian</option>
          <option value="BI">Bilingual (one file, both languages)</option>
        </select>
        <div class="hint">Pick "Bilingual" if the single PDF contains both English and Indonesian.</div>
      </div>
    </div>

    <label>PDF file</label>
    <input type="file" id="pdf">
    <div class="pdfname" id="pdfName"></div>
    <div class="hint">Choose the PDF, then attach that same file in the folder (named exactly the same).</div>
  </div>
</div>

<script>
const SECTIONS = __SECTIONS__;
const PRESS = __PRESS__;

const sel=document.getElementById('section');
SECTIONS.forEach(s=>{ const o=document.createElement('option'); o.value=s; o.textContent=s; sel.appendChild(o); });

// show the language selector only for the press-releases section
function syncLang(){ document.getElementById('langRow').style.display = (sel.value===PRESS)?'block':'none'; }
sel.addEventListener('change', syncLang); syncLang();

document.getElementById('pdf').addEventListener('change', function(){
  const f=this.files[0]; const n=document.getElementById('pdfName');
  if(f){ window.__pdfName=f.name; n.textContent='Selected: '+f.name; n.style.display='block';
         if(!/\.pdf$/i.test(f.name)) n.textContent='⚠ Not a .pdf — '+f.name; }
});

function saveDoc(){
  const section=sel.value;
  const title=document.getElementById('title').value.trim();
  const date=document.getElementById('date').value.trim();
  const pdf=window.__pdfName||"";
  if(!title){ alert('Please enter the document title.'); return; }
  if(!date){ alert('Please set the publish date.'); return; }
  if(!pdf){ alert('Please choose the PDF file.'); return; }
  if(!/\.pdf$/i.test(pdf)){ alert('The file must be a .pdf.'); return; }

  const rec={ section, title, date_published:date, pdf_file:pdf,
              lang: (section===PRESS)? document.getElementById('lang').value : null };

  const blob=new Blob([JSON.stringify(rec,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='doc-record.json'; a.click();
  alert('Saved doc-record.json to Downloads.\n\nAlso attach the PDF in the folder:\n- '+pdf+
        '\n\nSend the folder back to GDI.');
}
</script>
</body></html>
"""


def build():
    return (PAGE
            .replace("__SECTIONS__", json.dumps(SECTION_ORDER))
            .replace("__PRESS__", json.dumps(PRESS_SECTION)))


def main():
    argv = sys.argv[1:]
    out = None
    if "-o" in argv:
        i = argv.index("-o"); out = argv[i + 1]; del argv[i:i + 2]
    if not out:
        print("usage: python3 make-doc-editor.py -o new-document.html", file=sys.stderr)
        sys.exit(2)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build())
    print(f"✓ document editor written -> {out}")
    print("  COMMs double-clicks it, fills the fields, clicks Save document → doc-record.json")


if __name__ == "__main__":
    main()
