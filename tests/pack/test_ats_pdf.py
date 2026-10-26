import pytest

from jobgent.pack.ats_pdf import ats_check_text, keyword_buckets

GOOD = "Test Student\nNumber: +31600000000\ntest@example.com\nHEINEKEN | GenAI Intern  Sep 2025 - Feb 2026\nPython, SQL, Docker"


def test_good_text_layer_passes():
    r = ats_check_text(GOOD, email="test@example.com", phone="+31600000000")
    assert r.ok and r.problems == []


def test_problems_are_named():
    bad = "Test Student\n(cid:12)(cid:13) �\nSep 2025 – Feb 2026"
    r = ats_check_text(bad, email="test@example.com", phone="+31600000000")
    assert not r.ok
    text = " ".join(r.problems)
    assert "email" in text and "phone" in text and "unreadable" in text and "dash" in text


def test_keyword_buckets():
    b = keyword_buckets(pdf_text="Python and SQL in production", profile_text="python sql docker kubernetes-free", keywords=["Python", "SQL", "Docker", "Rust"])
    assert b == {"covered": ["Python", "SQL"], "missing_but_in_profile": ["Docker"], "gap": ["Rust"]}


@pytest.mark.slow
def test_real_pdf_round_trip(tmp_path):
    pytest.importorskip("playwright")
    from jobgent.pack.ats_pdf import pdf_text
    from jobgent.pack.pdf import html_to_pdf

    out = tmp_path / "cv.pdf"
    try:
        html_to_pdf("<html><body><p>test@example.com</p><p>+31600000000</p><p>2024 - 2025</p></body></html>", out)
    except RuntimeError as e:
        pytest.skip(str(e))
    r = ats_check_text(pdf_text(out), email="test@example.com", phone="+31600000000")
    assert r.ok, r.problems
