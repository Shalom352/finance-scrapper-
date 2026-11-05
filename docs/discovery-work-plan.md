# Information discovery work plan

## Goal

Find more institution-specific financial publications while preserving evidence, source provenance,
period attribution, and human review for uncertain results.

## Work and status

| Priority | Work | Status | Result |
| --- | --- | --- | --- |
| 1 | Improve discovery on verified institution websites | Implemented | Check robots-declared sitemaps and a bounded fallback before the same-host crawl; recognize PDF query URLs, favor requested years, and report per-site outcomes. |
| 2 | Recover information from scanned reports | Implemented, opt-in | Tesseract OCR is page/time bounded; transcripts retain page references; low-confidence values are skipped and all OCR values require visual review. |
| 3 | Add external search as a source of leads | Implemented, disabled by default | Brave results are fetched without redirects and stored as candidates only after a page-name check; a human must confirm official ownership. |
| 4 | Make documents easier to find | Implemented | Global search includes Entity Hub names and document labels, returns linked entity metadata, and resolves institution links for discovered documents. |
| 5 | Make discovery failures diagnosable | Implemented | Coverage reports identify sitemap, page, PDF, size-limit, validation, and robots outcomes per site. |
| 6 | Research development-finance transactions | Existing connectors | The active branch already collects IFC, BOAD, and Proparco official project pages with provenance and review status. |

## Before enabling the new paths

- Apply the additive Alembic migration `0024_document_ocr_transcript` to the Docker database.
- Rebuild the backend image so it includes Tesseract and the French / English language packs.
- Keep `DOCUMENT_OCR_ENABLED=false` until that rebuild is complete; when enabled, OCR results remain unverified.
- Keep `DISCOVERY_SEARCH_PROVIDER=none` unless API credentials and permission to retain search URLs are confirmed.

## Safeguards

- Preserve each source URL, retrieval outcome, and document hash.
- Never infer a reporting year from an upload directory or crawl date.
- A failed fetch or empty search result does not prove that a publication does not exist.
- External search suggests candidate sites; it does not establish official ownership.
- OCR never changes the original PDF and never passes automatic validation.
