from pathlib import Path
from wbrag.adapters import cvwd, fmwd
from wbrag.adapters.dates import parse_date
from wbrag import state

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf8", errors="ignore")


def test_fmwd_board_page():
    items = list(fmwd.parse_meeting_page(read("fmwd_board_agenda_packet.html"), "/board-agenda-packet"))
    assert len(items) == 18
    assert all(i["source_url"].startswith("https://www.fmwd.com/uploads/files/") for i in items)
    by = {i["title"]: i for i in items}
    assert by["08-04-2026 Board Agenda"]["doc_type"] == "agenda"
    assert by["08-04-2026 Board Agenda"]["meeting_date"] == "2026-08-04"
    assert by["7.27.26 Board Agenda - Adjourned"]["meeting_type"] == "adjourned"
    assert by["October 2026 Packetv2"]["date_precision"] == "month"


def test_fmwd_committee_page():
    items = list(fmwd.parse_meeting_page(read("fmwd_finance_committee.html"), "/finance-committee"))
    assert len(items) == 4 and all(i["governing_body"] == "Finance Committee" for i in items)


def test_cvwd_meeting_tiles():
    meta = dict(id=10497, title="Board Meeting", body="Board", body_slug="board")
    items = cvwd.parse_meeting(read("cvwd_meeting_10497.html"), meta)
    assert [i["doc_type"] for i in items] == ["agenda", "packet"]  # minutes tile is "Not available"
    assert items[0]["meeting_date"] == "2026-11-10"
    assert items[1]["source_url"].endswith("11-10-26-Board-Packet.pdf")


def test_dates():
    assert parse_date("Feb 11, 2026 Earmark") == ("2026-02-11", "day")
    assert parse_date("7.27.26 Board") == ("2026-07-27", "day")
    assert parse_date("Agenda-111026") == ("2026-11-10", "day")
    assert parse_date("October 2026 Packet") == ("2026-10-01", "month")
    assert parse_date("no date here") == (None, None)


def test_canonical_and_doc_id():
    a = state.canonical("https://WWW.FMWD.com/x.pdf?utm_source=a#frag")
    assert a == "https://www.fmwd.com/x.pdf"
    assert state.make_doc_id("fmwd", a) == state.make_doc_id("fmwd", "https://www.fmwd.com/x.pdf")
    assert len(state.make_doc_id("fmwd", a)) == 16
