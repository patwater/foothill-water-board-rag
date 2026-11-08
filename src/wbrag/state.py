"""SQLite crawl state: the source of truth. Manifests are exported from here."""
import hashlib, re, sqlite3
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from . import config

FIELDS = ["doc_id", "version", "agency", "governing_body", "body_slug", "meeting_key", "meeting_id",
          "meeting_date", "date_precision", "meeting_type", "item_number", "parent_doc_id", "doc_type",
          "title", "source_url", "canonical_url", "provenance", "local_path", "content_sha256", "bytes",
          "content_type", "detected_type", "page_count", "http_status", "etag", "last_modified",
          "retrieved_at", "status", "status_detail", "identity_check", "needs_ocr", "duplicate_of",
          "est_bytes", "snapshot_ts", "fetch_url"]

SCHEMA = f"""CREATE TABLE IF NOT EXISTS docs (
  {', '.join(f + (' INTEGER' if f in ('version','bytes','page_count','http_status','needs_ocr','est_bytes') else ' TEXT') for f in FIELDS)},
  PRIMARY KEY (doc_id, version));
CREATE INDEX IF NOT EXISTS ix_status ON docs(agency, status);
CREATE INDEX IF NOT EXISTS ix_sha ON docs(content_sha256);"""

TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_)")


def canonical(url: str) -> str:
    u = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if not TRACKING.match(k)]
    return urlunsplit((u.scheme, u.netloc.lower(), u.path, urlencode(q), ""))


def make_doc_id(agency: str, url: str) -> str:
    return hashlib.sha256((agency + canonical(url)).encode()).hexdigest()[:16]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def connect():
    config.DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH, timeout=120)
    db.execute("PRAGMA journal_mode=WAL")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    have = {r[1] for r in db.execute("PRAGMA table_info(docs)")}
    for f in FIELDS:
        if f not in have:  # forward migration for databases created before a column existed
            db.execute(f"ALTER TABLE docs ADD COLUMN {f} TEXT")
    return db


def upsert_pending(db, agency, item: dict) -> bool:
    """Insert a pending row for a discovered document. Returns True if new."""
    url = item["source_url"]
    did = make_doc_id(agency, url)
    if db.execute("SELECT 1 FROM docs WHERE doc_id=?", (did,)).fetchone():
        return False
    row = {f: None for f in FIELDS}
    row.update(item, doc_id=did, version=1, agency=agency, canonical_url=canonical(url),
               provenance=item.get("provenance", "live"), status="pending",
               body_slug=item.get("body_slug") or slug(item["governing_body"]))
    cols = [f for f in FIELDS if row[f] is not None]
    db.execute(f"INSERT INTO docs ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})", [row[c] for c in cols])
    return True


def assign_meeting_ids(db, agency):
    """meeting_id = <agency>-<body>-<date>[-n]; n separates distinct source meetings on one day."""
    rows = db.execute("SELECT DISTINCT body_slug, meeting_date, meeting_key FROM docs WHERE agency=? "
                      "ORDER BY body_slug, meeting_date, meeting_key", (agency,)).fetchall()
    seen: dict[tuple, list] = {}
    for r in rows:
        seen.setdefault((r["body_slug"], r["meeting_date"]), []).append(r["meeting_key"])
    for (body, date), keys in seen.items():
        for i, k in enumerate(keys):
            d = date or "undated"
            mid = f"{agency}-{body}-{d}" + (f"-{i+1}" if i else "")
            db.execute("UPDATE docs SET meeting_id=? WHERE agency=? AND body_slug=? AND "
                       "meeting_date IS ? AND meeting_key IS ?", (mid, agency, body, date, k))
    db.commit()
