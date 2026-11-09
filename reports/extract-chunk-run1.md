# Extract and chunk, run 1

Text layer only (pdfium, pypdf fallback). No OCR engine is installed, so scanned pages are recorded as `method: none`.

| Agency | PDFs extracted | Pages | Pages with no text | Docs with no text at all | Chunks | Tokens |
|---|---|---|---|---|---|---|
| burbank | 231 | 16,358 | 1,087 | 20 | 33,778 | 7.27M |
| cvwd | 1,070 | 26,978 | 4,547 | 35 | 42,703 | 10.44M |
| fmwd | 619 | 26,779 | 13,739 | 270 | 21,785 | 5.02M |
| pasadena | 1,742 | 18,092 | 5,202 | 451 | 23,797 | 5.65M |
| **total** | 3,662 | 88,207 | 24,575 | 776 | **122,063** | 28.4M |

Chunks never cross a page, carry the section heading, full metadata, authority tier (spec section 7; Wayback = 5),
`citation_url` with `#page=N`, and an extractive `doc_summary`. Output is `data/chunks/<agency>.jsonl` (gitignored).

## Gaps
- 776 documents (mostly FMWD Wayback scans and older Pasadena files) and about 24.6k pages have no text layer and are
  not searchable until OCR runs. OCR output must be written with `method: "ocr"` so chunks get `confidence: low`.
- `doc_summary` is extractive, not an LLM summary. Replace at index time.
- Duplicate-content rows and failed/invalid rows are excluded.
