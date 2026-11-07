"""Stages 3-5: smoke test, enumerate (dry run), download."""
import datetime as dt
import hashlib
import os
import shutil
from . import config, state, validate
from .adapters import ADAPTERS
from .http import Client, HostFailing, RobotsBlocked

EXT = {"pdf": "pdf", "html": "html", "txt": "txt"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def enumerate_agency(agency, limit=None, heads=True):
    """Fill SQLite with pending rows; HEAD each new row for a size estimate and dead-link check."""
    db, client = state.connect(), Client(agency)
    new = 0
    for item in ADAPTERS[agency].enumerate_items(client, limit):
        new += state.upsert_pending(db, agency, item)
        if new % 25 == 0:
            db.commit()  # keep write transactions short so a parallel agency run is not blocked
    db.commit()
    state.assign_meeting_ids(db, agency)
    if heads:
        rows = db.execute("SELECT doc_id, source_url FROM docs WHERE agency=? AND version=1 "
                          "AND status='pending' AND est_bytes IS NULL", (agency,)).fetchall()
        for r in rows:
            try:
                h = client.head(r["source_url"])
            except RobotsBlocked:
                db.execute("UPDATE docs SET status='gated', status_detail='blocked by robots.txt' WHERE doc_id=?",
                           (r["doc_id"],))
                continue
            except HostFailing:
                break
            except Exception as e:  # network error on one URL never stops the run
                db.execute("UPDATE docs SET status_detail=? WHERE doc_id=?", (f"HEAD error: {e}"[:200], r["doc_id"]))
                continue
            cl = h.headers.get("Content-Length")
            db.execute("UPDATE docs SET est_bytes=?, http_status=?, etag=?, last_modified=?, content_type=? "
                       "WHERE doc_id=? AND version=1",
                       (int(cl) if cl and cl.isdigit() else None, h.status_code, h.headers.get("ETag"),
                        h.headers.get("Last-Modified"), h.headers.get("Content-Type"), r["doc_id"]))
            db.commit()
    return new


def _target(row, version, ext):
    year = (row["meeting_date"] or "undated")[:4]
    d = config.RAW / row["agency"] / year / (row["meeting_id"] or "unassigned")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{row['doc_id']}-v{version}.{ext}"


def fetch_row(db, client, row, version=None, extra_headers=None):
    """Download one document. Returns 'ok' | 'unchanged' | other status. Commits after the file."""
    version = version or row["version"]
    did, url = row["doc_id"], row["source_url"]
    hdrs = dict(extra_headers or {})
    if row["etag"] and row["status"] == "ok":
        hdrs["If-None-Match"] = row["etag"]
    if row["last_modified"] and row["status"] == "ok":
        hdrs["If-Modified-Since"] = row["last_modified"]

    def upd(**kw):
        sets = ", ".join(f"{k}=?" for k in kw)
        db.execute(f"UPDATE docs SET {sets} WHERE doc_id=? AND version=?", [*kw.values(), did, version])
        db.commit()

    try:
        r = client.get(url, stream=True, headers=hdrs)
    except RobotsBlocked:
        upd(status="gated", status_detail="blocked by robots.txt", retrieved_at=now())
        return "gated"
    except HostFailing:
        raise
    except Exception as e:
        upd(status="failed", status_detail=f"{type(e).__name__}: {e}"[:200], retrieved_at=now())
        return "failed"
    if r.status_code == 304:
        r.close()
        return "unchanged"
    if r.status_code in (401, 403) or "accounts.google.com" in r.url:
        r.close()
        upd(status="gated", http_status=r.status_code, status_detail=f"HTTP {r.status_code} (login/permission)",
            retrieved_at=now())
        return "gated"
    if r.status_code != 200:
        r.close()
        upd(status="failed", http_status=r.status_code, status_detail=f"HTTP {r.status_code}", retrieved_at=now())
        return "failed"
    cl = r.headers.get("Content-Length")
    if cl and cl.isdigit() and int(cl) > config.MAX_FILE_BYTES:
        r.close()
        upd(status="skipped_large", est_bytes=int(cl), http_status=200,
            status_detail=f"{int(cl)} bytes exceeds {config.MAX_FILE_BYTES}", retrieved_at=now())
        return "skipped_large"
    tmp = config.DATA / "tmp" / f"{did}.part"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    n = 0
    try:
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
                h.update(chunk)
                n += len(chunk)
                if n > config.MAX_FILE_BYTES:
                    raise ValueError("file exceeds size cap while streaming")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        upd(status="failed", status_detail=f"stream error: {e}"[:200], retrieved_at=now())
        return "failed"
    finally:
        r.close()
    sha = h.hexdigest()
    v = validate.validate(tmp, url, row["agency"], int(cl) if cl and cl.isdigit() and not r.headers.get("Content-Encoding") else None)
    common = dict(http_status=200, etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"),
                  content_type=r.headers.get("Content-Type"), content_sha256=sha, bytes=n, retrieved_at=now(), **v)
    prev = db.execute("SELECT * FROM docs WHERE doc_id=? AND status IN ('ok','invalid') AND content_sha256 IS NOT NULL "
                      "ORDER BY version DESC LIMIT 1", (did,)).fetchone()
    if prev and prev["content_sha256"] == sha:  # same bytes: nothing new
        tmp.unlink(missing_ok=True)
        return "unchanged"
    if prev and row["status"] in ("ok", "invalid"):  # same doc_id, new bytes: add a version
        version = prev["version"] + 1
        new = dict(row)
        new.update(version=version, status="pending", local_path=None, content_sha256=None)
        cols = [c for c in state.FIELDS if new.get(c) is not None]
        db.execute(f"INSERT INTO docs ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})", [new[c] for c in cols])
    other = db.execute("SELECT doc_id, version, local_path FROM docs WHERE content_sha256=? AND doc_id!=? "
                       "AND local_path IS NOT NULL LIMIT 1", (sha, did)).fetchone()
    if other and v["status"] == "ok":
        tmp.unlink(missing_ok=True)
        upd(**{**common, "status": "duplicate", "duplicate_of": other["doc_id"], "local_path": other["local_path"],
               "status_detail": f"same bytes as {other['doc_id']}"})
        return "duplicate"
    ext = EXT.get(v["detected_type"], "bin")
    dest = _target(row, version, ext)
    os.replace(tmp, dest)  # atomic within the same volume
    upd(**{**common, "local_path": str(dest.relative_to(config.ROOT)).replace("\\", "/")})
    return v["status"]


def download_agency(agency, limit=None, refresh=False, only_ids=None):
    db, client = state.connect(), Client(agency)
    q = "SELECT * FROM docs WHERE agency=? AND "
    q += "status IN ('ok','invalid','duplicate')" if refresh else "status IN ('pending','failed')"
    rows = db.execute(q + " ORDER BY meeting_date DESC, doc_id", (agency,)).fetchall()
    if only_ids is not None:
        rows = [r for r in rows if r["doc_id"] in only_ids]
    if limit:
        rows = rows[:limit]
    counts: dict[str, int] = {}
    for row in rows:
        if refresh:  # cheap revalidation: HEAD first, refetch only if the validators moved
            try:
                h = client.head(row["source_url"])
            except Exception:
                continue
            same = (h.status_code == 200 and h.headers.get("ETag") == row["etag"]
                    and h.headers.get("Content-Length") in (None, str(row["bytes"])))
            if same:
                counts["unchanged"] = counts.get("unchanged", 0) + 1
                continue
        try:
            res = fetch_row(db, client, row)
        except HostFailing as e:
            print("STOP:", e)
            break
        counts[res] = counts.get(res, 0) + 1
    return counts


def smoke(agency):
    """Fetch the newest and oldest dated meeting of every body end to end."""
    db = state.connect()
    ids = set()
    for b in db.execute("SELECT DISTINCT body_slug FROM docs WHERE agency=?", (agency,)).fetchall():
        for order in ("DESC", "ASC"):
            m = db.execute(f"SELECT meeting_id FROM docs WHERE agency=? AND body_slug=? AND meeting_date IS NOT NULL "
                           f"ORDER BY meeting_date {order} LIMIT 1", (agency, b[0])).fetchone()
            if m:
                ids.update(r[0] for r in db.execute("SELECT doc_id FROM docs WHERE meeting_id=?", (m[0],)))
    res = download_agency(agency, only_ids=ids)
    rows = db.execute(f"SELECT body_slug, meeting_date, doc_type, status, identity_check, page_count, bytes, status_detail "
                      f"FROM docs WHERE doc_id IN ({','.join('?'*len(ids))}) ORDER BY body_slug, meeting_date", list(ids)).fetchall()
    return res, [dict(r) for r in rows]
