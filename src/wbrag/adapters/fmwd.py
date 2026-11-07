"""Foothill Municipal Water District (fmwd.com, custom CMS). Documents are PDFs under /uploads/files/.

The Board/Committee Archive pages only link to Google Drive folders that require sign-in, so
older records are `gated` and recorded in sources/fmwd.yaml rather than fetched."""
from urllib.parse import urljoin, unquote
from bs4 import BeautifulSoup
from .dates import parse_date

BASE = "https://www.fmwd.com"
MEETING_PAGES = {  # path -> (governing body, default meeting type)
    "/board-agenda-packet": ("Board of Directors", "regular"),
    "/ad-hoc-committee": ("Ad Hoc Committee", "committee"),
    "/engineering-and-om-committee": ("Engineering and O&M Committee", "committee"),
    "/finance-committee": ("Finance Committee", "committee"),
    "/hazard-mitigation-committee": ("Hazard Mitigation Committee", "committee"),
    "/personnel-committee": ("Personnel Committee", "committee"),
    "/water-resources-committee": ("Water Resources Committee", "committee"),
}
REFERENCE_PAGES = ["/finance-management-reports", "/rates-charges", "/compensation", "/administration",
                   "/disclosure", "/hazard-mitigation-plan", "/capital-improvements"]
GATED_ARCHIVES = [
    ("Board Meetings Archive", "https://drive.google.com/drive/folders/0Bw-okLLaGH9BOU5xSWJiNDVibGc"),
    ("Committee Meetings Archive", "https://drive.google.com/drive/folders/0Bw-okLLaGH9BdmM0Vlk0SXhock0"),
]


def classify(name: str, text: str):
    """File name wins; link text (often just 'Packet') is only a fallback."""
    for n in (name.lower(), text.lower()):
        for key, dt in (("minutes", "minutes_adopted"), ("packet", "packet"), ("agenda", "agenda"),
                        ("resolution", "resolution"), ("budget", "budget")):
            if key in n:
                return dt
        if "rate" in n and ("charge" in n or "study" in n):
            return "rate_study"
        if "plan" in n:
            return "plan"
        if "presentation" in n:
            return "presentation"
    return "other"


def doc_links(html: str, page_url: str):
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        if "/uploads/files/" in href and href.lower().endswith(".pdf") and href not in seen:
            seen.add(href)
            yield href, a.get_text(" ", strip=True)


def parse_meeting_page(html: str, path: str):
    body, mtype = MEETING_PAGES[path]
    for href, text in doc_links(html, BASE + path):
        name = unquote(href.rsplit("/", 1)[-1]).removesuffix(".pdf")
        date, prec = parse_date(name)
        low = name.lower()
        mt = "special" if "special" in low else "adjourned" if "adjourn" in low else mtype
        detail = ("date approximated to first of month (from file name)" if prec == "month" else
                  "no date in file name" if not date else None)
        yield dict(governing_body=body, meeting_key=f"{path}:{date or name}", meeting_date=date,
                   date_precision=prec, meeting_type=mt, doc_type=classify(name, text), title=name,
                   source_url=href, status_detail=detail)


def parse_reference_page(html: str, path: str):
    for href, text in doc_links(html, BASE + path):
        name = unquote(href.rsplit("/", 1)[-1]).removesuffix(".pdf")
        yield dict(governing_body="District Reference", body_slug="district-reference",
                   meeting_key="reference", meeting_date=None, meeting_type=None,
                   doc_type=classify(name, text), title=text or name, source_url=href,
                   status_detail=f"reference page {path}")


def enumerate_items(client, limit=None):
    n = 0
    for path in MEETING_PAGES:
        r = client.get(BASE + path)
        if r.status_code != 200:
            continue
        for it in parse_meeting_page(r.text, path):
            yield it
            n += 1
            if limit and n >= limit:
                return
    if not limit:
        for path in REFERENCE_PAGES:
            r = client.get(BASE + path)
            if r.status_code == 200:
                yield from parse_reference_page(r.text, path)
