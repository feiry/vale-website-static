#!/usr/bin/env python3
"""make-vacancy-manager.py — generate the COMMs-facing visual vacancy form.

Reads the current EN career page (and, for cross-checking, the ID page) and emits a
single self-contained `vacancy-manager.html` that a COMMs person DOUBLE-CLICKS
(works on file://, no server). It shows the current vacancy list with Remove
checkboxes and an "Add vacancy" section, and on Save downloads `vacancies.json`
for GDI to feed to intake-to-vacancy.py.

Usage:
  python3 make-vacancy-manager.py [-o vacancy-manager.html]

The generated form is intentionally simple: it never exposes UUIDs or slot markup
(intake-to-vacancy.py owns the font/UUID trick). PDFs are referenced by filename;
COMMs drops the actual PDF into the request folder alongside the saved JSON.
"""

import sys, os, re, json, argparse, html as htmllib
import vacancy_common as vc

EN_PAGE = "site/vale.com/indonesia/career.html"
ID_PAGE = "site/vale.com/in/indonesia/career.html"


def strip_label(label_html):
    """Turn the stored strong label into readable text: unescape, drop leading '> '."""
    t = htmllib.unescape(label_html)
    t = re.sub(r'^\s*>\s*', '', t)
    return t


def current_rows():
    h = open(EN_PAGE, encoding="utf-8", errors="replace").read()
    vacs = vc.scan_vacancies(h)
    sig = vc.type_sequence_sha(h)
    rows = [{"slug": v["slug"], "text": strip_label(v["label"])} for v in vacs]
    return rows, sig


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Vale — Job Vacancy Manager</title>
<style>
 body{{font-family:"Segoe UI",Arial,sans-serif;margin:0;color:#1f1f1f;background:#f4f8f5}}
 header{{background:#0a5c36;color:#fff;padding:16px 24px}}
 header h1{{margin:0;font-size:20px}}
 main{{max-width:900px;margin:24px auto;padding:0 16px}}
 h2{{color:#0a5c36;border-bottom:2px solid #0a5c36;padding-bottom:4px}}
 table{{border-collapse:collapse;width:100%;font-size:14px;background:#fff}}
 th,td{{border:1px solid #cfcfcf;padding:8px 10px;text-align:left}}
 th{{background:#0a5c36;color:#fff}}
 tr.rm{{background:#ffe9e9;text-decoration:line-through;color:#a00}}
 .addrow input{{width:100%;box-sizing:border-box;padding:6px}}
 .addrow td{{vertical-align:top}}
 button{{background:#0a5c36;color:#fff;border:0;border-radius:4px;padding:8px 14px;font-size:14px;cursor:pointer}}
 button.sec{{background:#e6b400;color:#1f1f1f}}
 .bar{{position:sticky;bottom:0;background:#fff;border-top:2px solid #0a5c36;padding:12px 16px;display:flex;gap:10px;justify-content:flex-end}}
 .note{{font-size:12px;color:#555;margin:4px 0 12px}}
</style></head><body>
<header><h1>Job Vacancy Manager — valeindonesia.com/career</h1></header>
<main>
 <h2>1. Current vacancies</h2>
 <p class="note">Tick <b>Remove</b> for any vacancy that has expired.</p>
 <table id="cur"><thead><tr><th style="width:60px">Remove</th><th>Vacancy</th></tr></thead>
 <tbody></tbody></table>

 <h2 style="margin-top:28px">2. Add new vacancies</h2>
 <p class="note">Fill a row per new vacancy. Put the PDF file (named exactly as below)
   in the same folder where you save this form's output. Date picker handles the format.</p>
 <table id="add"><thead><tr>
   <th>Title — English</th><th>Title — Indonesian</th><th style="width:150px">Date</th>
   <th style="width:200px">PDF filename</th></tr></thead><tbody></tbody></table>
 <p><button class="sec" onclick="addRow()">+ Add vacancy</button></p>
</main>
<div class="bar">
 <button class="sec" onclick="location.reload()">Reset</button>
 <button onclick="save()">Save changes (download vacancies.json)</button>
</div>
<script>
const ROWS = {rows_json};
const SIG  = {sig_json};
const tb = document.querySelector('#cur tbody');
ROWS.forEach((r,i)=>{{
  const tr=document.createElement('tr');
  tr.innerHTML='<td style="text-align:center"><input type="checkbox" data-i="'+i+'"></td><td>'+
     r.text.replace(/</g,'&lt;')+'</td>';
  tr.querySelector('input').onchange=e=>tr.classList.toggle('rm',e.target.checked);
  tb.appendChild(tr);
}});
const atb=document.querySelector('#add tbody');
function addRow(){{
  const tr=document.createElement('tr'); tr.className='addrow';
  tr.innerHTML='<td><input class="en" placeholder="National - Role Title"></td>'+
    '<td><input class="id" placeholder="Nasional - Role Title"></td>'+
    '<td><input class="dt" type="date"></td>'+
    '<td><input class="pdf" placeholder="20260909_role.pdf"></td>';
  atb.appendChild(tr);
}}
addRow();
function save(){{
  const remove=[];
  document.querySelectorAll('#cur tbody input:checked').forEach(c=>{{
    remove.push({{match: ROWS[+c.dataset.i].slug}});
  }});
  const add=[];
  document.querySelectorAll('#add tbody tr').forEach(tr=>{{
    const en=tr.querySelector('.en').value.trim();
    const id=tr.querySelector('.id').value.trim();
    const dt=tr.querySelector('.dt').value.trim();
    const pdf=tr.querySelector('.pdf').value.trim();
    if(en||id||dt||pdf){{ add.push({{title_en:en,title_id:id,date:dt,pdf:pdf}}); }}
  }});
  if(!add.length && !remove.length){{ alert('Nothing to add or remove.'); return; }}
  const out={{_meta:{{source_pages:["indonesia/career.html","in/indonesia/career.html"],
    type_sequence_sha:SIG, generated:new Date().toISOString().slice(0,10)}},
    add:add, remove:remove}};
  const blob=new Blob([JSON.stringify(out,null,2)],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='vacancies.json'; a.click();
}}
</script>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="vacancy-manager.html")
    args = ap.parse_args()
    if not os.path.isfile(EN_PAGE):
        print(f"ERROR: {EN_PAGE} not found (run from repo root)", file=sys.stderr)
        sys.exit(1)
    rows, sig = current_rows()
    out = TEMPLATE.format(rows_json=json.dumps(rows), sig_json=json.dumps(sig))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Wrote {args.out} ({len(rows)} current vacancies, sig={sig}).")
    print("Give this file to COMMs to double-click; they Save -> vacancies.json.")


if __name__ == "__main__":
    main()
