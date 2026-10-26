from pathlib import Path

import httpx
import pytest
import respx

from jobgent.errors import SourceError
from jobgent.sources.linkedin_guest import SEARCH_URL, LinkedInGuestSource

FIX = Path(__file__).parent.parent / "fixtures" / "linkedin"
PAGE = (FIX / "search_page.html").read_text()
DETAIL = (FIX / "job_detail.html").read_text()


def source(**kw) -> LinkedInGuestSource:
    return LinkedInGuestSource(keywords=["AI intern"], locations=["Amsterdam"], sleep=lambda s: None, **kw)


def test_parses_cards_and_fetches_descriptions():
    with respx.mock as m:
        search = m.get(url__startswith=SEARCH_URL).mock(side_effect=[httpx.Response(200, text=PAGE), httpx.Response(200, text="")])
        m.get(url__regex=r".*/jobs-guest/jobs/api/jobPosting/\d+").mock(return_value=httpx.Response(200, text=DETAIL))
        with httpx.Client() as client:
            jobs = source(max_pages=3).fetch(client)
    assert len(jobs) == 3
    j = jobs[0]
    assert j.source == "linkedin" and j.external_id == "4466885587"
    assert j.title == "ML Engineering Intern - LLM Research & Development" and j.company == "Prosus"
    assert j.location == "Amsterdam, North Holland, Netherlands" and j.posted_at is not None
    assert j.url == "https://nl.linkedin.com/jobs/view/ml-engineering-intern-llm-research-development-at-prosus-4466885587"
    assert len(j.description) > 200
    first = search.calls[0].request.url
    assert first.params["location"] == "Amsterdam, North Holland, Netherlands" and first.params["start"] == "0"
    assert len(search.calls) == 1  # a short page is the last page


def test_full_pages_continue_to_the_next_page():
    import re

    cards = re.findall(r"<li.*?</li>", PAGE, re.S)
    full = "".join(cards[i % 3].replace(re.search(r"jobPosting:(\d+)", cards[i % 3]).group(1), str(1000 + i)) for i in range(10))
    with respx.mock as m:
        search = m.get(url__startswith=SEARCH_URL).mock(side_effect=[httpx.Response(200, text=full), httpx.Response(200, text=PAGE)])
        with httpx.Client() as client:
            jobs = LinkedInGuestSource(keywords=["AI intern"], locations=["Amsterdam"], sleep=lambda s: None, fetch_details=False).fetch(client)
    assert [c.request.url.params["start"] for c in search.calls] == ["0", "10"] and len(jobs) == 13


def test_backs_off_on_429_then_succeeds():
    waits: list[float] = []
    src = LinkedInGuestSource(keywords=["AI intern"], locations=["Amsterdam"], sleep=waits.append, max_pages=1, fetch_details=False)
    with respx.mock as m:
        m.get(url__startswith=SEARCH_URL).mock(side_effect=[httpx.Response(429), httpx.Response(429), httpx.Response(200, text=PAGE)])
        with httpx.Client() as client:
            jobs = src.fetch(client)
    assert len(jobs) == 3 and waits[:2] == [0.5, 1.0]


def test_gives_up_with_a_clear_error_after_repeated_429():
    src = LinkedInGuestSource(keywords=["AI intern"], locations=["Amsterdam"], sleep=lambda s: None, max_pages=1)
    with respx.mock as m:
        m.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(429))
        with httpx.Client() as client, pytest.raises(SourceError, match="429"):
            src.fetch(client)


def test_closed_postings_are_skipped():
    closed = DETAIL.replace("<section>", "<section><figcaption>No longer accepting applications</figcaption>", 1)
    with respx.mock as m:
        m.get(url__startswith=SEARCH_URL).mock(side_effect=[httpx.Response(200, text=PAGE), httpx.Response(200, text="")])
        m.get(url__regex=r".*/jobPosting/4466885587").mock(return_value=httpx.Response(200, text=closed))
        m.get(url__regex=r".*/jobPosting/\d+").mock(return_value=httpx.Response(200, text=DETAIL))
        with httpx.Client() as client:
            jobs = source().fetch(client)
    assert "4466885587" not in [j.external_id for j in jobs] and len(jobs) == 2
