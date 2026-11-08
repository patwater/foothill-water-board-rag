"""Per-file validation (spec section 6). Files are untrusted data: only parsed, never executed."""
import re
import filetype
from pypdf import PdfReader
from . import config

EXPECTED = {"pdf": "pdf", "html": "html", "htm": "html", "txt": "txt", "vtt": "txt", "srt": "txt"}


def detect(head: bytes) -> str:
    k = filetype.guess(head)
    if k:
        return k.extension
    s = head.lstrip()[:512].lower()
    if s.startswith((b"<!doctype html", b"<html", b"<head", b"<body")) or b"<html" in s:
        return "html"
    try:
        head.decode("utf8")
        return "txt"
    except UnicodeDecodeError:
        return "bin"


def _text(page) -> str:
    try:
        return page.extract_text() or ""
    except Exception:  # odd font encodings break extraction, not the file; treated as no text
        return ""


def identity_ok(text: str, agency: str) -> bool:
    t = re.sub(r"\s+", " ", text.lower())
    return any(n in t for n in config.AGENCIES[agency]["identity"])


def validate(path, url: str, agency: str, content_length: int | None) -> dict:
    out = dict(detected_type=None, page_count=None, status="ok", status_detail=None,
               identity_check=None, needs_ocr=0)
    size = path.stat().st_size
    if size == 0:
        return {**out, "status": "invalid", "status_detail": "empty file"}
    if content_length and size != content_length:
        return {**out, "status": "invalid", "status_detail": f"size {size} != Content-Length {content_length}"}
    with open(path, "rb") as f:
        det = detect(f.read(2048))
    out["detected_type"] = det
    ext = url.split("?")[0].rsplit(".", 1)[-1].lower() if "." in url.rsplit("/", 1)[-1] else ""
    exp = EXPECTED.get(ext) or ("pdf" if not ext or "/" in ext else None)  # every adapter collects PDFs; an extensionless URL returning HTML is a dead link
    if exp and det != exp:
        why = "soft 404 / HTML saved as " + ext if det == "html" else f"detected {det}, expected {exp}"
        return {**out, "status": "invalid", "status_detail": why}
    if det == "pdf":
        try:
            r = PdfReader(str(path))
            if r.is_encrypted and not r.decrypt(""):  # owner-password-only PDFs open with an empty password
                return {**out, "status": "invalid", "status_detail": "encrypted PDF (password required)"}
            n = len(r.pages)
            out["page_count"] = n
            idx = sorted({int(i * (n - 1) / 9) for i in range(10)}) if n > 10 else list(range(n))
            texts = {i: _text(r.pages[i]) for i in set(idx) | {0, min(1, n - 1)}}
            sparse = sum(1 for i in idx if len(texts[i].strip()) < 50)
            out["needs_ocr"] = int(sparse > len(idx) / 2)
            head_text = " ".join(texts[i] for i in sorted(texts) if i < 2)
            out["identity_check"] = "pass" if identity_ok(head_text, agency) else (
                "unknown_no_text" if out["needs_ocr"] else "fail")
        except Exception as e:  # corrupt PDF
            return {**out, "status": "invalid", "status_detail": f"PDF error: {type(e).__name__}: {e}"[:200]}
    elif det == "html":
        txt = open(path, encoding="utf8", errors="ignore").read(200_000)
        out["identity_check"] = "pass" if identity_ok(txt, agency) else "fail"
    return out
