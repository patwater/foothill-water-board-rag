"""CVWD meeting tiles link to the web developer's staging hosts (cvwd.ccsdesigns.com). For each such
document, HEAD the same path on www.cvwd.com and record whether the official host serves the same bytes
(by Content-Length). Result goes into status_detail; hashes and doc_ids are untouched.

Run: python -m wbrag.mirrorcheck"""
import re
from urllib.parse import urlsplit
from . import state
from .http import Client

STAGING = re.compile(r"^(wp\.)?cvwd\.ccsdesigns\.com$")


def main():
    db, client = state.connect(), Client("cvwd")
    rows = db.execute("SELECT doc_id, version, source_url, bytes, status_detail FROM docs "
                      "WHERE agency='cvwd' AND status IN ('ok','invalid') AND status_detail NOT LIKE '%www.cvwd.com mirror%' "
                      "OR (agency='cvwd' AND status IN ('ok','invalid') AND status_detail IS NULL)").fetchall()
    tally = {"same_size": 0, "different_size": 0, "missing": 0}
    for r in rows:
        u = urlsplit(r["source_url"])
        if not STAGING.match(u.netloc):
            continue
        h = client.head(f"https://www.cvwd.com{u.path}" + (f"?{u.query}" if u.query else ""))
        if h.status_code != 200:
            key, note = "missing", f"www.cvwd.com mirror: HTTP {h.status_code}"
        elif h.headers.get("Content-Length") == str(r["bytes"]):
            key, note = "same_size", "www.cvwd.com mirror: same size"
        else:
            key, note = "different_size", f"www.cvwd.com mirror: size {h.headers.get('Content-Length')} vs {r['bytes']}"
        tally[key] += 1
        detail = "; ".join(x for x in (r["status_detail"], note) if x)
        db.execute("UPDATE docs SET status_detail=? WHERE doc_id=? AND version=?", (detail, r["doc_id"], r["version"]))
        db.commit()
    print(tally)


if __name__ == "__main__":
    main()
