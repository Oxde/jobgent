from datetime import datetime

import httpx
import respx

from jobgent.db import Job
from jobgent.liveness import check_liveness
import pytest


@pytest.fixture(autouse=True)
def no_dns(monkeypatch):
    monkeypatch.setattr("jobgent.sources.manual.assert_public_http_url", lambda url: None)


def job(url: str) -> Job:
    return Job(id=1, source="s", external_id="1", url=url, title="AI Intern", company="Acme", location=None,
               description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key="k")


def check(url: str, response: httpx.Response) -> str:
    with respx.mock as m:
        m.get(url).mock(return_value=response)
        with httpx.Client() as client:
            return check_liveness(job(url), client)


def test_open_posting():
    assert check("https://jobs.example.com/1", httpx.Response(200, text="<h1>AI Intern</h1> Apply now")) == "open"


def test_gone_posting():
    assert check("https://jobs.example.com/2", httpx.Response(404)) == "closed"
    assert check("https://jobs.example.com/3", httpx.Response(410)) == "closed"


def test_closed_wording():
    for text in ["No longer accepting applications", "This job is no longer available", "Deze vacature is gesloten", "The position has been filled"]:
        assert check("https://jobs.example.com/4", httpx.Response(200, text=f"<p>{text}</p>")) == "closed", text


def test_server_errors_are_unknown_not_closed():
    assert check("https://jobs.example.com/5", httpx.Response(503)) == "unknown"
    assert check("https://jobs.example.com/6", httpx.Response(429)) == "unknown"


def test_no_url_is_unknown():
    with httpx.Client() as client:
        assert check_liveness(job(""), client) == "unknown"


def test_redirect_to_a_private_address_is_not_followed(monkeypatch):
    from jobgent.errors import SourceError

    def guard(url: str) -> None:
        if "127.0.0.1" in url:
            raise SourceError("manual", "not public")

    monkeypatch.setattr("jobgent.sources.manual.assert_public_http_url", guard)
    with respx.mock as m:
        m.get("https://jobs.example.com/r").mock(return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"}))
        admin = m.get("http://127.0.0.1/admin").mock(return_value=httpx.Response(200, text="open"))
        with httpx.Client() as client:
            assert check_liveness(job("https://jobs.example.com/r"), client) == "unknown"
    assert admin.call_count == 0
