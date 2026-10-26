from datetime import date, datetime, timedelta

from jobgent.db import Job, Match, open_db
from jobgent.profile.models import SearchProfile
from jobgent.views import list_jobs

EN = "We are looking for an intern to join our data team. You will build models and you are curious about AI."
NL = "Wij zoeken een stagiair voor ons team. Je werkt mee aan de ontwikkeling van onze producten en je bent leergierig."


def job(title: str, **kw: object) -> Job:
    base: dict[str, object] = dict(source="s", external_id=title, url="u", title=title, company="c", location="Amsterdam",
                                   description=EN, posted_at=datetime.now(), fetched_at=datetime.now(), dedupe_key=title)
    base.update(kw)
    return Job(**base)


def test_unscored_jobs_show_without_a_key_using_rules(tmp_path):
    Session = open_db(tmp_path / "t.db")
    sp = SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))
    with Session() as s:
        scored = job("Data Intern", is_internship=True, language="en", dutch_required=False, in_region=True, classified_at=datetime.now())
        s.add(scored)
        s.flush()
        s.add(Match(job_id=scored.id, total=80, skills=40, role=20, lang_loc=10, timing=10, reasons=[], gaps=[], model="m"))
        s.add_all([
            job("AI Intern", posted_at=datetime.now() - timedelta(days=1)),
            job("Stagiair Marketing", description=NL),
            job("Senior Engineer"),
            job("ML Intern", location="Austin, TX"),
        ])
        s.commit()
        rows = list_jobs(s, sp)
    assert [(r.title, r.score) for r in rows] == [("Data Intern", 80), ("AI Intern", None)]


def test_classified_but_unscored_jobs_show_when_they_pass_the_model_filter(tmp_path):
    Session = open_db(tmp_path / "t.db")
    sp = SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))
    with Session() as s:
        s.add_all([
            job("ING AI Intern", source="manual", is_internship=True, language="en", dutch_required=False, classified_at=datetime.now()),
            job("ABN Stagiaire", source="manual", is_internship=True, language="nl", dutch_required=True, classified_at=datetime.now()),
        ])
        s.commit()
        rows = list_jobs(s, sp)
    assert [(r.title, r.score) for r in rows] == [("ING AI Intern", None)]
