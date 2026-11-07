"""Export SQLite rows to manifests/<agency>.jsonl (the committed record)."""
import json
from . import config, state

PUBLIC = [f for f in state.FIELDS if f not in ("meeting_key",)]


def export(agency):
    db = state.connect()
    config.MANIFESTS.mkdir(exist_ok=True)
    rows = db.execute("SELECT * FROM docs WHERE agency=? ORDER BY meeting_date, body_slug, doc_id, version", (agency,))
    path = config.MANIFESTS / f"{agency}.jsonl"
    n = 0
    with open(path, "w", encoding="utf8", newline="\n") as f:
        for r in rows:
            d = {k: r[k] for k in PUBLIC}
            d["needs_ocr"] = bool(d["needs_ocr"]) if d["needs_ocr"] is not None else None
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            n += 1
    return path, n
