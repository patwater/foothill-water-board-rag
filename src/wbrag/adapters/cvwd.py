"""Crescenta Valley Water District (cvwd.com, WordPress + ccsi-agendas-minutes plugin).

Listing: WP REST /wp-json/wp/v2/meetings (id, link, title, category class). Each meeting page
carries a date heading and Agenda / Minutes / Packet tiles linking to PDFs."""
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .dates import parse_date

BASE = "https://www.cvwd.com"
LIST = (BASE + "/wp-json/wp/v2/meetings?per_page=100&orderby=date&order=asc"
        "&_fields=id,link,title,class_list&page={page}")
TILE_TYPE = {"agenda": "agenda", "minutes": "minutes_adopted", "packet": "packet",
             "video": "video_link", "transcript": "transcript"}
REFERENCE_PAGES = [  # non-meeting governance documents linked from page content
    "/about-us/who-we-are/transparency/", "/about-us/governance/strategic-plan/",
    "/about-us/news-information/hazard-mitigation-plan/",
]


def body_from_classes(classes) -> str:
    for c in classes:
        if c.startswith("meeting_category-"):
            return c.removeprefix("meeting_category-").replace("-meeting", "").replace("-", " ").title()
    return "Board"


def parse_meeting(html: str, meta: dict) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one(".wp-block-ccsi-single-meeting")
    if not root:
        return []
    h1 = root.select_one(".ccsi-single-meeting__heading")
    h2 = root.select_one(".ccsi-single-meeting__date")
    title = h1.get_text(" ", strip=True) if h1 else meta.get("title", "")
    date, prec = parse_date(h2.get_text(" ", strip=True)) if h2 else (None, None)
    body = meta["body"]
    low = title.lower()
    mtype = ("special" if "special" in low else "adjourned" if "adjourn" in low else
             "regular" if body.lower() == "board" else "committee")
    items = []
    for a in root.select("a.ccsi-single-meeting__tile"):
        label_el = a.select_one(".ccsi-single-meeting__tile-label")
        label = label_el.get_text(strip=True) if label_el else "Document"
        detail = []
        if "cancel" in low:
            detail.append("meeting marked canceled")
        if label.lower() == "minutes":
            detail.append("posted as 'Minutes'; adoption status not stated on page")
        items.append(dict(
            governing_body="Board of Directors" if body == "Board" else body,
            body_slug=meta["body_slug"], meeting_key=str(meta["id"]), meeting_date=date,
            date_precision=prec, meeting_type=mtype, doc_type=TILE_TYPE.get(label.lower(), "other"),
            title=f"{title} {label}", source_url=urljoin(BASE, a["href"]),
            status_detail="; ".join(detail) or None))
    return items


def enumerate_items(client, limit=None):
    page, seen = 1, 0
    while True:
        r = client.get(LIST.format(page=page))
        if r.status_code == 400:  # past last page
            break
        r.raise_for_status()
        for m in r.json():
            body = body_from_classes(m["class_list"])
            body_slug = "board" if body == "Board" else re.sub(r"[^a-z0-9]+", "-", body.lower()).strip("-")
            meta = dict(id=m["id"], title=re.sub(r"&#8211;|&#038;", "-", m["title"]["rendered"]),
                        body=body, body_slug=body_slug)
            pr = client.get(m["link"])
            if pr.status_code != 200:
                continue
            yield from parse_meeting(pr.text, meta)
            seen += 1
            if limit and seen >= limit:
                return
        if page >= int(r.headers.get("X-WP-TotalPages", page)):
            break
        page += 1
    if not limit:
        for path in REFERENCE_PAGES:
            yield from reference_items(client, BASE + path)


def parse_reference(html: str, url: str):
    soup = BeautifulSoup(html, "lxml")
    main = soup.find("main") or soup
    seen = set()
    for a in main.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href.lower().split("?")[0].endswith(".pdf") and "cvwd.com" in href and href not in seen:
            seen.add(href)
            t = a.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]
            low = t.lower()
            dtp = ("budget" if "budget" in low else "plan" if "plan" in low else
                   "rate_study" if "rate" in low else "other")
            yield dict(governing_body="District Reference", body_slug="district-reference",
                       meeting_key="reference", meeting_date=None, meeting_type=None, doc_type=dtp,
                       title=t, source_url=href, status_detail=f"reference page {url}")


def reference_items(client, url):
    r = client.get(url)
    if r.status_code == 200:
        yield from parse_reference(r.text, url)
