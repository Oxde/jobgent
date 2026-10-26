from datetime import datetime

from jobgent.agent import agent_queue, run_agent
from jobgent.db import AgentRun, Evaluation, Job, Match, open_db


def test_run_agent_evaluates_only_new_top_jobs_and_records_the_run(services, monkeypatch):
    calls: list[int] = []

    def fake_fetch(svc, classify=True, score=True):
        from jobgent.fetch import FetchSummary
        from jobgent.ingest import IngestReport
        return FetchSummary(sources=[], ingest=IngestReport(inserted=3), skipped=[], classified=0, scored=0)

    def fake_eval(session, llm, model, profile, job, client=None):
        calls.append(job.id)
        ev = Evaluation(job=job, verdict="apply" if job.id == 2 else "skip", verdict_reason="r", gates=[], requirements=[], coverage=80)
        session.add(ev)
        session.commit()
        return ev

    monkeypatch.setattr("jobgent.agent.fetch_all", fake_fetch)
    monkeypatch.setattr("jobgent.agent.evaluate_job", fake_eval)
    services.llm_factory = lambda: object()
    run = run_agent(services, max_evaluate=5, min_score=60)
    assert sorted(calls) == [1, 2] and run.evaluated == 2 and run.queued == 1 and run.status == "done"
    # second run: already evaluated jobs are not paid for again
    calls.clear()
    run_agent(services, max_evaluate=5, min_score=60)
    assert calls == []
    with services.sessionmaker() as s:
        assert s.query(AgentRun).count() == 2
        queue = agent_queue(s)
    assert [q.job.id for q in queue] == [2]


def test_run_agent_without_key_fetches_and_says_why(services, monkeypatch):
    from jobgent.errors import MissingSecretError
    from jobgent.fetch import FetchSummary
    from jobgent.ingest import IngestReport

    monkeypatch.setattr("jobgent.agent.fetch_all", lambda svc, classify=True, score=True: FetchSummary(sources=[], ingest=IngestReport(inserted=5), skipped=["classify/score: ANTHROPIC_API_KEY not set"], classified=0, scored=0))

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    run = run_agent(services)
    assert run.status == "done" and run.evaluated == 0 and "ANTHROPIC_API_KEY" in run.note and run.fetched == 5
