# Sri Hadriana's answers — 2026-09-02 (email 1a061493247270b5)

Unblocks Bucket 3 (remaining 6) and Bucket 4 (News tags).

## Q1 — Sustainability "New Content" pages = HALAMAN BARU (new pages), taxonomy FINAL
- Clone the 6 new-slug pages as NEW pages (biodiversity, keberagaman-kesetaraan-dan-inklusi,
  penutupan-tambang-dan-rehabilitasi, manajemen-air-dan-efluen, pengelolaan-limbah-b3-dan-non-b3,
  pengelolaan-emisi-dan-energi).
- KEEP the existing old-slug clones (keanekaragaman-hayati, keberagaman-kesetaraan-inklusi,
  rehabilitasi-pascatambang, air-dan-limbah-cair, limbah, emisi) as BACKUP — do NOT delete.
- Release/rilis uses the NEW updated URLs from vale.com. No rename, no redirects needed.
- ESG taxonomy is FINAL ("SUDAH FINAL, SILAKAN DILANJUTKAN") — safe to proceed.
- NOTE: 2 of these 6 old-slug pages I ALREADY re-cloned this session (rehabilitasi-pascatambang refreshed;
  keberagaman-kesetaraan-inklusi is close-slug to new). Just clone the 6 NEW slugs alongside.

## Q2 — News tags = TRIM the category chip list (NOT html meta tags)
Current live News page (screenshot) has a bloated chip row:
  All, Australia, Brazil, Business, Canada, China, Global, IGP Morowali, IGP Pomalaa, Indonesia,
  Indonesia ESG, Indonesia news, Innovation, Investors, Japan, Malaysia, Oman, People, Social,
  Sustainability, United Kingdom
→ too many, many are irrelevant global-Vale categories (Australia/Brazil/Canada/China/Japan/Malaysia/Oman/UK).

Sri's two target options:
- OPTION A: Social, Environment, Governance (3 chips only)
- OPTION B (her PREFERRED / "more effective"): All, IGP Morowali, IGP Pomalaa, IGP Sorlim (if any),
  People, Social, Sustainability

This affects the News/all-news page chip filter — likely build-news.py + the all-news.html template.
DECISION NEEDED FROM FEIRY: Option A or B? (Sri leans B). Then implement the filter chips accordingly.

## Status
Both buckets now UNBLOCKED pending: (a) execute Bucket 3 (6 new pages), (b) Feiry picks News tag option A/B.
