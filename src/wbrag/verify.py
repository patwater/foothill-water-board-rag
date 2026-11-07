"""Stage 6: reconcile SQLite against disk, coverage checks, per-agency run report."""
import collections
import datetime as dt
import hashlib
import statistics
from . import config, state


def reconcile(agency):
    db = state.connect()
    problems = []
    seen_paths = set()
    for r in db.execute("SELECT * FROM docs WHERE agency=? AND status IN ('ok','invalid','duplicate')", (agency,)):
        p = config.ROOT / r["local_path"] if r["local_path"] else None
        if not p or not p.exists():
            problems.append(f"missing file for {r['doc_id']} v{r['version']}")
            continue
        seen_paths.add(p.resolve())
        if r["status"] == "ok" and hashlib.sha256(p.read_bytes()).hexdigest() != r["content_sha256"]:
            problems.append(f"hash mismatch {r['doc_id']} v{r['version']}")
    base = config.RAW / agency
    if base.exists():
        for f in base.rglob("*"):
            if f.is_file() and f.resolve() not in seen_paths:
                problems.append(f"orphan file {f.relative_to(config.ROOT)}")
    return problems


def coverage(agency):
    db = state.connect()
    out = {}
    bodies = db.execute("SELECT DISTINCT body_slug, governing_body FROM docs WHERE agency=? "
                        "AND meeting_date IS NOT NULL", (agency,)).fetchall()
    for b in bodies:
        ms = db.execute("SELECT meeting_id, meeting_date, GROUP_CONCAT(DISTINCT doc_type) t FROM docs WHERE agency=? "
                        "AND body_slug=? AND meeting_date IS NOT NULL GROUP BY meeting_id ORDER BY meeting_date",
                        (agency, b["body_slug"])).fetchall()
        dates = sorted({dt.date.fromisoformat(m["meeting_date"]) for m in ms})
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        med = statistics.median(gaps) if gaps else None
        long_gaps = [(str(dates[i]), str(dates[i + 1]), g) for i, g in enumerate(gaps) if med and g > max(2 * med, 45)]
        types = [set(m["t"].split(",")) for m in ms]
        out[b["governing_body"]] = dict(
            meetings=len(ms), earliest=str(dates[0]), latest=str(dates[-1]), median_gap_days=med,
            long_gaps=long_gaps[:25], n_long_gaps=len(long_gaps),
            agenda_no_minutes=sum(1 for t in types if t & {"agenda", "packet"} and "minutes_adopted" not in t),
            minutes_no_agenda=sum(1 for t in types if "minutes_adopted" in t and not t & {"agenda", "packet"}))
    return out


def report(agency, idempotency=None):
    db = state.connect()
    A = config.AGENCIES[agency]
    q = lambda s, *a: db.execute(s, (agency, *a)).fetchall()
    total = q("SELECT COUNT(*) FROM docs WHERE agency=?")[0][0]
    L = [f"# {A['name']} ({agency}): run 1 report", "",
         f"Generated {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')}", ""]
    L += ["## Totals", f"- Rows in manifest: {total}"]
    for s, n, b in q("SELECT status, COUNT(*), COALESCE(SUM(bytes),0) FROM docs WHERE agency=? GROUP BY status"):
        L.append(f"- `{s}`: {n} rows, {b/1e6:.1f} MB")
    est = q("SELECT COALESCE(SUM(est_bytes),0) FROM docs WHERE agency=?")[0][0]
    L += [f"- Estimated size from HEAD: {est/1e6:.1f} MB", ""]
    L += ["## By year and document type", "", "| year | " + " | ".join(sorted({r[0] for r in q('SELECT doc_type FROM docs WHERE agency=?')})) + " |"]
    types = sorted({r[0] for r in q("SELECT doc_type FROM docs WHERE agency=?")})
    L.append("|---" * (len(types) + 1) + "|")
    by = collections.defaultdict(dict)
    for y, t, n in q("SELECT COALESCE(SUBSTR(meeting_date,1,4),'undated'), doc_type, COUNT(*) FROM docs WHERE agency=? GROUP BY 1,2"):
        by[y][t] = n
    for y in sorted(by):
        L.append(f"| {y} | " + " | ".join(str(by[y].get(t, "")) for t in types) + " |")
    L += ["", "## Governing bodies and coverage"]
    for body, c in coverage(agency).items():
        L.append(f"- **{body}**: {c['meetings']} meetings, {c['earliest']} to {c['latest']}, median gap "
                 f"{c['median_gap_days']} days; {c['n_long_gaps']} unusually long gaps; "
                 f"{c['agenda_no_minutes']} meetings with agenda/packet but no minutes; "
                 f"{c['minutes_no_agenda']} with minutes but no agenda")
        for a, b2, g in c["long_gaps"][:8]:
            L.append(f"    - gap {a} to {b2} ({g} days)")
    def listing(title, sql, fmt, cap=40):
        rows = q(sql)
        L.extend(["", f"## {title} ({len(rows)})"])
        L.extend(fmt(r) for r in rows[:cap])
        if len(rows) > cap:
            L.append(f"- ... and {len(rows)-cap} more (see manifest)")
    listing("Failed", "SELECT source_url, status_detail FROM docs WHERE agency=? AND status='failed'", lambda r: f"- {r[0]}: {r[1]}")
    listing("Gated", "SELECT source_url, status_detail FROM docs WHERE agency=? AND status='gated'", lambda r: f"- {r[0]}: {r[1]}")
    listing("Skipped large", "SELECT source_url, est_bytes FROM docs WHERE agency=? AND status='skipped_large'", lambda r: f"- {r[0]} ({r[1]} bytes)")
    listing("Invalid files", "SELECT source_url, status_detail FROM docs WHERE agency=? AND status='invalid'", lambda r: f"- {r[0]}: {r[1]}")
    listing("Identity-check failures", "SELECT source_url, title FROM docs WHERE agency=? AND identity_check='fail'", lambda r: f"- {r[0]} ({r[1]})")
    listing("Duplicates", "SELECT source_url, duplicate_of FROM docs WHERE agency=? AND status='duplicate'", lambda r: f"- {r[0]} duplicate of {r[1]}")
    listing("Approximate or missing dates", "SELECT source_url, status_detail FROM docs WHERE agency=? AND doc_type IN ('agenda','packet','minutes_adopted') AND (meeting_date IS NULL OR date_precision='month')", lambda r: f"- {r[0]}: {r[1]}")
    n_ocr = q("SELECT COUNT(*) FROM docs WHERE agency=? AND needs_ocr=1")[0][0]
    L += ["", f"## OCR candidates: {n_ocr} files flagged `needs_ocr`", "", "## Reconciliation"]
    probs = reconcile(agency)
    L.append("- SQLite and disk agree" if not probs else f"- {len(probs)} problems")
    L += [f"    - {p}" for p in probs[:20]]
    L += ["", "## Idempotency", f"- {idempotency or 'not run'}", ""]
    path = config.REPORTS / f"{agency}-run1.md"
    config.REPORTS.mkdir(exist_ok=True)
    path.write_text("\n".join(L), encoding="utf8")
    return path
