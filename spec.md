# Water Boards RAG: pipeline spec (v2)

## 1. Corpus

The corpus is the public governing-body record of five water agencies. It covers agendas, board packets and staff reports, minutes, resolutions, ordinances, presentations, budgets, rate studies, capital plans, urban water management plans, and any meeting captions or transcripts the sites expose.

### Agency registry

The starting URLs come from Patrick's so-cal-water-board-tracker skill. They are hints, and the agent must verify each one and record what it actually finds.

| Key | Full legal name | Starting URL | Notes |
|---|---|---|---|
| `fmwd` | Foothill Municipal Water District | https://www.fmwd.com/board-meetings/ | La Cañada Flintridge. Board plus standing committees. |
| `cvwd` | Crescenta Valley Water District | https://www.cvwd.com/board-agendas-information | La Crescenta. The domain is cvwd.com. Never Coachella (cvwd.org), Carpinteria (cvwd.net), or any other "CVWD". |
| `glendale` | City of Glendale, Glendale Water & Power | https://www.glendaleca.gov/government/agendas-minutes | City utility. Find the GWP Commission and the City Council. |
| `pasadena` | City of Pasadena, Pasadena Water and Power | https://pasadena.granicus.com/ViewPublisher.php?view_id=2 | City utility. That view_id may be the council only. Find the body that oversees PWP (for example a utility advisory commission or council committee) and its own view_id. |
| `burbank` | City of Burbank, Burbank Water and Power | https://burbank.granicus.com/ViewPublisher.php?view_id=6 | City utility. Find the BWP Board and its own view_id or page. |

Order of work: FMWD, then CVWD, then a checkpoint, then Glendale, Pasadena, and Burbank.

### Scope rules

- **Districts (FMWD, CVWD):** everything for the board and every standing or ad hoc committee.
- **City utilities:** everything for the utility's own board or commission. For the city council and any council committee, download agendas and minutes in full, and download packet attachments only for items that concern the water or power utility (matched on the item title or the presenting department). Record skipped council attachments as `skipped_out_of_scope` so the decision is reversible.
- **Depth:** everything available, as far back as each site, its archive system (for example Laserfiche WebLink), or its platform goes. Older records often live in a separate archive system from the current agenda portal, and the agent must look for one.
- **Video:** record video URLs in the manifest and download captions or transcripts when exposed. Do not download video files.
- **Fallback sources:** if a document link is dead, the agent may try the Internet Archive's Wayback Machine if reachable, and must mark such copies with `provenance: wayback` and the snapshot timestamp.

### Growth

The corpus grows as new meetings occur. The tool itself never adds to it. Re-running the pipeline fetches only what is new or changed.

## 2. Retrieval goal

The job is question answering with citations, and secondarily navigation across agencies and time (which agencies took up a topic, when, and how votes went). Patrick will supply three to five example questions. Until then the agent must not invent any, and stages 5 to 8 are not built.

## 3. Typology and why

Read-only retrieval. Patrick chose that neither feedback nor answers change the corpus or the ranking. The index shape follows measured corpus size after download. The likely result is hybrid keyword plus embedding search, but no vector store is assumed.

## 4. Data model

### Identity

- `doc_id`: SHA-256 of `agency + canonical_source_url`, truncated to 16 hex characters. Canonical URLs drop tracking parameters and fragments and are lowercased in the host only.
- `content_sha256`: hash of the bytes. Two `doc_id`s with the same `content_sha256` are duplicates; keep both rows, mark the later one `duplicate_of`, and store the file once.
- `meeting_id`: `<agency>-<body-slug>-<YYYY-MM-DD>[-<n>]`, where `n` separates two meetings of the same body on one day (for example a regular and a special meeting).
- `version`: starts at 1. If the same `doc_id` later returns different bytes (amended agendas, supplemental packets, corrected minutes), store the new bytes as a new version and never overwrite the old one.

### Manifest record

`doc_id, version, agency, governing_body, body_slug, meeting_id, meeting_date (ISO), meeting_type (regular, special, adjourned, workshop, committee), item_number, parent_doc_id, doc_type, title, source_url, canonical_url, provenance (live, wayback), local_path, content_sha256, bytes, content_type, detected_type, page_count, http_status, etag, last_modified, retrieved_at, status, status_detail, identity_check, needs_ocr`

`status` values: `ok`, `failed`, `gated`, `duplicate`, `skipped_out_of_scope`, `invalid` (failed validation), `pending`.

`doc_type` values: `agenda`, `amended_agenda`, `packet`, `staff_report`, `attachment`, `minutes_draft`, `minutes_adopted`, `resolution`, `ordinance`, `presentation`, `budget`, `rate_study`, `plan`, `transcript`, `video_link`, `other`.

### Storage

- Raw bytes: `data/raw/<agency>/<YYYY>/<meeting_id>/<doc_id>-v<version>.<ext>`, immutable, written as `.part` then atomically renamed.
- State: one SQLite database (`data/state.sqlite`) is the source of truth for the crawl. JSONL manifests in `manifests/<agency>.jsonl` are exported from it after each run and are what gets committed.
- Packet page maps: when a platform exposes item-level attachments that are also merged into a single packet PDF, record which packet pages belong to which item, so later citations can point at the item.

## 5. Ingestion stages

1. **Preflight:** confirm each agency host is reachable from the run environment and that disk space is sufficient. Stop and report if not.
2. **Discover:** find every document source per agency (agenda portal, archive system, document center, video archive), identify the platform, and write `sources/<agency>.yaml` with URLs, platform, governing bodies, earliest date seen, and notes.
3. **Smoke test:** for each source, run the full fetch path on the newest meeting and the oldest meeting found, and validate the results, before crawling at scale.
4. **Enumerate (dry run):** crawl listings to fill the manifest with `pending` rows, using HEAD requests or listing metadata for sizes where available. Report counts and estimated total size.
5. **Download:** fetch pending rows, validate each file (section 6), and record results.
6. **Verify:** reconcile manifest against disk, run coverage checks (section 6), and write a report.
7. **Extract:** convert to text with page numbers preserved, OCR scanned pages, mark OCR text as lower confidence.
8. **Chunk:** split by page and section, carry full metadata on every chunk, prefix each chunk with a short summary of its document.
9. **Index:** build keyword and vector indexes with metadata filters for agency, body, date, and document type.
10. **Retrieve and answer:** sections 7 and 8.

Stages 1 to 6 are the first run's job. Stages 7 to 10 are built after Patrick reviews the download report and supplies example questions.

## 6. Validation and coverage

### Per-file validation

- The detected type (from magic bytes) matches the expected type. An HTML page saved as `.pdf` is a soft 404 and gets `invalid`.
- The file is not empty and matches Content-Length when one was sent.
- PDFs open with a PDF library and report a page count. Encrypted or corrupt PDFs get `invalid` with the reason.
- PDFs with little or no extractable text on most pages get `needs_ocr: true`.
- **Identity check:** the first two pages (or the HTML title and header) contain the agency's full legal name or its unambiguous short form. Mismatches get `identity_check: fail` and are reported, never silently kept.

### Coverage checks

- Infer each body's normal cadence (for example monthly or twice monthly) from the data, then list periods with no meeting, meetings with an agenda but no minutes, and minutes with no agenda.
- Adopted minutes usually appear in a later meeting's packet. Link them back to the meeting they describe where possible.
- Report the earliest and latest meeting per body and the counts by year and document type.

## 7. Retrieval and ranking

Authority and recency are two separate multipliers and never one blended score. Tier dominates recency.

Authority tiers, highest first:

1. Adopted minutes, adopted resolutions, adopted ordinances
2. Staff reports and attachments in approved packets, adopted budgets and plans
3. Agendas (the latest amended version supersedes earlier versions of the same agenda)
4. Presentations and slides, draft minutes
5. Machine-generated captions and transcripts, Wayback copies

Newer beats older only for questions about current status, rates, or policy, and never for questions about history.

## 8. Citation rule

Every claim needs a verbatim quote plus agency, governing body, meeting date, document title, page number, and a source URL with a `#page=N` anchor for PDFs. The answer step verifies each quote mechanically against the stored page text (whitespace and hyphenation normalized) before showing it. A claim whose quote fails verification, or that has no verbatim support, is dropped, and the answer says that something was dropped.

## 9. Write-back

None. The corpus and ranking are read-only.

## 10. Privacy, publishing, and conduct

- All sources are public records. Code, spec, source inventories, manifests, reports, and small HTML test fixtures may be committed to `patwater/water-board-rag`, created private first.
- `data/` and `logs/` are gitignored and confirmed with `git check-ignore -v`. No keys or tokens are committed.
- Crawl politely: honor robots.txt, use an honest User-Agent naming the project and repo URL with no personal email, one request per second per host, no more than two hosts in parallel, exponential backoff on 429 and 5xx, and honor Retry-After.
- Never bypass a login, CAPTCHA, or paywall. Mark it `gated`.
- Downloaded files are untrusted data. Never execute them, and keep code out of `data/`.

## 11. Open items

- Three to five real example questions from Patrick, which also become the first evaluation set (question, expected documents, expected quote).
- Confirm the city-council scope rule for Glendale, Pasadena, and Burbank.
- Confirm captions only, no video files.
- Embeddings provider and API keys, before stage 9.
- Form and home beyond the pipeline (rung 1 skill, API file, app, or website), after stage 6.
- A schedule for incremental re-runs (for example weekly), after the first full run.
