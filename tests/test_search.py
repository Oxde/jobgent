import json
from pathlib import Path

import httpx
import respx

from jobgent.config import load_settings
from jobgent.search import search_jobs

FIX = json.loads((Path(__file__).parent / "fixtures" / "apify_linkedin.json").read_text())


def test_search_runs_linkedin_now_and_returns_matching_jobs(services):
    services.settings = load_settings(env={"JOBGENT_HOME": str(services.settings.home), "APIFY_TOKEN": "t"}, secrets_file=services.settings.home / "none")
    with respx.mock as m:
        route = m.post(url__startswith="https://api.apify.com/").mock(return_value=httpx.Response(200, json=FIX))
        result = search_jobs(services, "AI intern", "Amsterdam")
    body = json.loads(route.calls[0].request.content)
    assert body["keywords"] == "AI intern" and body["location"] == "Amsterdam, North Holland, Netherlands"
    assert result.fetched == 2 and result.source_error is None
    titles = [j.title for j in result.jobs]
    assert "Data Science Intern" in titles  # Amsterdam, from LinkedIn
    assert "AI Intern" not in titles or all(j.location and "Rotterdam" not in j.location for j in result.jobs)


def test_search_without_token_still_searches_the_database(services):
    services.settings = load_settings(env={"JOBGENT_HOME": str(services.settings.home), "APIFY_TOKEN": ""}, secrets_file=services.settings.home / "none")
    result = search_jobs(services, "data", "Amsterdam")
    assert result.fetched == 0 and "APIFY_TOKEN" in (result.source_error or "")
    assert [j.title for j in result.jobs] == ["Data Intern"]
