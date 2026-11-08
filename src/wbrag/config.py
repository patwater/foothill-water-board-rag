"""Agency registry and run-wide settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
DB_PATH = DATA / "state.sqlite"
LOGS = ROOT / "logs"
MANIFESTS = ROOT / "manifests"
REPORTS = ROOT / "reports"
SOURCES = ROOT / "sources"

USER_AGENT = "water-board-rag/0.1 (research crawler; https://github.com/patwater/water-board-rag)"
MIN_INTERVAL = 1.0  # seconds between requests per host
TIMEOUT = 30
MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_CONSECUTIVE_ERRORS = 20

AGENCIES = {
    "fmwd": {
        "name": "Foothill Municipal Water District",
        "identity": ["foothill municipal water district", "foothill mwd", "fmwd"],
        "start": "https://www.fmwd.com/board-meetings/",
        "hosts": ["www.fmwd.com"],
        # Patrick explicitly authorized ignoring the robots.txt Disallow on /uploads/ for FMWD
        # (all FMWD documents live there). Recorded in sources/fmwd.yaml and the run report.
        "robots_override_prefixes": ["/uploads/"],
    },
    "cvwd": {
        "name": "Crescenta Valley Water District",
        "identity": ["crescenta valley water district", "cvwd"],
        "start": "https://www.cvwd.com/board-agendas-information",
        "hosts": ["www.cvwd.com"],
        "robots_override_prefixes": [],
    },
    "glendale": {"name": "City of Glendale, Glendale Water & Power", "identity": ["glendale"],
                 "start": "https://www.glendaleca.gov/government/agendas-minutes",
                 "hosts": ["www.glendaleca.gov"], "robots_override_prefixes": []},
    "pasadena": {"name": "City of Pasadena, Pasadena Water and Power", "identity": ["pasadena"],
                 "start": "https://pasadena.granicus.com/ViewPublisher.php?view_id=2",
                 "hosts": ["pasadena.granicus.com"], "robots_override_prefixes": []},
    "burbank": {"name": "City of Burbank, Burbank Water and Power", "identity": ["burbank"],
                "start": "https://burbank.granicus.com/ViewPublisher.php?view_id=6",
                "hosts": ["burbank.granicus.com"], "robots_override_prefixes": ["/"]},  # user-authorized 2026-11-07, burbank.granicus.com only
}
