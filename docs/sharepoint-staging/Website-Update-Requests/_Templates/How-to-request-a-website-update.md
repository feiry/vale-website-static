# How to Request a Website Update

This guide is for the **COMMs team**. It explains how to get content published to
**www.valeindonesia.com** — news articles, documents, page edits, and new pages.

**You author the content; GDI reviews and publishes it.** You never need Azure access
or any technical tools. You fill in a template, drop it in a folder, and GDI does the rest.

---

## Where everything lives

Everything goes through one SharePoint area:

```
Website-Update-Requests/
├── _Templates/          ← blank templates + this guide. Copy from here.
├── 1-Submitted/         ← put your finished request folder here
├── 2-In-Progress/       ← GDI moves it here while working on it
└── 3-Done-Deployed/     ← GDI moves it here once it's live (with the live links)
```

You only ever touch **`1-Submitted/`**. The folder your request sits in tells you its status.

---

## The one rule for every request

**One request = one folder.** Name the folder like this:

```
YYYY-MM-DD_<type>_<short-name>/
```

- `type` is one of `news`, `document`, `page-edit`, or `new-page`
- example: `2026-09-10_news_pkb-negotiation/`

Inside that folder put:
1. Your filled-in request — either the saved **`news-record.json`** (news, from the
   visual form), a saved **`.json`** from the page editor (new-page), or a filled
   **`request.md`** template (documents, page-edits)
2. **Every image or PDF** you referenced, named exactly as you attached it

Then move the whole folder into `1-Submitted/`.

---

## 1. Publish a news article

You write news in a **visual form** — no code, no Markdown. GDI sends you an editable
`new-article.html` file; you double-click it to open it in your web browser and fill it in.

1. Ask GDI for the **news article form** (or grab `new-article.html` from `_Templates/`).
   Double-click it — it opens in your browser as a normal fillable form.
2. Fill it in:
   - **Publish date** — pick from the date picker (controls newest-first sort order).
   - **Category** — pick ONE from the dropdown (`IGP Morowali`, `IGP Pomalaa`,
     `IGP Sorlim`, `People`, `Social`, `Sustainability`).
   - **Cover image** — click *Choose File* and pick the cover photo (optional; blank
     = default placeholder). You'll see a preview.
   - **English** and **Bahasa Indonesia** sections — type the Title, Subtitle, and Body
     in each language.
3. Writing the body — just type. Use the buttons above the body box:
   - **B** / **I** for bold / italic
   - **Heading** for a subheading
   - **• List** for bullet points
   - **Link** to add a link
   - **Image** to place a photo inline (it appears right in the box as you go)
4. When done, click **"Save article ↓"** at the top — it downloads a small
   `news-record.json` file.
5. Put that downloaded file **plus every image you used** (cover + any inline photos,
   named exactly as you attached them) into one request folder, and move it to
   `1-Submitted/`.

Both languages are normally required. If an article truly exists in only one language,
leave the other language's fields blank.

> **Editing an existing article as a starting point?** Ask GDI to send you the form
> *pre-filled from that article* — it opens with the current text and images already in
> place, so you just tweak what changed.

## 2. Add a document (report / statement / presentation / press release)

1. Copy `_Templates/document-request.md` into your request folder as `request.md`.
2. Fill it in:
   - **section** — copy ONE of these exactly:
     `Annual Reports`, `Sustainability Reports`, `Financial Statements`,
     `Presentation`, `Press Releases & Announcements`.
   - **title_en / title_id** — the title shown on the download card in each language.
   - **date_published** — publication date (`YYYY-MM-DD`).
   - **pdf_file** — the filename of the PDF you attached.
3. Attach the PDF in the same folder.
4. Move the folder to `1-Submitted/`.

## 3. Edit an existing page

For changing text, stats, photos, or contact details on a page that already exists.

1. Create a request folder (`…_page-edit_…`) with a `request.md` describing:
   - the **page URL** (both English and Indonesian if it applies),
   - a **screenshot** with the part to change marked,
   - **what to change** — the old wording and the new wording, or the photo to swap.
2. Attach any new images.
3. Move the folder to `1-Submitted/`.

## 4. Request a new page

**Easiest — a new page based on an existing one** (recommended when a current page
already has the layout you want):

1. Copy `_Templates/new-page-request.md` into a `…_new-page_…` folder as `request.md`.
2. Fill in the **existing page's URL** (the layout to reuse) and your **new page titles**
   (English + Indonesian). Move the folder to `1-Submitted/`.
3. GDI sends you back **two editable pages** (English + Indonesian) — simple `.html` files.
   **Just double-click one to open it in your web browser.** You'll see the real page, exactly
   as it looks live. Then:
   - **Click any highlighted text** and type your new wording.
   - **Click any highlighted image** and pick a replacement from your computer.
   - When done, click **"Save changes"** at the top — it downloads a small file.
   Return those downloaded files (plus any new images) in the folder. No HTML, no code —
   you're editing right on top of the real page.
4. GDI builds the new page with the correct layout and deploys it after approval.

**Brand-new page (no existing layout to copy):** create a `…_new-page_…` folder describing
what you want, with the full content (both languages) + any images. This is hands-on work
for GDI — the request gives them everything they need to build it.

---

## What happens after you submit

1. GDI picks up your folder and moves it to `2-In-Progress/`.
2. GDI builds it and puts it on the **preview (dev) site** first.
3. GDI shares the preview link. **The COMMs approver (Maman Ashari Hasan Tjokke) checks and approves it.**
4. After approval, GDI publishes it to the live site (**www.valeindonesia.com**).
5. GDI moves your folder to `3-Done-Deployed/` with the live links and date.

## How long it takes (typical)

| Request type            | Turnaround (once GDI starts)        |
|-------------------------|-------------------------------------|
| News article            | 1 business day                      |
| Document                | 1 business day                      |
| Existing-page edit      | 1–2 business days                   |
| New page / re-clone     | Scheduled — agreed case-by-case     |

*Turnaround starts when GDI picks up the request and assumes the approver
(Maman Ashari Hasan Tjokke) signs off promptly on the dev preview. New pages
and re-clones vary in effort, so GDI gives a target date per request.*

## Tips to avoid delays

- Attach **every** image/PDF you reference, named **exactly** as in the template.
- Fill in **both languages** unless the content genuinely exists in only one.
- For a document, copy the **section** name exactly — a typo means it won't appear.
- Put the request in its **own folder**; don't mix two requests together.
