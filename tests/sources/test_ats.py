import json
from pathlib import Path

import httpx
import pytest
import respx

from stageone.errors import SourceError
from stageone.sources.ats import ATSSource
from stageone.sources.base import html_to_text
from stageone.sources.companies import Company, load_companies

FIX = Path(__file__).parent.parent / "fixtures" / "ats"

CASES = {
    "greenhouse": ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "Data Science Intern"),
    "lever": ("https://api.lever.co/v0/postings/acme", "Software Engineering Intern"),
    "recruitee": ("https://acme.recruitee.com/api/offers/", "AI Intern"),
    "homerun": ("https://acme.homerun.co/api/v1/jobs", "Marketing Intern"),
    "ashby": ("https://api.ashbyhq.com/posting-api/job-board/acme", "ML Intern"),
    "workable": ("https://apply.workable.com/api/v1/widget/accounts/acme", "Product Intern"),
}


@pytest.mark.parametrize("ats", list(CASES))
def test_ats_adapter_parses_fixture(ats):
    url, title = CASES[ats]
    src = ATSSource(Company(name="Acme", ats=ats, board="acme"))
    with respx.mock(assert_all_called=True) as m:
        m.get(url__startswith=url).mock(return_value=httpx.Response(200, json=json.loads((FIX / f"{ats}.json").read_text())))
        with httpx.Client() as client:
            jobs = src.fetch(client)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == title
    assert j.company == "Acme"
    assert j.url.startswith("https://")
    assert "<" not in j.description and j.description.strip()
    assert j.source == f"ats:{ats}:acme"
    assert j.posted_at is not None


def test_ats_http_error_raises_source_error():
    src = ATSSource(Company(name="Acme", ats="lever", board="acme"))
    with respx.mock as m:
        m.get(url__startswith="https://api.lever.co/v0/postings/acme").mock(return_value=httpx.Response(500, text="boom"))
        with httpx.Client() as client, pytest.raises(SourceError, match="500"):
            src.fetch(client)


def test_html_to_text_strips_tags_and_entities():
    assert html_to_text("<p>Hello&nbsp;<b>world</b></p><ul><li>a</li></ul>") == "Hello world\na"


def test_load_companies(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("companies:\n  - name: Acme\n    ats: greenhouse\n    board: acme\n")
    cs = load_companies(f)
    assert cs == [Company(name="Acme", ats="greenhouse", board="acme")]


def test_shipped_companies_file_is_valid():
    cs = load_companies(Path(__file__).parent.parent.parent / "data" / "companies.yaml")
    assert len(cs) >= 20
