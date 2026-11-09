"""Pasadena City Council items related to water and power, from ww2.cityofpasadena.net.

The site has no robots.txt. Each year page (/?year=YYYY) links the meeting agenda pages (<year> Agendas/Mon_DD_YY/
agenda.asp). An agenda page lists numbered items, each followed by "AR n.pdf" staff reports plus attachments. Items
are kept when their heading mentions Water and Power (department tag, strong) or power/electric/water keywords
(weak); the match is recorded in status_detail. City Council minutes are added for meetings that have a match."""
import re
from datetime import datetime
from html import unescape
from urllib.parse import unquote, urljoin

BASE = "https://ww2.cityofpasadena.net"
YEARS = range(1998, 2027)
STRONG = re.compile(r"\((?:Pasadena\s+)?Water\s*(?:and|&|&amp;)\s*Power(?:\s+Dep\w*\.?)?\)|\bPWP\b|water\s*(?:and|&)\s*power", re.I)
WEAK = re.compile(
    r"\b(?:light\s+and\s+power|water\s+(?:rates?|supply|shortage|system|conservation|management|quality|utility|reclamation|recycling|"
    r"rights|storage|treatment|infrastructure|main|reservoir|service|purchase)|urban\s+water|recycled\s+water|"
    r"electric\s+(?:system|rates?|utility|supply|service|infrastructure)|(?:public|renewable|clean)\s+power|"
    r"power\s+(?:plant|supply|purchase|agreement|rates?|contract|authority|project|resources?)|hydroelectric|"
    r"wastewater|utility\s+(?:rates?|users?\s+tax|undergrounding)|undergrounding|MWD|Metropolitan\s+Water|"
    r"Intermountain|Magnolia\s+Power|Glenarm|Azusa\s+Canyon|Arroyo\s+Seco\s+Canyon|Rose\s+Bowl\s+Water|Raymond\s+Basin)\b", re.I)
CONTRACTOR = re.compile(r"\b\w+\s+Electric(?:al)?,?\s+(?:Inc|Corp|Co|LLC)\b", re.I)
DOC_EXT = (".pdf", ".doc", ".docx", ".xls", ".xlsx")
AR_RX = re.compile(r"^(?:.*/)?(AR\s*\d+[A-Za-z]?)\b", re.I)


def meeting_date(href):
    m = re.search(r"/([A-Z][a-z]{2})_(\d{1,2})_(\d{2})/", unquote(href))
    if not m:
        return None
    try:
        return datetime.strptime("_".join(m.groups()), "%b_%d_%y").date().isoformat()
    except ValueError:
        return None


def agenda_pages(year_html):
    hrefs = re.findall(r'href="([^"]*agenda[^"]*\.asp)"', year_html, re.I)
    return list(dict.fromkeys(hrefs))


def minutes_links(year_html):
    out = {}
    for h in re.findall(r'href="([^"]*)"', year_html):
        u = unquote(h)
        m = re.search(r"(?:/|^)(?:CC MINUTES|Minutes[^/]*)/(\d{4})[ ]?(\d\d)[ ]?(\d\d)[^/]*\.pdf$", u, re.I)
        if m and "CDC" not in u and "Successor" not in u and "SA MIN" not in u:
            out.setdefault("-".join(m.groups()), []).append(h)
    return out


def parse_agenda(html, page_url):
    """Yield (item_heading, [(href, label)]) for each item group that has document links."""
    toks = []
    def mark(m):
        toks.append(m.group(1))
        return f" \u27e6{len(toks) - 1}\u27e7 "
    h = re.sub(r"<!\[.*?\]>", "", html, flags=re.S)
    h = re.sub(r'<a\s[^>]*href="([^"]*)"[^>]*>.*?</a>', mark, h, flags=re.S | re.I)
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S | re.I)
    t = unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t)
    groups, last_end, cur = [], 0, None
    for m in re.finditer(r"\u27e6(\d+)\u27e7", t):
        href = toks[int(m.group(1))]
        low = unquote(href).lower()
        if not low.endswith(DOC_EXT) or href.startswith("http") or "disclaimer" in low or "agenda%20disclaimer" in low:
            continue
        am = AR_RX.match(unquote(href))
        key = re.sub(r"\s+", "", am.group(1)).upper() if am else unquote(href)
        if cur and cur["key"] == key:
            cur["links"].append(href)
            cur["end"] = m.end()
            continue
        heading = t[last_end:m.start()]
        cur = dict(key=key, links=[href], heading=heading, end=m.end())
        groups.append(cur)
        last_end = m.end()
    for g in groups:
        hd = re.sub(r"\u27e6\d+\u27e7", " ", g["heading"])
        starts = list(re.finditer(r"(?:^|\s)(\d{1,2})\.\s+(?=[A-Z(])", hd))
        hd = hd[starts[-1].start():] if starts else hd[-600:]
        g["heading"] = re.sub(r"\s+", " ", hd).strip()[:900]
        g["links"] = [urljoin(page_url, l) for l in g["links"]]
    return groups


def classify(url, key):
    n = unquote(url).rsplit("/", 1)[-1].lower()
    if "resolution" in n or "ordinance" in n:
        return "resolution"
    if "attachment" in n or "exhibit" in n:
        return "attachment"
    return "staff_report" if key.startswith("AR") else "other"


def match_kind(heading):
    head = re.sub(r"Recommendation.*", "", heading[:400], flags=re.I)  # title only, not the CEQA boilerplate
    if STRONG.search(head):
        return "strong"
    if WEAK.search(CONTRACTOR.sub("", head)):
        return "weak"
    return None


def items_for_agenda(html, page_url, date, kinds=("strong", "weak")):
    path = unquote(page_url)
    special = "special" in path.lower()
    for g in parse_agenda(html, page_url):
        k = match_kind(g["heading"])
        if k not in kinds:
            continue
        for u in g["links"]:
            fname = unquote(u).rsplit("/", 1)[-1].rsplit(".", 1)[0]
            yield dict(
                governing_body="City Council", body_slug="city-council", meeting_key=f"cc:{date}:{'sp' if special else 'reg'}",
                meeting_date=date, date_precision="day", meeting_type="special" if special else "regular",
                doc_type=classify(u, g["key"]), title=f"{g['key']} {fname}: {g['heading'][:160]}",
                source_url=u, status_detail=f"water/power match={k}; item: {g['heading'][:300]}")


def enumerate_items(client, limit=None, years=YEARS, kinds=("strong", "weak")):
    n = 0
    for y in years:
        r = client.get(f"{BASE}/?year={y}")
        if r.status_code != 200:
            continue
        yh = r.content.decode("utf-8", "replace")
        mins, hit_dates = minutes_links(yh), set()
        for href in agenda_pages(yh):
            url = urljoin(f"{BASE}/", href)
            date = meeting_date(href)
            pr = client.get(url)
            if pr.status_code != 200 or not date:
                continue
            for item in items_for_agenda(pr.content.decode("utf-8", "replace"), url, date, kinds):
                hit_dates.add(date)
                yield item
                n += 1
                if limit and n >= limit:
                    return
        for date in sorted(hit_dates):
            for h in mins.get(date, []):
                yield dict(governing_body="City Council", body_slug="city-council", meeting_key=f"cc:{date}:reg",
                           meeting_date=date, date_precision="day", meeting_type="regular", doc_type="minutes_adopted",
                           title=f"City Council minutes {date}", source_url=urljoin(f"{BASE}/", h),
                           status_detail="minutes for a meeting with water/power items")
                n += 1
