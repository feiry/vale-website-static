# How to Request a Website Update

This guide is for the **COMMs team**. It explains how to get content published to
**www.valeindonesia.com** — news articles, documents, page edits, and new pages.

**You author the content; GDI reviews and publishes it.** You never need Azure access
or any technical tools. You fill in a template, drop it in a folder, and GDI does the rest.

---

## Where everything lives

Everything goes through one shared **`Website-Update-Requests`** folder:

```
Website-Update-Requests/
├── _Templates/          ← blank forms + this guide. Copy from here.
├── 1-Submitted/         ← put your finished request folder here
├── 2-In-Progress/       ← GDI moves it here while working on it
└── 3-Done-Deployed/     ← GDI moves it here once it's live (with the live links)
```

> **This is just a shared working folder** between COMMs and GDI — it lives wherever
> both teams agree (SharePoint, OneDrive, or a Teams file library). It is *not* connected
> to the website; it's only the hand-off point for requests. The steps are the same
> wherever it lives.

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
1. Your filled-in request — the saved **`news-record.json`** (news form) or
   **`doc-record.json`** (document form), a saved **`.json`** from the page editor
   (new-page), or a short **`request.md`** note (page-edits)
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

Like news, you use a **visual form** — no code. GDI sends you an editable
`new-document.html`; double-click it to open it in your browser.

1. Ask GDI for the **document form** (or grab `new-document.html` from `_Templates/`).
   Double-click it — it opens in your browser as a normal fillable form.
2. Fill it in:
   - **Section** — pick ONE from the dropdown: `Annual Reports`, `Sustainability Reports`,
     `Financial Statements`, `Quarterly Reports`, `Presentation`,
     `Press Releases & Announcements`.
   - **Document title** — the title shown on the download card, exactly as it should read.
   - **Publish date** — the date picker (sort order within the section).
   - **PDF file** — click *Choose File* and pick the PDF (this captures its exact name).
   - **Language** — *only appears for Press Releases* (English or Indonesian). Every other
     section is bilingual/NA, so you won't see this field.
3. Click **"Save document ↓"** — it downloads a small `doc-record.json`.
4. Put that file **plus the PDF** (named exactly as you selected it) into one request
   folder, and move it to `1-Submitted/`.

## 3. Edit an existing page

For changing text, stats, photos, or contact details on a page that already exists.
You edit the page **visually** — no code — but first you must ask GDI for the editor.

1. **Request the editor first.** Tell GDI which page you want to edit (the **page URL**,
   English and/or Indonesian). GDI generates a visual editor for that exact page and
   places it in **`_Templates/`** (named for the page, e.g. `sustainability-editor.html`).
2. Grab that editor file, **double-click** it — it opens in your browser showing the real,
   styled page. Then:
   - **Click any highlighted text** and type the new wording.
   - **Click any highlighted image** and pick a replacement from your computer.
   - When done, click **"Save changes"** — it downloads a small file named after the page.
3. Put that downloaded file (plus any new images) in a request folder and move it to
   `1-Submitted/`.

> The editor is generated per page and per language. If you're editing both the English
> and Indonesian versions, ask GDI for both editors.

## 4. Request a new page

**Easiest — a new page based on an existing one** (recommended when a current page
already has the layout you want). Like page edits, you **request the editor first**.

1. **Request the editor first.** Tell GDI:
   - the **existing page's URL** (the layout you want to reuse), and
   - your **new page titles** (English + Indonesian).
   GDI generates the visual editor(s) for that layout and places them in **`_Templates/`**
   (English + Indonesian).
2. Grab the editor file(s), **double-click** to open in your browser — you'll see the real
   page, exactly as it looks live. Then:
   - **Click any highlighted text** and type your new wording.
   - **Click any highlighted image** and pick a replacement from your computer.
   - When done, click **"Save changes"** — it downloads a small file.
   Put the downloaded file(s) (plus any new images) in a `…_new-page_…` folder and move it
   to `1-Submitted/`. No HTML, no code — you edit right on top of the real page.
3. GDI builds the new page with the correct layout and deploys it after approval.

**Brand-new page (no existing layout to copy):** create a `…_new-page_…` folder describing
what you want, with the full content (both languages) + any images. This is hands-on work
for GDI — the request gives them everything they need to build it.

---

## What happens after you submit

1. GDI picks up your folder and moves it to `2-In-Progress/`.
2. GDI builds it and puts it on the **preview (dev) site** first.
3. GDI shares the preview link. **You — the person who submitted the request — check and
   approve it on the preview** before it goes live. (The requester is the approver.)
4. After your approval, GDI publishes it to the live site (**www.valeindonesia.com**).
5. GDI moves your folder to `3-Done-Deployed/` with the live links and date.

## How long it takes

**Target: 1 hour for every request type** (news, document, page edit, new page, vacancy) —
measured from when GDI picks up the request to when it's live, assuming you approve the dev
preview promptly.

**After office hours:** requests submitted outside office hours are only guaranteed within
the 1-hour target **if you notify GDI in advance** that an after-hours update is coming.
Without that heads-up, an after-hours request is handled the next business day.

## Tips to avoid delays

- Attach **every** image/PDF you reference, named **exactly** as in the template.
- Fill in **both languages** unless the content genuinely exists in only one.
- For a document, copy the **section** name exactly — a typo means it won't appear.
- Put the request in its **own folder**; don't mix two requests together.
