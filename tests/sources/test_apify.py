import json
from pathlib import Path

import httpx
import pytest
import respx

from jobgent.errors import SourceError
from jobgent.sources.apify import ApifyLinkedInSource

FIX = Path(__file__).parent.parent / "fixtures" / "apify_linkedin.json"
RUN_URL = "https://api.apify.com/v2/acts/meka.im~linkedin-jobs-scraper/run-sync-get-dataset-items"


def test_linkedin_maps_dataset_items():
    src = ApifyLinkedInSource(token="t", keywords=["data intern"], locations=["Netherlands"], actor="meka.im~linkedin-jobs-scraper")
    with respx.mock(assert_all_called=True) as m:
        route = m.post(url__startswith=RUN_URL).mock(return_value=httpx.Response(200, json=json.loads(FIX.read_text())))
        with httpx.Client() as client:
            jobs = src.fetch(client)
    assert route.call_count == 1
    assert [j.external_id for j in jobs] == ["4001", "4002"]
    assert jobs[0].source == "linkedin"
    assert jobs[0].company == "Acme BV"
    assert jobs[1].description == "Build AI."
    assert jobs[0].posted_at is not None
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer t" and "token=" not in str(req.url)
    body = json.loads(req.content)
    assert body["keywords"] == "data intern" and body["location"] == "Netherlands"
    assert body["datePosted"] == "pastMonth" and body["limitPerSource"] == 100 and "keyword" not in body


def test_one_run_per_keyword_location_pair():
    src = ApifyLinkedInSource(token="t", keywords=["a", "b"], locations=["x", "y"])
    with respx.mock as m:
        route = m.post(url__startswith="https://api.apify.com/").mock(return_value=httpx.Response(200, json=[]))
        with httpx.Client() as client:
            src.fetch(client)
    assert route.call_count == 4


def test_unauthorized_raises_source_error_naming_apify():
    src = ApifyLinkedInSource(token="bad", keywords=["a"], locations=["x"])
    with respx.mock as m:
        m.post(url__startswith="https://api.apify.com/").mock(return_value=httpx.Response(401, text="nope"))
        with httpx.Client() as client, pytest.raises(SourceError, match="APIFY"):
            src.fetch(client)
