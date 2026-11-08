# water-board-rag

Citation-grounded RAG over the public board records of five Los Angeles area water agencies.
The full pipeline spec is in [`spec.md`](spec.md). This repo currently implements stages 1 to 6
(preflight, discover, smoke test, enumerate, download, verify) for **FMWD** and **CVWD**.
Extraction, chunking, indexing and answering (`extract.py`, `chunk.py`, `index.py`, `answer.py`) are stubs.

## Usage

```
pip install -e .[dev]
python -m wbrag preflight  --agency fmwd
python -m wbrag enumerate  --agency fmwd          # fill SQLite with pending rows + HEAD size estimates
python -m wbrag smoke      --agency fmwd          # newest + oldest meeting of every body
python -m wbrag download   --agency fmwd          # resumable; --limit N, --refresh to revalidate ok rows
python -m wbrag verify     --agency fmwd          # idempotency re-run, report, manifest export
python -m wbrag export     --agency fmwd
pytest
```

`data/` (raw files, `state.sqlite`) and `logs/` are gitignored. Committed: code, `sources/`,
`manifests/*.jsonl`, `reports/`, and small HTML fixtures in `tests/fixtures/`.

## Notes

- Polite crawling: honest User-Agent, one request per second per host, backoff on 429/5xx, robots.txt honored.
- **FMWD robots.txt override:** fmwd.com disallows `/uploads/`, where all of its documents live. The
  repo owner explicitly authorized ignoring that Disallow for FMWD only. See `sources/fmwd.yaml`.
- **CVWD content signals:** cvwd.com sets `ai-train=no`; it does not state `ai-input`. This corpus is
  used for retrieval only, never for training.
- Never bypass logins: FMWD's pre-2026 archive is in Google Drive folders that require sign-in, so it is `gated`.
- **Burbank robots.txt override:** authorized for burbank.granicus.com only (BWP Board, 2012 to 2026 via the archive search). Glendale and Pasadena remain blocked by access controls.
