from fastapi.testclient import TestClient

from jobgent.db import Evaluation
from jobgent.interview import InterviewPrep, Question
from jobgent.llm import FakeLLM
from jobgent.web.app import create_app


def test_agent_endpoints(services, monkeypatch):
    from jobgent.db import AgentRun

    def fake_run(svc, max_evaluate=15, min_score=65):
        with svc.sessionmaker() as s:
            r = AgentRun(status="done", fetched=4, evaluated=1, queued=1, note="")
            s.add(r)
            s.add(Evaluation(job_id=2, verdict="apply", verdict_reason="Strong fit", gates=[{"name": "language", "status": "flag", "reason": "Dutch is a plus"}], requirements=[]))
            s.commit()
            return r

    monkeypatch.setattr("jobgent.web.app.run_agent", fake_run)
    c = TestClient(create_app(services))
    assert c.get("/api/agent").json()["last_run"] is None
    r = c.post("/api/agent/run")
    assert r.status_code == 200 and r.json()["fetched"] == 4
    d = c.get("/api/agent").json()
    assert d["last_run"]["queued"] == 1 and d["queue"][0]["job"]["title"] == "Data Intern" and d["queue"][0]["red_flags"] == ["Dutch is a plus"]
    assert c.post("/api/agent/dismiss/2").status_code == 200
    assert c.get("/api/agent").json()["queue"] == []


def test_insights_endpoint(services):
    with services.sessionmaker() as s:
        s.add(Evaluation(job_id=1, verdict="consider", verdict_reason="", gates=[], requirements=[
            {"text": "SQL", "kind": "skill", "importance": "critical", "basis": "stated", "status": "gap", "evidence": ""}]))
        s.commit()
    d = TestClient(create_app(services)).get("/api/insights").json()
    assert d["learning_gaps"][0]["skill"] == "SQL" and "calibration" in d


def test_interview_prep_saved_and_read_back(services):
    services.llm_factory = lambda: FakeLLM([InterviewPrep(likely_questions=[Question(question="Why us?")], questions_to_ask=["What does success look like?"])])
    c = TestClient(create_app(services))
    assert c.get("/api/jobs/1/interview-prep").json() is None
    r = c.post("/api/jobs/1/interview-prep", json={"stage": "first round"})
    assert r.status_code == 200 and r.json()["likely_questions"][0]["question"] == "Why us?"
    assert c.get("/api/jobs/1/interview-prep").json()["stage"] == "first round"
