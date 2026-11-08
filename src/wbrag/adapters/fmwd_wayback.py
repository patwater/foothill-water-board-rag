"""FMWD history recovered from the Internet Archive (Wayback Machine) CDX index.

FMWD's pre-2026 archive is in Google Drive folders that require sign-in (gated, not bypassed). Older files
were however published on fmwd.com itself (/Resources/Documents/..., /uploads/files/...) and captured by the
Wayback Machine. Spec section 1 allows Wayback copies when marked provenance=wayback with the snapshot time.
Rows keep the original fmwd.com URL as source_url and fetch the raw capture (`id_` flavor) from archive.org."""
import re
from urllib.parse import quote, unquote, urlsplit
from .dates import parse_date

CDX = ("https://web.archive.org/cdx/search/cdx?url=fmwd.com&matchType=domain&output=json"
       "&fl=original,timestamp,mimetype,length&collapse=urlkey"
       "&filter=mimetype:application/pdf&filter=statuscode:200")

BODY_RULES = [  # (regex on lowercased path+name, governing body, meeting type)
    (r"engr|engineering|ecm|eocm", "Engineering and O&M Committee", "committee"),
    (r"finance|fcm|/fc/", "Finance Committee", "committee"),
    (r"personnel|pcm|/pc/", "Personnel Committee", "committee"),
    (r"wrc|water resources|wcm", "Water Resources Committee", "committee"),
    (r"hazard|hmpc", "Hazard Mitigation Committee", "committee"),
    (r"ad hoc|earmark", "Ad Hoc Committee", "committee"),
    (r"bdpkt|board.?packet|board.?agenda|bdagenda|board packets|bp_|/board", "Board of Directors", "regular"),
]


def classify(name):
    n = name.lower()
    for key, dt in (("minutes", "minutes_adopted"), ("pkt", "packet"), ("packet", "packet"),
                    ("agenda", "agenda"), ("resolution", "resolution"), ("budget", "budget"),
                    ("uwmp", "plan"), ("plan", "plan"), ("presentation", "presentation")):
        if key in n:
            return dt
    return "other"


def item_from_cdx(original, ts, length, held_paths):
    path = re.sub(r"/{2,}", "/", unquote(urlsplit(original).path))
    low = path.lower()
    if low in held_paths:
        return None
    name = path.rsplit("/", 1)[-1].removesuffix(".pdf").removesuffix(".PDF")
    body = mtype = None
    for rx, b, mt in BODY_RULES:
        if re.search(rx, low):
            body, mtype = b, mt
            break
    dtype = classify(name)
    date, prec = parse_date(name) if body else (None, None)
    if body is None or dtype == "other":
        body, mtype = "District Reference", None
        date, prec = None, None
    if "special" in low and mtype:
        mtype = "special"
    detail = f"Wayback capture {ts}; original http(s)://fmwd.com{path}"
    if prec == "month":
        detail += "; date approximated to first of month"
    return dict(
        governing_body=body, body_slug=None if body != "District Reference" else "district-reference",
        meeting_key=f"wb:{body}:{date or name}", meeting_date=date, date_precision=prec, meeting_type=mtype,
        doc_type=dtype, title=name, source_url="https://www.fmwd.com" + quote(path),
        fetch_url=f"https://web.archive.org/web/{ts}id_/" + original.replace(" ", "%20"),
        provenance="wayback", snapshot_ts=ts, est_bytes=int(length) if length and length.isdigit() else None,
        status_detail=detail)


def parse_cdx(rows, held_paths):
    best = {}
    for original, ts, _mime, length in rows:
        path = re.sub(r"/{2,}", "/", unquote(urlsplit(original).path)).lower()
        if path not in best or ts > best[path][1]:  # latest capture wins; case/port variants collapse
            best[path] = (original, ts, length)
    for original, ts, length in best.values():
        it = item_from_cdx(original, ts, length, held_paths)
        if it:
            yield it


def enumerate_items(client, limit=None, held_paths=frozenset()):
    r = client.get(CDX)
    r.raise_for_status()
    rows = r.json()[1:]
    for n, it in enumerate(parse_cdx(rows, held_paths), 1):
        yield it
        if limit and n >= limit:
            return
