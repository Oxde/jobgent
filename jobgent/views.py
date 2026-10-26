"""Read models shared by MCP, CLI and web."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.classify import guess_language, in_region, prefilter
from jobgent.db import Application, Job, Match, Status
from jobgent.errors import JobgentError
from jobgent.profile.models import SearchProfile


class JobSummary(BaseModel):
    id: int
    title: str
    company: str
    location: str | None
    score: int | None
    status: str
    url: str
    posted_at: datetime | None
    source: str


class JobDetail(JobSummary):
    description: str
    reasons: list[str]
    gaps: list[str]
    is_internship: bool | None
    language: str | None
    dutch_required: bool | None
    dutch_plus: bool | None
    start_hint: str | None
    months: int | None
    paid: bool | None
    pack_dir: str | None


def summary(job: Job) -> JobSummary:
    return JobSummary(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        score=job.match.total if job.match else None,
        status=job.application.status.value if job.application else Status.new.value,
        url=job.url,
        posted_at=job.posted_at,
        source=job.source,
    )


def detail(job: Job) -> JobDetail:
    base = summary(job).model_dump()
    return JobDetail(
        **base,
        description=job.description,
        reasons=job.match.reasons if job.match else [],
        gaps=job.match.gaps if job.match else [],
        is_internship=job.is_internship,
        language=job.language,
        dutch_required=job.dutch_required,
        dutch_plus=job.dutch_plus,
        start_hint=job.start_hint,
        months=job.months,
        paid=job.paid,
        pack_dir=job.application.pack_dir if job.application else None,
    )


def get_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise JobgentError(f"No job with id {job_id}. Use jobs_list to find ids.")
    return job


def _rule_match(job: Job, search: SearchProfile) -> bool:
    """Feed rule for jobs no model has classified yet (no API key): title + region + language guess."""
    return prefilter(job.title) and in_region(job.location) and guess_language(job.description) in search.languages


def list_jobs(
    session: Session,
    search: SearchProfile,
    min_score: int = 0,
    status: str | None = None,
    source: str | None = None,
    limit: int = 30,
) -> list[JobSummary]:
    """Scored jobs that pass the model's filter, then unscored jobs that pass the rules, newest first."""
    q = select(Job).outerjoin(Match).outerjoin(Application)
    if source:
        q = q.where(Job.source.like(f"{source}%"))
    if status:
        if status == Status.new.value:
            q = q.where((Application.id.is_(None)) | (Application.status == Status.new))
        else:
            q = q.where(Application.status == Status(status))
    else:
        q = q.where((Application.id.is_(None)) | (Application.status.notin_([Status.skipped, Status.rejected])))
    scored: list[Job] = []
    unscored: list[Job] = []
    for job in session.scalars(q):
        passes_model = (
            job.is_internship is True
            and job.language in search.languages
            and job.dutch_required is False
            and job.in_region is not False
        )
        if job.match is not None:
            if passes_model and job.match.total >= min_score:
                scored.append(job)
        elif min_score == 0 and (passes_model if job.classified_at is not None else _rule_match(job, search)):
            unscored.append(job)
    scored.sort(key=lambda j: (-(j.match.total if j.match else 0), -j.id))
    unscored.sort(key=lambda j: (j.posted_at or j.fetched_at), reverse=True)
    return [summary(j) for j in (scored + unscored)[:limit]]


def list_applications(session: Session, status: str | None = None) -> list[JobSummary]:
    q = select(Job).join(Application)
    if status:
        q = q.where(Application.status == Status(status))
    else:
        q = q.where(Application.status != Status.new)
    q = q.order_by(Application.updated_at.desc())
    return [summary(j) for j in session.scalars(q)]
