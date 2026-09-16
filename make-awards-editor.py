#!/usr/bin/env python3
"""make-awards-editor.py — a visual, browser-based form for adding Awards / Certifications
to the awards-and-certifications page.

Produces ONE self-contained .html file COMMs double-clicks to open. They add one or more
items; each item is either an **Award** (year + bilingual description + awarding body +
image, optional news link) or a **Certification** (bilingual standard/validity/scope/
issuer + image). Clicking "Save" downloads an `awards-record.json` GDI feeds to
`intake-to-awards.py`, which injects the rows into both the EN and ID pages.

Usage:
    python3 make-awards-editor.py -o new-award.html

The form captures only what COMMs knows; GDI/intake derives the Liferay markup, ids,
and image paths. No dependencies, no build step — it's a static HTML file.
"""

import os
import sys

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Add an award / certification — PT Vale</title>
<style>
:root{--teal:#00795e;--teald:#00533f;--yellow:#F2A900;--grey:#5a5a5a;--line:#dce3e0;}
*{box-sizing:border-box}
body{margin:0;font-family:Calibri,-apple-system,Arial,sans-serif;color:#222;background:#eef2f0;}
#bar{position:sticky;top:0;z-index:10;background:var(--teald);color:#fff;padding:12px 20px;
  display:flex;align-items:center;gap:16px}
#bar b{color:var(--yellow)}
#bar .sp{flex:1}
#bar button{background:var(--yellow);color:#111;border:0;border-radius:5px;padding:9px 18px;font-weight:bold;font-size:14px;cursor:pointer}
.wrap{max-width:900px;margin:22px auto;padding:0 18px 80px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px 22px;margin-bottom:18px;position:relative}
.card h3{margin:0 0 4px;color:var(--teald);font-size:16px}
.card .kill{position:absolute;top:14px;right:16px;background:#fff;border:1px solid var(--line);border-radius:6px;color:#a33;padding:4px 10px;cursor:pointer;font-size:12px}
.row{display:flex;gap:18px;flex-wrap:wrap}
.col{flex:1;min-width:240px}
label{display:block;font-weight:bold;font-size:12px;color:var(--teald);margin:12px 0 4px}
input[type=text],input[type=number],select,textarea{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:6px;font-size:14px;font-family:inherit}
textarea{min-height:64px;resize:vertical}
.hint{font-size:11px;color:var(--grey);margin-top:2px}
.imgname{margin-top:6px;font-size:12px;color:var(--teald);font-weight:bold;display:none}
.note{background:#fff8e6;border:1px solid var(--yellow);border-radius:8px;padding:12px 16px;font-size:13px;color:#5a4a00;margin-bottom:18px}
.langbox{border:1px solid var(--line);border-radius:8px;padding:6px 14px 14px;margin-top:10px;background:#fafcfb}
.langbox .tag{display:inline-block;font-size:11px;font-weight:bold;color:#fff;background:var(--teal);border-radius:4px;padding:2px 8px;margin:10px 0 2px}
.addbtn{background:var(--teal);color:#fff;border:0;border-radius:6px;padding:10px 18px;font-weight:bold;cursor:pointer;font-size:14px}
.typewrap{display:flex;gap:8px;margin:4px 0 6px}
.typewrap label{display:flex;align-items:center;gap:6px;font-weight:normal;color:#222;margin:0;cursor:pointer;border:1px solid var(--line);border-radius:6px;padding:8px 12px}
.only-award,.only-cert{display:none}
</style></head>
<body>
<div id="bar"><span>🏆 <b>PT Vale</b> — add award / certification</span><span class="sp"></span>
  <button onclick="save()">Save ⤓</button></div>
<div class="wrap">
  <div class="note">Add one or more items. For each, choose <b>Award</b> or <b>Certification</b>,
  fill both English and Indonesian, and attach the image (badge/certificate photo). Awards need a
  <b>year</b> (they group by year on the page). When done, click <b>Save</b> — send the downloaded
  file plus every image back to GDI. Everything is previewed on the dev site and approved before it goes live.</div>

  <div id="items"></div>
  <button class="addbtn" onclick="addItem()">+ Add another item</button>
</div>

<template id="tpl">
  <div class="card" data-item>
    <button class="kill" onclick="this.closest('[data-item]').remove()">✕ remove</button>
    <h3>Item</h3>
    <div class="typewrap">
      <label><input type="radio" name="TYPE" value="award" checked> Award</label>
      <label><input type="radio" name="TYPE" value="certification"> Certification</label>
    </div>

    <div class="only-award">
      <label>Year</label>
      <input type="number" class="f-year" placeholder="e.g. 2026" min="1990" max="2099">
      <div class="hint">Which year block this award appears under (newest year shows first).</div>
      <label>Related news link (optional)</label>
      <input type="text" class="f-link" placeholder="/indonesia/w/some-article.html">
      <div class="hint">If the award image should link to a news article on this site. Leave blank if none.</div>
    </div>

    <label>Image (badge / certificate photo)</label>
    <input type="file" class="f-img" accept="image/*">
    <div class="imgname"></div>
    <div class="hint">Attach this same image file in the folder, named exactly the same.</div>

    <div class="langbox">
      <span class="tag">English</span>
      <div class="only-award">
        <label>Award description</label><textarea class="f-en-description" placeholder="e.g. Gold Award — CSR & Community Empowerment (Food Sector), InTechSEA 2026"></textarea>
        <label>Awarding body</label><input type="text" class="f-en-awarding_body" placeholder="e.g. National Research and Innovation Agency (BRIN)">
      </div>
      <div class="only-cert">
        <label>Standard</label><input type="text" class="f-en-standard" placeholder="e.g. ISO 14001 — Environmental Management">
        <label>Validity period</label><input type="text" class="f-en-validity" placeholder="e.g. Jan 1, 2026 – Dec 31, 2029">
        <label>Scope</label><textarea class="f-en-scope" placeholder="e.g. Mining and processing of nickel"></textarea>
        <label>Issuing body</label><input type="text" class="f-en-issuer" placeholder="e.g. Bureau Veritas">
      </div>
    </div>

    <div class="langbox">
      <span class="tag">Bahasa Indonesia</span>
      <div class="only-award">
        <label>Deskripsi penghargaan</label><textarea class="f-id-description" placeholder="mis. Gold Award — CSR & Pemberdayaan Masyarakat (Bidang Pangan), InTechSEA 2026"></textarea>
        <label>Pemberi penghargaan</label><input type="text" class="f-id-awarding_body" placeholder="mis. Badan Riset dan Inovasi Nasional (BRIN)">
      </div>
      <div class="only-cert">
        <label>Standar</label><input type="text" class="f-id-standard" placeholder="mis. ISO 14001 — Manajemen Lingkungan">
        <label>Masa berlaku</label><input type="text" class="f-id-validity" placeholder="mis. 1 Jan 2026 – 31 Des 2029">
        <label>Cakupan</label><textarea class="f-id-scope" placeholder="mis. Penambangan dan pengolahan nikel"></textarea>
        <label>Penerbit</label><input type="text" class="f-id-issuer" placeholder="mis. Bureau Veritas">
      </div>
    </div>
  </div>
</template>

<script>
function wireTypeToggle(card){
  function sync(){
    const t = card.querySelector('input[name="TYPE"]:checked').value;
    card.querySelectorAll('.only-award').forEach(e=>e.style.display = t==='award'?'block':'none');
    card.querySelectorAll('.only-cert').forEach(e=>e.style.display  = t==='certification'?'block':'none');
    card.querySelector('h3').textContent = (t==='award'?'Award':'Certification');
  }
  card.querySelectorAll('input[name="TYPE"]').forEach(r=>r.addEventListener('change',sync));
  sync();
}
function wireImg(card){
  const inp=card.querySelector('.f-img'), lbl=card.querySelector('.imgname');
  inp.addEventListener('change',function(){
    const f=this.files[0];
    if(f){ card.__img=f.name; lbl.textContent='Selected: '+f.name; lbl.style.display='block'; }
  });
}
function addItem(){
  const tpl=document.getElementById('tpl');
  const node=tpl.content.firstElementChild.cloneNode(true);
  // radios must have unique names per card so they don't cross-link
  const uid='t'+Math.floor(performance.now()*1000)+Math.floor(Math.random()*1000);
  node.querySelectorAll('input[name="TYPE"]').forEach(r=>r.name='TYPE_'+uid);
  document.getElementById('items').appendChild(node);
  // re-query the fixed name inside wireTypeToggle via the new name
  wireTypeToggleNamed(node,'TYPE_'+uid);
  wireImg(node);
}
function wireTypeToggleNamed(card,name){
  function sync(){
    const t=card.querySelector('input[name="'+name+'"]:checked').value;
    card.querySelectorAll('.only-award').forEach(e=>e.style.display=t==='award'?'block':'none');
    card.querySelectorAll('.only-cert').forEach(e=>e.style.display=t==='certification'?'block':'none');
    card.querySelector('h3').textContent=(t==='award'?'Award':'Certification');
  }
  card.querySelectorAll('input[name="'+name+'"]').forEach(r=>r.addEventListener('change',sync));
  sync();
}
function val(card,cls){ const e=card.querySelector(cls); return e?e.value.trim():''; }

function save(){
  const cards=[...document.querySelectorAll('[data-item]')];
  if(!cards.length){ alert('Add at least one item.'); return; }
  const items=[];
  for(const c of cards){
    const type=c.querySelector('input[type=radio]:checked').value;
    const en={}, id={};
    if(type==='award'){
      en.description=val(c,'.f-en-description'); en.awarding_body=val(c,'.f-en-awarding_body');
      id.description=val(c,'.f-id-description'); id.awarding_body=val(c,'.f-id-awarding_body');
    } else {
      for(const k of ['standard','validity','scope','issuer']){
        en[k]=val(c,'.f-en-'+k); id[k]=val(c,'.f-id-'+k);
      }
    }
    const it={type, en, id, image: c.__img||''};
    if(type==='award'){
      const y=val(c,'.f-year');
      if(!/^\d{4}$/.test(y)){ alert('Each award needs a 4-digit year.'); return; }
      it.year=y;
      const link=val(c,'.f-link');
      if(link) it.link=link;
    }
    const hasEN=Object.values(en).some(v=>v), hasID=Object.values(id).some(v=>v);
    if(!hasEN && !hasID){ alert('Fill at least one language for every item.'); return; }
    items.push(it);
  }
  const rec={items};
  const blob=new Blob([JSON.stringify(rec,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='awards-record.json'; a.click();
  const imgs=items.map(i=>i.image).filter(Boolean);
  alert('Saved awards-record.json to Downloads.\n\nAlso attach these image files in the folder:\n- '+
        (imgs.join('\n- ')||'(none)')+'\n\nSend the folder back to GDI.');
}

addItem();  // start with one item
</script>
</body></html>
"""


def main():
    argv = sys.argv[1:]
    out = None
    if "-o" in argv:
        i = argv.index("-o"); out = argv[i + 1]; del argv[i:i + 2]
    if not out:
        print("usage: python3 make-awards-editor.py -o new-award.html", file=sys.stderr)
        sys.exit(2)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(PAGE)
    print(f"✓ awards editor written -> {out}")
    print("  COMMs double-clicks it, adds items, clicks Save → awards-record.json")


if __name__ == "__main__":
    main()
