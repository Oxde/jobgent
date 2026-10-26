"""Match score per job: four sub-scores, reasons and gaps."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.classify import feed_filter
from jobgent.db import Job, Match
from jobgent.llm import LLM
from jobgent.profile.models import Profile

_PROMPT = (Path(__file__).parent / "prompts" / "score.md").read_text()
DUTCH_PLUS_PENALTY = 10


class ScoreOutput(BaseModel):
    skills: int = Field(ge=0, le=50)
    role: int = Field(ge=0, le=20)
    lang_loc: int = Field(ge=0, le=15)
    timing: int = Field(ge=0, le=15)
    reasons: list[str]
    gaps: list[str]
    keywords: list[str] = Field(default_factory=list)


def profile_for_prompt(profile: Profile) -> str:
    data = profile.model_dump(mode="json")
    data["personal"] = {"name": profile.personal.name, "location": profile.personal.location}
    data.pop("verified", None)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def total_score(out: ScoreOutput, dutch_plus: bool) -> int:
    total = out.skills + out.role + out.lang_loc + out.timing
    if dutch_plus:
        total -= DUTCH_PLUS_PENALTY
    return max(total, 0)


def _render(profile: Profile, job: Job) -> str:
    return (
        f"## Student profile\n{profile_for_prompt(profile)}\n\n"
        f"## Posting\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location or ''}\n"
        f"Start hint: {job.start_hint or 'not stated'}\nDuration months: {job.months or 'not stated'}\n\n{job.description[:6000]}"
    )


def score_job(session: Session, llm: LLM, model: str, profile: Profile, job: Job) -> Match:
    out = llm.complete_json(model=model, system=_PROMPT, user=_render(profile, job), schema=ScoreOutput)
    match = job.match
    if match is None:
        match = Match(job=job)
        session.add(match)
    match.skills, match.role, match.lang_loc, match.timing = out.skills, out.role, out.lang_loc, out.timing
    match.reasons, match.gaps, match.model = out.reasons, out.gaps, model
    match.keywords = out.keywords
    match.total = total_score(out, bool(job.dutch_plus))
    session.commit()
    return match


def score_jobs(session: Session, llm: LLM, model: str, profile: Profile, limit: int | None = None) -> int:
    q = feed_filter(select(Job), profile.search).outerjoin(Match).where(Match.id.is_(None)).order_by(Job.id)
    if limit is not None:
        q = q.limit(limit)
    jobs = list(session.scalars(q))
    for job in jobs:
        score_job(session, llm, model, profile, job)
    return len(jobs)
