from datetime import date, datetime

from sqlalchemy import select

from jobgent.classify import Classification, ClassificationBatch, classify_jobs, feed_filter, prefilter
from jobgent.db import Job, open_db
from jobgent.llm import FakeLLM
from jobgent.profile.models import SearchProfile


def job(title: str, **kw: object) -> Job:
    base: dict[str, object] = dict(source="s", external_id=title, url="u", title=title, company="c", location=None,
                                   description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key=title)
    base.update(kw)
    return Job(**base)


def test_prefilter():
    assert prefilter("Senior Engineer") is False
    assert prefilter("Stagiair Data") is True
    assert prefilter("Graduation Internship AI") is True
    assert prefilter("Working Student - ML") is True


def test_classify_skips_prefiltered_and_writes_fields(tmp_path):
    Session = open_db(tmp_path / "t.db")
    llm = FakeLLM([ClassificationBatch(items=[Classification(index=0, is_internship=True, language="en", dutch_required=False, dutch_plus=True, start_hint="Feb 2027", months=5, paid=True)])])
    with Session() as s:
        s.add_all([job("Senior Engineer"), job("Data Intern")])
        s.commit()
        n = classify_jobs(s, llm, "m")
        assert n == 2 and llm.calls == 1
        senior = s.scalar(select(Job).where(Job.title == "Senior Engineer"))
        intern = s.scalar(select(Job).where(Job.title == "Data Intern"))
        assert senior is not None and senior.is_internship is False and senior.classified_at is not None
        assert intern is not None and intern.is_internship is True and intern.dutch_plus is True and intern.months == 5
        assert classify_jobs(s, llm, "m") == 0


def test_feed_filter_keeps_dutch_plus_drops_dutch_required(tmp_path):
    Session = open_db(tmp_path / "t.db")
    sp = SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))
    with Session() as s:
        s.add_all([
            job("plus", is_internship=True, language="en", dutch_required=False, dutch_plus=True),
            job("req", is_internship=True, language="en", dutch_required=True, dutch_plus=False),
            job("nl", is_internship=True, language="nl", dutch_required=False),
            job("notintern", is_internship=False, language="en", dutch_required=False),
        ])
        s.commit()
        titles = {j.title for j in s.scalars(feed_filter(select(Job), sp))}
    assert titles == {"plus"}


def test_in_region():
    from jobgent.classify import in_region

    assert in_region(None) is True
    assert in_region("Amsterdam, Netherlands") is True
    assert in_region("Remote - EMEA") is True
    assert in_region("San Francisco, CA") is False
    assert in_region("Berlin, Germany") is False


def test_out_of_region_jobs_skip_model_and_leave_feed(tmp_path):
    Session = open_db(tmp_path / "t.db")
    llm = FakeLLM([ClassificationBatch(items=[Classification(index=0, is_internship=True, language="en", dutch_required=False, dutch_plus=False)])])
    sp = SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))
    with Session() as s:
        s.add_all([job("Data Intern", location="Austin, TX"), job("AI Intern", location="Utrecht")])
        s.commit()
        assert classify_jobs(s, llm, "m") == 2 and llm.calls == 1
        titles = {j.title for j in s.scalars(feed_filter(select(Job), sp))}
    assert titles == {"AI Intern"}


def test_manual_jobs_bypass_prefilters_and_job_ids_limits_scope(tmp_path):
    Session = open_db(tmp_path / "t.db")
    llm = FakeLLM([ClassificationBatch(items=[Classification(index=0, is_internship=True, language="en", dutch_required=False, dutch_plus=False)])])
    with Session() as s:
        manual = job("Junior Data Analyst (6-month placement)", source="manual", location="Austin, TX")
        other = job("Data Intern")
        s.add_all([manual, other])
        s.commit()
        assert classify_jobs(s, llm, "m", job_ids=[manual.id]) == 1 and llm.calls == 1
        assert manual.is_internship is True and other.classified_at is None


def test_classify_commits_per_batch(tmp_path):
    Session = open_db(tmp_path / "t.db")

    class Flaky(FakeLLM):
        def complete_json(self, **kw):
            if self.calls == 1:
                self.calls += 1
                raise RuntimeError("boom")
            return super().complete_json(**kw)

    llm = Flaky([ClassificationBatch(items=[Classification(index=0, is_internship=True, language="en", dutch_required=False, dutch_plus=False)])])
    with Session() as s:
        s.add_all([job("A Intern"), job("B Intern")])
        s.commit()
        import pytest as _pt

        with _pt.raises(RuntimeError):
            classify_jobs(s, llm, "m", batch=1)
    with Session() as s:
        done = [j.title for j in s.scalars(select(Job).where(Job.classified_at.is_not(None)))]
        assert done == ["A Intern"]


def test_guess_language():
    from jobgent.classify import guess_language

    assert guess_language("Wij zoeken een stagiair voor ons team. Je werkt mee aan de ontwikkeling van onze producten en je bent leergierig.") == "nl"
    assert guess_language("We are looking for an intern to join our team. You will work on data pipelines and you are curious.") == "en"
    assert guess_language("") == "other"
