"""Burbank Water and Power Board records from the city's Granicus publisher (view_id=6).

Granicus RSS (agenda and minutes modes) lists the most recent ~100 items across all city bodies; only the
"BWP Board Meeting" entries are kept. Viewer URLs 302 to /DocumentViewer.php?file=<id>.pdf. Older meetings
need the archive search form, which is not implemented."""
import re
from datetime import datetime
from html import unescape

BASE = "https://burbank.granicus.com"
FEED = BASE + "/ViewPublisherRSS.php?view_id=6&mode={mode}"
BODY = "BWP Board"


def parse_feed(xml, mode):
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title = unescape(re.search(r"<title>(.*?)</title>", it).group(1)).strip()
        if not title.startswith("BWP Board Meeting"):
            continue
        m = re.search(r"-\s*(?:DARK\s*-\s*)?([A-Z][a-z]{2} \d{1,2}, \d{4})$", title)
        if not m:
            continue
        date = datetime.strptime(m.group(1), "%b %d, %Y").date().isoformat()
        clip = re.search(r"clip_id=(\d+)", it).group(1)
        viewer = "AgendaViewer" if mode == "agenda" else "MinutesViewer"
        yield dict(
            governing_body=BODY, body_slug="bwp-board", meeting_key=f"bwp:{date}", meeting_date=date,
            date_precision="day", meeting_type="regular", doc_type="agenda" if mode == "agenda" else "minutes_adopted",
            title=f"{title} ({mode})", source_url=f"{BASE}/{viewer}.php?view_id=6&clip_id={clip}")


def enumerate_items(client, limit=None):
    n = 0
    # the minutes feed rarely lists BWP, so minutes are probed per agenda clip (same clip_id)
    r = client.get(FEED.format(mode="agenda"))
    r.raise_for_status()
    items = list(parse_feed(r.text, "agenda"))
    items += [dict(i, doc_type="minutes_adopted", title=i["title"].replace("(agenda)", "(minutes)"),
                   source_url=i["source_url"].replace("AgendaViewer", "MinutesViewer")) for i in items]
    for mode in (None,):
        for item in items:
            # a meeting without minutes yet redirects to /panes/NoMinutes.php
            final = client.head(item["source_url"]).url
            if "/panes/No" in final:
                continue
            yield item
            n += 1
            if limit and n >= limit:
                return
