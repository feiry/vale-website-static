---
# ── New page request (based on an existing page) ──────────────────────
# Use this when you want a NEW page that looks like an existing one, but with
# your own content. You do NOT edit HTML — GDI sends you an EDITABLE PAGE you
# open in your browser and edit visually (type on the text, click to swap images).
# Drop this file (renamed request.md) into ONE folder in
# SharePoint > Website-Update-Requests > 1-Submitted.
request_type: new-page
mode: from-existing           # from-existing (copy an existing page's layout) | brand-new (describe below)
source_page_url:              # the LIVE page whose layout you want to reuse,
                              #   e.g. https://www.valeindonesia.com/indonesia/dividend.html
new_page_title_en:           # English title (becomes the page heading + URL)
new_page_title_id:           # Indonesian title
---

# ─── How this works (2 steps) ─────────────────────────────────────────
# STEP 1 — You submit THIS request naming the source page (source_page_url).
# STEP 2 — GDI sends back two EDITABLE PAGES (English + Indonesian) — .html files.
#          Double-click one to open it in your browser: you'll see the real page.
#            • Click any highlighted TEXT and type your new wording.
#            • Click any highlighted IMAGE and pick a new file from your computer.
#            • Click "Save changes" at the top → it downloads a small file.
#          Return both downloaded files (plus any new images) in this same folder.
#          GDI builds the new page (correct layout) and deploys it after your approval.
#
# NOTES:
#   • You edit right on top of the real page — no HTML, no code, can't break the layout.
#   • You can change text and swap images, but you can't add/remove whole sections.
#   • If you need a DIFFERENT layout (more/fewer sections), tell GDI — that's a
#     hand-built page, not this quick path.
#
# For a BRAND-NEW page (mode: brand-new) with no existing layout to copy,
# describe what you want below and attach any content/images — GDI will build it.
notes:
