"""A4 PDF via Chromium. Returns the page count so callers can enforce one page."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

# When `fit` is on and the page overflows a little, print smaller instead of spilling onto page two.
FIT_SCALES = (0.98, 0.96, 0.94, 0.92, 0.9)


def html_to_pdf(html: str, out: Path, fit: bool = False) -> int:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="load")

            def render(scale: float) -> int:
                page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True, scale=scale)
                return len(PdfReader(str(out)).pages)

            pages = render(1.0)
            if fit and pages == 2:
                for scale in FIT_SCALES:
                    pages = render(scale)
                    if pages == 1:
                        break
                else:
                    pages = render(1.0)
            browser.close()
    except PlaywrightError as e:
        hint = " Run `uv run playwright install chromium`." if "Executable doesn't exist" in str(e) else ""
        raise RuntimeError(f"Chromium failed to render the PDF: {e}.{hint}") from e
    return pages
