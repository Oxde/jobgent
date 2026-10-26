"""Interview prep per job and stage: likely questions, STAR stories from profile facts only, consistency with what was sent."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from jobgent.db import Job
from jobgent.errors import InventedClaimError
from jobgent.guard import wrap_posting
from jobgent.llm import LLM
from jobgent.pack.factguard import fact_check
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent / "prompts" / "interview.md").read_text()


class Question(BaseModel):
    question: str
    why: str = ""
    answer_hint: str = ""


class Star(BaseModel):
    title: str
    situation: str
    task: str
    action: str
    result: str
    source: str = ""


class InterviewPrep(BaseModel):
    likely_questions: list[Question] = Field(default_factory=list)
    stories: list[Star] = Field(default_factory=list)
    consistency: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    gaps_to_prepare: list[str] = Field(default_factory=list)


def prepare_interview(
    llm: LLM, model: str, profile: Profile, job: Job, stage: str, gaps: list[str], cv_text: str, letter_text: str
) -> InterviewPrep:
    user = (
        f"## Stage\n{stage}\n\n## Profile (only source of truth)\n{profile_for_prompt(profile)}\n\n## Facts about me\n" + "\n".join(profile.facts)
        + f"\n\n## Gaps found when evaluating this job\n" + ("\n".join(f"- {g}" for g in gaps) or "none recorded")
        + f"\n\n## CV that was sent\n{cv_text or 'not available'}\n\n## Cover letter that was sent\n{letter_text or 'not available'}"
        + f"\n\n## Posting ({job.title} at {job.company})\n{wrap_posting(job.description[:8000])}"
    )
    prep = llm.complete_json(model=model, system=_PROMPT, user=user, schema=InterviewPrep, max_tokens=4000)
    corpus = yaml.safe_dump(profile.model_dump(mode="json"), allow_unicode=True) + "\n".join(profile.facts) + job.description + cv_text + letter_text
    story_text = "\n".join(f"{s.situation} {s.task} {s.action} {s.result}" for s in prep.stories)
    report = fact_check(story_text, corpus)
    if report.invented_numbers:
        raise InventedClaimError([f"number not in your profile: {n}" for n in report.invented_numbers])
    return prep
