"""Stage 8: page- and section-aware chunks with full metadata (spec section 5).

Chunks never cross a page boundary, so every chunk has one exact page for citation (#page=N). Within a page, text is
split into blocks at blank lines and heading lines, then packed up to TARGET tokens. The current section heading
carries across pages of a document. Each chunk gets a `context` prefix (agency, body, date, type, title, section) and the
document's `doc_summary`, which for now is extractive (title plus the start of page 1); an LLM summary can replace it
at index time. Output: data/chunks/<agency>.jsonl."""
import json
import re
import tiktoken
from . import config, state
from .extract import text_path

CHUNKS = config.ROOT / "data" / "chunks"
TARGET, MIN_SPLIT, MAX = 380, 150, 520
ENC = tiktoken.get_encoding("cl100k_base")
HEADING = re.compile(r"^(?:\d{1,2}[.)]\s+[A-Z(]|[A-Z][A-Z0-9 ,&/()\-:.']{12,}$|(?:ATTACHMENT|EXHIBIT|APPENDIX|ARTICLE|SECTION)\b)")
TIER = {"minutes_adopted": 1, "resolution": 1, "ordinance": 1, "staff_report": 2, "attachment": 2, "packet": 2,
        "budget": 2, "plan": 2, "rate_study": 2, "agenda": 3, "amended_agenda": 3, "presentation": 4,
        "minutes_draft": 4, "transcript": 5}


def tier(doc_type, provenance):
    return 5 if provenance == "wayback" else TIER.get(doc_type, 3)


def ntok(s):
    return len(ENC.encode(s, disallowed_special=()))


def blocks(text):
    """Yield (is_heading, text) blocks from one page."""
    cur = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            if cur:
                yield False, " ".join(cur)
                cur = []
        elif HEADING.match(s) and len(s) < 160:
            if cur:
                yield False, " ".join(cur)
                cur = []
            yield True, s
        else:
            cur.append(s)
    if cur:
        yield False, " ".join(cur)


def split_long(s):
    """Split an over-long block on sentence ends, then hard-wrap on words."""
    out, cur = [], ""
    for sent in re.split(r"(?<=[.;:!?])\s+", s):
        if cur and ntok(cur + " " + sent) > MAX:
            out.append(cur)
            cur = ""
        cur = (cur + " " + sent).strip()
        while ntok(cur) > MAX:
            words = cur.split()
            if len(words) < 2:
                break
            half = len(words) // 2
            out.append(" ".join(words[:half]))
            cur = " ".join(words[half:])
    if cur:
        out.append(cur)
    return out


def page_chunks(text, section):
    """Return ([(section, chunk_text)], section_at_end) for one page."""
    res, buf, buf_tok = [], [], 0

    def flush():
        nonlocal buf, buf_tok
        if buf:
            res.append((section, "\n".join(buf)))
        buf, buf_tok = [], 0

    for is_head, b in blocks(text):
        if is_head:
            if buf_tok >= MIN_SPLIT:  # small sections stay together with what follows
                flush()
                section = b[:140]
            elif not buf:
                section = b[:140]
            buf.append(b)
            buf_tok += ntok(b)
            continue
        for piece in (split_long(b) if ntok(b) > MAX else [b]):
            t = ntok(piece)
            if buf and buf_tok + t > TARGET:
                flush()
            buf.append(piece)
            buf_tok += t
    flush()
    return res, section


def doc_summary(title, pages):
    first = next((p["text"] for p in pages if p["text"].strip()), "")
    return f"{title}. " + re.sub(r"\s+", " ", first).strip()[:300]


def run(agency, limit=None):
    db = state.connect()
    rows = db.execute("SELECT * FROM docs WHERE agency=? AND status='ok' AND detected_type='pdf' "
                      "ORDER BY meeting_date, doc_id", (agency,)).fetchall()
    CHUNKS.mkdir(parents=True, exist_ok=True)
    stats = {"docs": 0, "no_text": 0, "chunks": 0, "tokens": 0, "missing_extract": 0}
    tmp = CHUNKS / f"{agency}.jsonl.part"
    with open(tmp, "w", encoding="utf8") as out:
        for r in rows:
            tp = text_path(agency, r["doc_id"], r["version"])
            if not tp.exists():
                stats["missing_extract"] += 1
                continue
            if limit and stats["docs"] >= limit:
                break
            pages = [json.loads(l) for l in open(tp, encoding="utf8")]
            if not any(p["text"].strip() for p in pages):
                stats["no_text"] += 1
                continue
            stats["docs"] += 1
            section = ""
            base = dict(doc_id=r["doc_id"], version=r["version"], agency=agency, governing_body=r["governing_body"],
                        meeting_id=r["meeting_id"], meeting_date=r["meeting_date"], date_precision=r["date_precision"],
                        meeting_type=r["meeting_type"], doc_type=r["doc_type"], title=r["title"],
                        provenance=r["provenance"], authority_tier=tier(r["doc_type"], r["provenance"]),
                        source_url=r["source_url"], doc_summary=doc_summary(r["title"] or "", pages))
            for p in pages:
                if not p["text"].strip():
                    continue
                chunks, section = page_chunks(p["text"], section)
                for k, (sec, txt) in enumerate(chunks, 1):
                    ctx = " | ".join(x for x in (agency.upper(), r["governing_body"], r["meeting_date"],
                                                 r["doc_type"], r["title"], sec) if x)
                    rec = dict(base, chunk_id=f"{r['doc_id']}-v{r['version']}-p{p['page']:04d}-{k}",
                               page=p["page"], section=sec, text=txt, context=ctx, tokens=ntok(txt),
                               ocr=p["method"] == "ocr", confidence="low" if p["method"] == "ocr" else "high",
                               citation_url=f"{r['source_url']}#page={p['page']}")
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    stats["chunks"] += 1
                    stats["tokens"] += rec["tokens"]
    tmp.replace(CHUNKS / f"{agency}.jsonl")
    return stats
