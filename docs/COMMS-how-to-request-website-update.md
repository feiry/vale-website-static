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
1. The filled-in template, saved as **`request.md`**
2. **Every image or PDF** you referenced, named exactly as you typed it

Then move the whole folder into `1-Submitted/`.

---

## 1. Publish a news article

1. Copy `_Templates/news-request.md` into your new request folder as `request.md`.
2. Fill it in:
   - **date** — the publish date (`YYYY-MM-DD`).
   - **category** — pick ONE: `IGP Morowali`, `IGP Pomalaa`, `IGP Sorlim`, `People`,
     `Social`, or `Sustainability`.
   - **cover_image** — the filename of the cover photo you attached (or leave blank).
   - **EN** and **ID** sections — title, subtitle, and body in each language.
3. Writing the body — just write normally. You can use:
   - `**bold**`, `*italic*`
   - `[link text](https://…)` for links
   - `##` for a subheading
   - lines starting with `- ` for bullet points
   - `[IMG: photo1.jpg]` on its own line to place a photo (and attach `photo1.jpg`)
4. Attach the cover and every `[IMG:]` photo in the same folder.
5. Move the folder to `1-Submitted/`.

Both languages are normally required. If an article truly exists in only one language,
delete the entire other `# EN` or `# ID` section.

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

## 4. Request a new page (or refresh one from vale.com)

For a brand-new page, or copying an updated page from the main Vale site.

1. Create a request folder (`…_new-page_…`) with a `request.md` that gives:
   - the **source URL** on vale.com (if it's a refresh/copy), OR
   - the full **content** for a brand-new page (both languages) plus any images.
2. Move the folder to `1-Submitted/`.

New pages and re-clones are hands-on work for GDI — the request just gives them
everything they need to do it.

---

## What happens after you submit

1. GDI picks up your folder and moves it to `2-In-Progress/`.
2. GDI builds it and puts it on the **preview (dev) site** first.
3. GDI shares the preview link. **A COMMs lead checks and approves it.**
4. After approval, GDI publishes it to the live site (**www.valeindonesia.com**).
5. GDI moves your folder to `3-Done-Deployed/` with the live links and date.

## How long it takes (typical)

| Request type            | Turnaround (once GDI starts) |
|-------------------------|------------------------------|
| News article            | 1–2 business days            |
| Document                | 1–2 business days            |
| Existing-page edit      | 2–3 business days            |
| New page / re-clone     | Scheduled (larger effort)    |

*(Confirm the exact turnaround with GDI — these are guidelines.)*

## Tips to avoid delays

- Attach **every** image/PDF you reference, named **exactly** as in the template.
- Fill in **both languages** unless the content genuinely exists in only one.
- For a document, copy the **section** name exactly — a typo means it won't appear.
- Put the request in its **own folder**; don't mix two requests together.
