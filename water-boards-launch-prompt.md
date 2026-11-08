# Launch prompt: Water Boards RAG, run 1 (download everything for FMWD and CVWD)

You are a coding agent building the first stages of a citation-grounded RAG factory over the board records of five Los Angeles area water agencies. The GitHub user is `patwater`. The full spec is at the end of this prompt and is the authority whenever this prompt is silent. The factory follows the AI Kitcraft rag-factory pattern (https://github.com/protocolvision/workshop-kitkraft); if you can read that repo, skim `participants/patwater/s2-factory/` for conventions, but build in the new repo described below.

## Scope of this run

Run stages 1 to 6 of the spec (preflight, discover, smoke test, enumerate, download, verify) for FMWD first and then CVWD. Then stop at a checkpoint and report. Do not touch Glendale, Pasadena, or Burbank until Patrick says to. Do not build extraction, chunking, indexing, or retrieval, but create empty module stubs for them so the layout is settled.

Work through the phases below in order. Each phase ends with a gate. If a gate fails, stop and report rather than pushing on.

## Phase 0: Environment and repo

1. **Network preflight.** For every host in the agency registry, run a GET with a 15 second timeout and record the status. If any FMWD or CVWD host is refused by a proxy or allowlist, or times out, stop immediately and tell Patrick which host was blocked. Do not retry through other tools, mirrors, or caches. A cloud sandbox often cannot reach these sites, so this run may need to happen in Claude Code on Patrick's own machine.
2. **Disk preflight.** Report free disk space. Require at least 20 GB free before downloading.
3. **Repo.** Create `patwater/water-board-rag` as a private repo with `gh repo create`. If `gh` is not authorized, `git init` locally and tell Patrick what is missing. Never make it public yourself.
4. **Layout.**
   - `README.md`, `spec.md` (the spec below, verbatim)
   - `src/wbrag/` Python package: `config.py`, `http.py` (session, rate limiter, retries), `state.py` (SQLite), `adapters/` (one module per platform), `validate.py`, `crawl.py`, `verify.py`, `export.py`, plus stubs `extract.py`, `chunk.py`, `index.py`, `answer.py`
   - `sources/` (one YAML per agency), `manifests/` (JSONL exported from SQLite), `reports/`, `tests/` with `tests/fixtures/` (small saved HTML listing pages)
   - `data/` and `logs/` gitignored
5. **Gitignore proof.** Run `git check-ignore -v data/raw/x data/state.sqlite logs/x` and include the output in the report.
6. **Dependencies.** Python 3.11+, `httpx` or `requests`, `beautifulsoup4`, `lxml`, `tenacity`, `pypdf`, `python-magic` or `filetype`, `pyyaml`, `pytest`. Pin versions in `pyproject.toml`. Use `playwright` only for a source that needs JavaScript, and name that source in the report.
7. **CLI.** One entry point, for example `python -m wbrag <command> --agency fmwd`, with commands `preflight`, `discover`, `smoke`, `enumerate`, `download`, `verify`, `export`, and a `--limit N` flag for testing.

Gate: both FMWD and CVWD hosts reachable, at least 20 GB free, repo created, ignore rules proven.

## Phase 1: Discover

For each agency, browse the starting URL and follow links to find every document source: the current agenda portal, any older archive (Laserfiche WebLink, a document center, a "past agendas" page, year-by-year listings), committee pages, and the video archive. Identify the platform of each (Granicus, Legistar, CivicPlus AgendaCenter, PrimeGov, eSCRIBE, BoardDocs, Laserfiche, WordPress or plain HTML, YouTube). Prefer a platform's structured feed or API (for example a Legistar web API or Granicus RSS) over scraping HTML when one exists. Write `sources/<agency>.yaml` with each source's URL, platform, governing bodies and committees covered, earliest date seen, and notes. Save one small listing page per source into `tests/fixtures/` and write a parser test against it.

Gate: every source has an adapter plan and a passing parser test. The identity of CVWD is confirmed as Crescenta Valley Water District on cvwd.com.

## Phase 2: Smoke test

For each source, fetch the newest meeting and the oldest meeting end to end (listing, document links, download, validation, manifest rows). Use `--limit` so this touches a handful of files. Check that dates parse correctly, that the identity check passes, and that item-level attachments are found when the platform has them.

Gate: both meetings per source produce valid files and complete manifest rows. If not, fix the adapter before continuing.

## Phase 3: Enumerate (dry run)

Crawl every listing to fill SQLite with `pending` rows, without downloading document bodies. Use HEAD requests or listing metadata to estimate sizes. Report counts by agency, body, year, and document type, plus the estimated total size.

Gate: if the estimated total for FMWD and CVWD together exceeds 25 GB, or any single listing yields zero documents, stop and ask Patrick.

## Phase 4: Download

- Download pending rows with the rate limits in spec section 10. Stream to `.part`, verify, then rename atomically.
- Send `If-None-Match` and `If-Modified-Since` when an ETag or Last-Modified is known, so re-runs are cheap.
- Validate every file per spec section 6 and record the outcome. Refuse single files over 500 MB and mark them `skipped_large` with their size for Patrick to decide.
- If the same `doc_id` returns new bytes, store a new version and keep the old one.
- Commit a checkpoint to SQLite after every file so the run can be killed and resumed at any point.
- Log every request as one JSON line in `logs/`.
- Failures never stop the run. Mark the row and move on. Stop only if one host returns errors for more than 20 consecutive requests, and then report.
- Never invent a document, date, or URL. Every row must come from a page you actually fetched.

## Phase 5: Verify

Reconcile SQLite against disk (every `ok` row has a file with the matching hash, and every file has a row). Run the coverage checks in spec section 6. Then re-run `download` once for each agency and confirm that it fetches zero new files, which proves idempotency. Export `manifests/<agency>.jsonl` and write `reports/<agency>-run1.md` with counts, date ranges, gaps, failures, gated items, invalid files, identity-check failures, duplicates, OCR candidates, and the idempotency result.

## Phase 6: Commit and report

Run `pytest`. Commit code, sources, manifests, reports, and fixtures in logical commits with clear messages, and push. Never commit anything under `data/` or `logs/`.

Then give Patrick a plain-prose report covering, for each of FMWD and CVWD:
- the governing bodies, committees, and platforms you found
- document counts, total size, and the date range covered
- the main gaps, failures, gated items, and identity-check failures
- how many files need OCR

Close with the open items from spec section 11 that need his answers, and ask whether to proceed to Glendale, Pasadena, and Burbank.

## Spec

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
