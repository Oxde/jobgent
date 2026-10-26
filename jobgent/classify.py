"""Hard pre-filter plus a model pass: internship? English? Dutch required?"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from jobgent.db import Job
from jobgent.errors import JobgentError
from jobgent.llm import LLM
from jobgent.profile.models import SearchProfile

_PROMPT = (Path(__file__).parent / "prompts" / "classify.md").read_text()
MANUAL_SOURCE = "manual"
_INTERN_WORDS = re.compile(
    r"\b(intern|interns|internship|internships|stage|stagiair|stagiaire|afstudeer\w*|graduation|trainee|working\s+student|werkstudent)\b",
    re.IGNORECASE,
)


_REGION_WORDS = re.compile(
    r"\b(netherlands|the netherlands|nederland|holland|dutch|nl|amsterdam|rotterdam|utrecht|eindhoven|the hague|den haag"
    r"|delft|leiden|groningen|tilburg|nijmegen|enschede|maastricht|haarlem|amersfoort|arnhem|breda|zwolle|hilversum"
    r"|remote|europe|emea|eu)\b",
    re.IGNORECASE,
)


def prefilter(title: str) -> bool:
    return _INTERN_WORDS.search(title) is not None


def in_region(location: str | None) -> bool:
    """Unknown location passes; otherwise it must look like NL / remote / Europe-wide."""
    if not location:
        return True
    return _REGION_WORDS.search(location) is not None


class Classification(BaseModel):
    index: int
    is_internship: bool
    language: Literal["en", "nl", "other"]
    dutch_required: bool
    dutch_plus: bool
    start_hint: str | None = None
    months: int | None = None
    paid: bool | None = None


class ClassificationBatch(BaseModel):
    items: list[Classification] = Field(default_factory=list)


def _render(jobs: list[Job]) -> str:
    parts = []
    for i, j in enumerate(jobs):
        parts.append(f"### Posting {i}\nTitle: {j.title}\nCompany: {j.company}\nLocation: {j.location or ''}\n\n{j.description[:4000]}\n")
    return "\n".join(parts)


def classify_jobs(
    session: Session, llm: LLM, model: str, batch: int = 10, job_ids: list[int] | None = None
) -> int:
    """Classify jobs without `classified_at` (all of them, or only `job_ids`). Returns how many were handled.
    Jobs the user added by hand (source `manual`) always go to the model: no title or region pre-filter."""
    q = select(Job).where(Job.classified_at.is_(None)).order_by(Job.id)
    if job_ids is not None:
        q = q.where(Job.id.in_(job_ids))
    pending = list(session.scalars(q))
    now = datetime.now()
    to_model: list[Job] = []
    for job in pending:
        manual = job.source == MANUAL_SOURCE
        job.in_region = True if manual else in_region(job.location)
        if manual or (job.in_region and prefilter(job.title)):
            to_model.append(job)
        else:
            job.is_internship = False
            job.classified_at = now
    session.commit()
    for start in range(0, len(to_model), batch):
        chunk = to_model[start : start + batch]
        result = llm.complete_json(
            model=model, system=_PROMPT, user=_render(chunk), schema=ClassificationBatch, max_tokens=4096
        )
        by_index = {c.index: c for c in result.items}
        for i, job in enumerate(chunk):
            c = by_index.get(i)
            if c is None:
                raise JobgentError(f"classifier returned no item for posting {i} (job id {job.id}, {job.title!r})")
            job.is_internship = c.is_internship
            job.language = c.language
            job.dutch_required = c.dutch_required
            job.dutch_plus = c.dutch_plus
            job.start_hint = c.start_hint
            job.months = c.months
            job.paid = c.paid
            job.classified_at = now
        session.commit()
    return len(pending)


def feed_filter(q: Select[tuple[Job]], profile: SearchProfile) -> Select[tuple[Job]]:
    return q.where(
        Job.in_region.is_not(False),
        Job.is_internship.is_(True),
        Job.language.in_(profile.languages),
        Job.dutch_required.is_(False),
    )
