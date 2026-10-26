from datetime import date, datetime

from sqlalchemy import select

from jobgent.db import Job, Match, open_db
from jobgent.llm import FakeLLM
from jobgent.profile.models import Personal, Profile, SearchProfile
from jobgent.score import ScoreOutput, profile_for_prompt, score_jobs


def profile() -> Profile:
    return Profile(personal=Personal(name="A", email="secret@x.nl", phone="+310"),
                   search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def job(title: str, **kw: object) -> Job:
    base: dict[str, object] = dict(source="s", external_id=title, url="u", title=title, company="c", location=None,
                                   description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key=title,
                                   is_internship=True, language="en", dutch_required=False, dutch_plus=False,
                                   classified_at=datetime.now())
    base.update(kw)
    return Job(**base)


def out() -> ScoreOutput:
    return ScoreOutput(skills=40, role=20, lang_loc=15, timing=10, reasons=["python"], gaps=["sql"])


def test_total_and_dutch_plus_penalty(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        s.add_all([job("a"), job("b", dutch_plus=True)])
        s.commit()
        n = score_jobs(s, FakeLLM([out(), out()]), "m", profile())
        assert n == 2
        totals = {m.job.title: m.total for m in s.scalars(select(Match))}
        assert totals == {"a": 85, "b": 75}


def test_already_scored_jobs_are_skipped(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        s.add(job("a"))
        s.commit()
        llm = FakeLLM([out()])
        score_jobs(s, llm, "m", profile())
        assert score_jobs(s, llm, "m", profile()) == 0 and llm.calls == 1


def test_unclassified_or_excluded_jobs_not_scored(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        s.add_all([job("x", dutch_required=True), job("y", is_internship=False), job("z", classified_at=None, is_internship=None)])
        s.commit()
        assert score_jobs(s, FakeLLM([]), "m", profile()) == 0


def test_profile_for_prompt_has_no_contact_details():
    text = profile_for_prompt(profile())
    assert "secret@x.nl" not in text and "+310" not in text and "A" in text


def test_score_job_links_match_to_job_object(tmp_path):
    from jobgent.score import score_job
    from jobgent.views import detail

    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        j = job("a")
        s.add(j)
        s.commit()
        score_job(s, FakeLLM([out()]), "m", profile(), j)
        assert detail(j).score == 85 and detail(j).reasons == ["python"]


def test_score_output_keywords_are_stored(tmp_path):
    from jobgent.score import score_job

    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        j = job("a")
        s.add(j)
        s.commit()
        o = out()
        o.keywords = ["Python", "SQL"]
        m = score_job(s, FakeLLM([o]), "m", profile(), j)
        assert m.keywords == ["Python", "SQL"]
