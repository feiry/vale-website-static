---
# ── Document Library request ─────────────────────────────────────────
# Add a PDF (annual report, sustainability report, financial statement,
# presentation, or press release) to the Document Library.
# Drop this file (renamed request.md) plus the PDF into ONE folder in
# SharePoint > Website-Update-Requests > 1-Submitted.
request_type: document
section: Annual Reports          # Pick EXACTLY ONE (copy the text exactly):
                                 #   Annual Reports
                                 #   Sustainability Reports
                                 #   Financial Statements
                                 #   Presentation
                                 #   Press Releases & Announcements
title_en: PT Vale Indonesia Tbk - Annual Report 2026
title_id: PT Vale Indonesia Tbk - Laporan Tahunan 2026
date_published: 2026-01-01       # Publication date, YYYY-MM-DD. Controls sort order within the section.
lang:                            # Leave blank for a bilingual/NA doc. Use `en` or `id` only for
                                 # Press Releases that exist in one language (the EN/BH split).
pdf_file: your-document-2026.pdf # Filename of the PDF you attached (spelled exactly).
---

# ─── Notes for whoever fills this in ──────────────────────────────────
# • The `section` text must match one of the five options above EXACTLY,
#   or the document silently won't appear on the page.
# • Attach the PDF in the same folder, named exactly as pdf_file.
# • title_en / title_id are what show on the download card (English page /
#   Indonesian page). If you only have one, GDI will mirror it.
# • You don't touch JSON or paths — GDI adds the record and rebuilds the
#   Document Library page for you.
