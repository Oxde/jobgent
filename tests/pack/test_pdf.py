import pytest

from stageone.pack.pdf import html_to_pdf

pytestmark = pytest.mark.slow


def test_html_to_pdf_one_page(tmp_path):
    pytest.importorskip("playwright")
    out = tmp_path / "x.pdf"
    try:
        pages = html_to_pdf("<html><body><p>hi</p></body></html>", out)
    except RuntimeError as e:  # chromium not installed on this machine
        pytest.skip(str(e))
    assert pages == 1 and out.stat().st_size > 500


def test_html_to_pdf_counts_pages(tmp_path):
    pytest.importorskip("playwright")
    html = "<html><body>" + "<p style='page-break-after: always'>a</p>" * 2 + "<p>b</p></body></html>"
    try:
        pages = html_to_pdf(html, tmp_path / "y.pdf")
    except RuntimeError as e:
        pytest.skip(str(e))
    assert pages == 3
