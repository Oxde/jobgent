"""A4 PDF via Chromium. Returns the page count so callers can enforce one page."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def html_to_pdf(html: str, out: Path) -> int:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
            browser.close()
    except PlaywrightError as e:
        hint = " Run `uv run playwright install chromium`." if "Executable doesn't exist" in str(e) else ""
        raise RuntimeError(f"Chromium failed to render the PDF: {e}.{hint}") from e
    return len(PdfReader(str(out)).pages)
