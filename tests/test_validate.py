import pytest
from wbrag import validate


def test_html_saved_as_pdf_is_soft_404(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_text("<!DOCTYPE html><html><body>Not found</body></html>")
    v = validate.validate(p, "https://www.cvwd.com/x.pdf", "cvwd", None)
    assert v["status"] == "invalid" and "soft 404" in v["status_detail"]


def test_empty_and_length_mismatch(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"")
    assert validate.validate(p, "u.pdf", "cvwd", None)["status"] == "invalid"
    p.write_bytes(b"%PDF-1.4 junk")
    assert validate.validate(p, "u.pdf", "cvwd", 999)["status"] == "invalid"


def test_corrupt_pdf(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4\nthis is not a real pdf\n")
    assert validate.validate(p, "u.pdf", "cvwd", None)["status"] == "invalid"


def test_identity():
    assert validate.identity_ok("Crescenta  Valley\nWater District agenda", "cvwd")
    assert not validate.identity_ok("Coachella Valley Water District", "cvwd")
