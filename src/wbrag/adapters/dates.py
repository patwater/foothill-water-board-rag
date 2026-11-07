"""Best-effort meeting date parsing from file names and page text."""
import re
import datetime as dt

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _iso(y, m, d):
    try:
        return dt.date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date(text: str):
    """Returns (iso_date, precision) with precision 'day' | 'month', or (None, None)."""
    t = text.replace("_", " ")
    m = re.search(r"\b([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (20\d\d)\b", t)
    if m and m.group(1)[:3].lower() in MONTHS:
        d = _iso(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        if d:
            return d, "day"
    m = re.search(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d\d|\d\d)(?!\d)", t)
    if m:
        y = int(m.group(3))
        y += 2000 if y < 100 else 0
        d = _iso(y, int(m.group(1)), int(m.group(2)))
        if d:
            return d, "day"
    m = re.search(r"\b(20\d\d)[.\-](\d\d)[.\-](\d\d)\b", t)
    if m:
        d = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            return d, "day"
    m = re.search(r"(?<!\d)(\d\d)(\d\d)(\d\d)(?!\d)", t)  # MMDDYY, e.g. Agenda-111026
    if m:
        d = _iso(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if d:
            return d, "day"
    m = re.search(r"\b([A-Za-z]{3,9})\.?,? (20\d\d)\b", t)
    if m and m.group(1)[:3].lower() in MONTHS:
        return _iso(int(m.group(2)), MONTHS[m.group(1)[:3].lower()], 1), "month"
    return None, None
