"""Stage 7: per-page text from downloaded PDFs (spec section 5).

Writes data/text/<agency>/<doc_id>-v<version>.jsonl, one JSON object per page:
  {"page": 1, "text": "...", "method": "text" | "none", "chars": N}
Pages with almost no text layer get method "none" (candidates for OCR). OCR text, when an OCR engine is added, must
use method "ocr" so chunks inherit lower confidence. Text is stored as extracted; whitespace and hyphenation are
normalized only at citation-verification time."""
import json
import pypdfium2 as pdfium
from . import config, state

TEXT = config.ROOT / "data" / "text"
MIN_CHARS = 25  # below this a page counts as having no text layer


def text_path(agency, doc_id, version):
    return TEXT / agency / f"{doc_id}-v{version}.jsonl"


def pages_pdfium(path):
    pdf = pdfium.PdfDocument(str(path), password="")
    out = []
    try:
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            out.append((i + 1, tp.get_text_bounded()))
            tp.close()
            page.close()
    finally:
        pdf.close()
    return out


def pages_pypdf(path):  # fallback for files pdfium rejects
    from pypdf import PdfReader
    r = PdfReader(str(path))
    if r.is_encrypted:
        r.decrypt("")
    out = []
    for i, p in enumerate(r.pages):
        try:
            out.append((i + 1, p.extract_text() or ""))
        except Exception:
            out.append((i + 1, ""))
    return out


def extract_file(path):
    try:
        return pages_pdfium(path)
    except Exception:
        return pages_pypdf(path)


def run(agency, limit=None, force=False):
    db = state.connect()
    rows = db.execute("SELECT doc_id, version, local_path FROM docs WHERE agency=? AND status='ok' "
                      "AND detected_type='pdf' ORDER BY meeting_date, doc_id", (agency,)).fetchall()
    (TEXT / agency).mkdir(parents=True, exist_ok=True)
    summary = {"docs": 0, "skipped": 0, "failed": 0, "pages": 0, "empty_pages": 0, "ocr_pending_docs": 0}
    for r in rows:
        dest = text_path(agency, r["doc_id"], r["version"])
        if dest.exists() and not force:
            summary["skipped"] += 1
            continue
        if limit and summary["docs"] >= limit:
            break
        try:
            pages = extract_file(r["local_path"])
        except Exception as e:
            summary["failed"] += 1
            print(f"extract failed {r['doc_id']}: {e}")
            continue
        empty = 0
        tmp = dest.with_suffix(".part")
        with open(tmp, "w", encoding="utf8") as f:
            for n, t in pages:
                t = t.replace("\r\n", "\n").replace("\r", "\n")
                method = "text" if len(t.strip()) >= MIN_CHARS else "none"
                empty += method == "none"
                f.write(json.dumps({"page": n, "text": t if method == "text" else "", "method": method,
                                    "chars": len(t.strip())}, ensure_ascii=False) + "\n")
        tmp.replace(dest)
        summary["docs"] += 1
        summary["pages"] += len(pages)
        summary["empty_pages"] += empty
        summary["ocr_pending_docs"] += bool(pages) and empty / len(pages) > 0.5
    return summary
