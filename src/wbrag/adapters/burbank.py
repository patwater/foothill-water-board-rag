"""Burbank Water and Power Board records from the city's Granicus archive (view_id=6).

The archive search (ViewSearchResults.php) lists every archived meeting with its Agenda/Minutes links. The board
appears under two names: "Burbank Water and Power Board ..." (2011 to 2024) and "BWP Board ..." (2019 on), so both
are searched and de-duplicated by clip_id. Viewer URLs 302 to /DocumentViewer.php?file=<id>.pdf."""
import re
from datetime import datetime
from html import unescape

BASE = "https://burbank.granicus.com"
SEARCH = BASE + "/ViewSearchResults.php"
QUERIES = ("BWP", "Water and Power")
NAME_RX = re.compile(r"^(BWP Board|Burbank Water and Power Board)", re.I)
BODY = "BWP Board"


def parse_results(html):
    for row in re.findall(r"<tr onMouseOver.*?</tr>", html, re.S):
        nm = re.search(r'id="([^"]*)" scope="rowgroup"', row)
        dm = re.search(r">(\d\d/\d\d/\d\d)</td>", row)
        if not nm or not dm:
            continue
        name = unescape(nm.group(1)).strip()
        if not NAME_RX.match(name) or re.search(r"cancel", name, re.I):
            continue
        date = datetime.strptime(dm.group(1), "%m/%d/%y").date().isoformat()
        special = "special" in name.lower()
        for viewer, dtype in (("AgendaViewer", "agenda"), ("MinutesViewer", "minutes_adopted")):
            m = re.search(rf"{viewer}\.php\?view_id=6&(?:amp;)?clip_id=(\d+)", row)
            if m:
                yield dict(
                    governing_body=BODY, body_slug="bwp-board", meeting_key=f"bwp:{date}:{name}", meeting_date=date,
                    date_precision="day", meeting_type="special" if special else "regular", doc_type=dtype,
                    title=f"{name} ({dtype})", source_url=f"{BASE}/{viewer}.php?view_id=6&clip_id={m.group(1)}")


def enumerate_items(client, limit=None):
    seen, n = set(), 0
    for q in QUERIES:
        r = client.get(f"{SEARCH}?view_id=6&types[Clip]=on&allwords={q.replace(' ', '+')}")
        r.raise_for_status()
        for item in parse_results(r.text):
            if item["source_url"] in seen:
                continue
            seen.add(item["source_url"])
            yield item
            n += 1
            if limit and n >= limit:
                return
