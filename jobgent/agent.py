"""The daily job agent: fetch → score → evaluate the best new postings → queue the ones worth the student's time.
It never applies or sends anything; the queue is a suggestion list."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import AgentRun, Application, Evaluation, Job, Status
from jobgent.errors import JobgentError, MissingSecretError
from jobgent.evaluate import evaluate_job
from jobgent.fetch import fetch_all
from jobgent.service import Services
from jobgent.views import JobSummary, list_jobs, summary

DEFAULT_MAX_EVALUATE = 15
DEFAULT_MIN_SCORE = 65


class QueueItem(BaseModel):
    job: JobSummary
    verdict: str
    reason: str
    red_flags: list[str]


def _step(session: Session, run: AgentRun, step: str) -> None:
    run.step = step
    session.commit()


def run_agent(services: Services, max_evaluate: int = DEFAULT_MAX_EVALUATE, min_score: int = DEFAULT_MIN_SCORE) -> AgentRun:
    with services.sessionmaker() as s:
        run = AgentRun()
        s.add(run)
        s.commit()
        notes: list[str] = []
        try:
            _step(s, run, "Fetching new postings")
            fetched = fetch_all(services, classify=True, score=True)
            run.fetched = fetched.ingest.inserted
            notes += fetched.skipped
            notes += [f"{src.source}: {src.error}" for src in fetched.sources if src.error]
            try:
                llm = services.llm_factory()
            except MissingSecretError as e:
                notes.append(f"Evaluation skipped: {e.name} not set.")
                llm = None
            if llm is not None:
                _step(s, run, "Evaluating the best new postings")
                profile = services.store.load()
                todo: list[Job] = []
                for c in list_jobs(s, profile.search, min_score=min_score, limit=1000):
                    candidate = s.get(Job, c.id)
                    if c.score is not None and candidate is not None and candidate.evaluation is None:
                        todo.append(candidate)
                with services.http_client_factory() as client:
                    for job in todo[:max_evaluate]:
                        try:
                            ev = evaluate_job(s, llm, services.settings.fast_model, profile, job, client)
                        except JobgentError as e:
                            notes.append(f"{job.title}: {e}")
                            continue
                        run.evaluated += 1
                        if ev.verdict in ("apply", "consider"):
                            run.queued += 1
            run.status = "done"
        except Exception as e:  # noqa: BLE001 — a failed run is recorded and shown, not swallowed
            run.status, run.error = "failed", f"{type(e).__name__}: {e}"
        run.note = "\n".join(notes)
        run.step = ""
        run.finished_at = datetime.now()
        s.commit()
        if run.status == "failed":
            raise JobgentError(f"Agent run failed: {run.error}")
        return run


def agent_queue(session: Session) -> list[QueueItem]:
    """Evaluated postings worth a look that the student has not acted on: apply first, then consider, by score."""
    rows = session.scalars(
        select(Evaluation).join(Job).outerjoin(Application)
        .where(Evaluation.verdict.in_(["apply", "consider"]), Evaluation.dismissed.is_(False))
        .where((Application.id.is_(None)) | (Application.status == Status.new))
    )
    items = [
        QueueItem(job=summary(e.job), verdict=e.verdict, reason=e.verdict_reason,
                  red_flags=[g["reason"] for g in e.gates if g.get("status") == "flag"])
        for e in rows
    ]
    return sorted(items, key=lambda q: (q.verdict != "apply", -(q.job.score or 0)))


def last_run(session: Session) -> AgentRun | None:
    return session.scalar(select(AgentRun).order_by(AgentRun.id.desc()))
