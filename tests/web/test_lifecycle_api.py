from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from jobgent.db import Application, Status
from jobgent.llm import FakeLLM
from jobgent.pack.followup import FollowUp
from jobgent.web.app import create_app


def test_status_undo_notes_interview_and_timeline(services):
    c = TestClient(create_app(services))
    c.post("/api/jobs/1/status", json={"status": "applied"})
    r = c.post("/api/jobs/1/status/undo")
    assert r.status_code == 200 and r.json()["status"] == "new"
    c.post("/api/jobs/1/status", json={"status": "interview"})
    when = (datetime.now() + timedelta(days=1)).replace(microsecond=0)
    assert c.post("/api/jobs/1/interview", json={"at": when.isoformat()}).status_code == 200
    assert c.post("/api/jobs/1/notes", json={"text": "Recruiter: Anna"}).status_code == 200
    kinds = [i["kind"] for i in c.get("/api/jobs/1/timeline").json()]
    assert kinds == ["status", "interview", "note"]
    assert c.post("/api/jobs/2/status/undo").status_code == 400


def test_followup_draft_and_mark_sent(services):
    with services.sessionmaker() as s:
        s.add(Application(job_id=1, status=Status.applied, applied_at=datetime.now() - timedelta(days=9)))
        s.commit()
    services.llm_factory = lambda: FakeLLM([FollowUp(subject="Following up: AI Intern", body="Hi,\n\nSince applying I built X.\n\nBest,\nT")])
    c = TestClient(create_app(services))
    r = c.post("/api/jobs/1/followup")
    assert r.status_code == 200 and r.json()["subject"].startswith("Following up")
    assert c.get("/api/jobs/1/documents").json()["followup"]["units"][0]["text"] == "Hi,"
    assert c.post("/api/jobs/1/followup/sent").status_code == 200
    home = c.get("/api/home").json()
    assert all(a["kind"] != "follow_up" for a in home["actions"])  # just followed up


def test_followup_with_banned_phrase_is_rewritten(services):
    with services.sessionmaker() as s:
        s.add(Application(job_id=1, status=Status.applied, applied_at=datetime.now() - timedelta(days=9)))
        s.commit()
    fake = FakeLLM([FollowUp(subject="s", body="Just checking in on my application."), FollowUp(subject="s", body="I wanted to share a new project.")])
    services.llm_factory = lambda: fake
    r = TestClient(create_app(services)).post("/api/jobs/1/followup")
    assert r.json()["body"] == "I wanted to share a new project." and fake.calls == 2


def test_jobs_list_shows_verdict_deadline_age_and_collapses_cities(services):
    from jobgent.db import Evaluation, Job, Match

    with services.sessionmaker() as s:
        j1 = s.get(Job, 1)
        j1.deadline = "15 Nov 2026"
        j1.posted_at = datetime.now() - timedelta(days=40)
        s.add(Evaluation(job_id=1, verdict="apply", verdict_reason="r", gates=[], requirements=[]))
        twin = Job(source="ats:lever:acme", external_id="99", url="https://acme/99", title="Data Intern", company="Acme",
                   location="Utrecht", description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key="Data Intern|utrecht",
                   is_internship=True, language="en", dutch_required=False, dutch_plus=False, classified_at=datetime.now())
        s.add(twin)
        s.flush()
        s.add(Match(job_id=twin.id, total=50, skills=1, role=1, lang_loc=1, timing=1, reasons=[], gaps=[], model="m"))
        s.commit()
    services.store.update("search.locations", ["Netherlands"])
    rows = TestClient(create_app(services)).get("/api/jobs").json()
    data = next(r for r in rows if r["title"] == "Data Intern")
    ai = next(r for r in rows if r["title"] == "AI Intern")
    assert data["also_in"] == 1 and len([r for r in rows if r["title"] == "Data Intern"]) == 1
    assert ai["verdict"] == "apply" and ai["deadline"] == "15 Nov 2026" and ai["age_days"] >= 40
