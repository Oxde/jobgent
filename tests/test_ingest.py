from datetime import datetime

import httpx

from stageone.db import Job, open_db
from stageone.ingest import dedupe_key, run_fetch, upsert_jobs
from stageone.sources.base import RawJob


def raw(source: str, ext: str, company: str, title: str, desc: str = "d") -> RawJob:
    return RawJob(source=source, external_id=ext, url=f"https://x/{ext}", title=title, company=company, location=None, description=desc, posted_at=None)


def test_dedupe_key_normalises():
    assert dedupe_key("Picnic", "Data Science Intern (m/f/d) 2027") == "picnic|data science|"
    assert dedupe_key("ACME B.V.", "Stagiair AI – Internship") == "acme|ai|"


def test_upsert_counts_and_updates(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        r = upsert_jobs(s, [raw("linkedin", "1", "Acme", "AI Intern")])
        assert (r.inserted, r.updated, r.duplicates) == (1, 0, 0)
        r = upsert_jobs(s, [raw("linkedin", "1", "Acme", "AI Intern", desc="new")])
        assert (r.inserted, r.updated, r.duplicates) == (0, 1, 0)
        assert s.query(Job).one().description == "new"


def test_cross_source_duplicate_prefers_ats(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        upsert_jobs(s, [raw("linkedin", "1", "Acme", "AI Intern")])
        r = upsert_jobs(s, [raw("ats:greenhouse:acme", "9", "Acme", "AI Internship")])
        assert r.duplicates == 1
        jobs = s.query(Job).all()
        assert len(jobs) == 1 and jobs[0].source == "ats:greenhouse:acme"
        # the reverse direction keeps the ATS row
        r = upsert_jobs(s, [raw("linkedin", "2", "Acme", "AI Intern")])
        assert r.duplicates == 1 and s.query(Job).one().source == "ats:greenhouse:acme"


class _Good:
    name = "good"

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        return [raw("good", "1", "Acme", "Intern")]


class _Bad:
    name = "bad"

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        raise RuntimeError("exploded")


def test_run_fetch_isolates_source_failures(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s, httpx.Client() as client:
        report = run_fetch(s, [_Bad(), _Good()], client)
    assert report.ingest.inserted == 1
    by_name = {r.source: r for r in report.results}
    assert by_name["bad"].error == "RuntimeError: exploded"
    assert by_name["good"].error is None and len(by_name["good"].jobs) == 1
    assert report.failed == ["bad"]


def test_dedupe_key_includes_city():
    assert dedupe_key("Acme", "AI Intern", "Amsterdam, North Holland, Netherlands") == "acme|ai|amsterdam"
    assert dedupe_key("Acme", "AI Intern", "Amsterdam, Netherlands") == "acme|ai|amsterdam"
    assert dedupe_key("Acme", "AI Intern", None) == "acme|ai|"


def test_same_title_different_city_is_not_duplicate(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        a = raw("ats:greenhouse:x", "1", "Acme", "AI Intern")
        b = raw("ats:greenhouse:x", "2", "Acme", "AI Intern")
        a.location, b.location = "Amsterdam, Netherlands", "Berlin, Germany"
        r = upsert_jobs(s, [a, b])
        assert (r.inserted, r.duplicates) == (2, 0)
