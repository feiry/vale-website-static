---
# ── New page request (based on an existing page) ──────────────────────
# Use this when you want a NEW page that looks like an existing one, but with
# your own content. You do NOT edit HTML — GDI sends you a simple content file
# extracted from the page you choose; you fill in the text and images.
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
# STEP 2 — GDI sends back two simple content files (content-en.md + content-id.md)
#          extracted from that page. You edit the VALUES only — the text, links,
#          and images — then return them in this same folder. GDI builds the new
#          page (correct layout + chrome) and deploys it after your approval.
#
# RULES for the content files GDI sends you:
#   • Edit the values in place. Do NOT add, remove, or reorder blocks.
#   • To replace an image: attach the file here and put its name in the block's
#     `new:` line. Leave `new:` blank to keep the existing image.
#   • If you need a DIFFERENT layout (more/fewer sections), tell GDI — that's a
#     hand-built page, not this quick path.
#
# For a BRAND-NEW page (mode: brand-new) with no existing layout to copy,
# describe what you want below and attach any content/images — GDI will build it.
notes:
