"""Rewrite one unit of a document on request. The model may decline when the request needs facts the profile lacks."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from jobgent.db import Job
from jobgent.guides import cv_writing_guide
from jobgent.llm import LLM
from jobgent.pack.tailor import job_text
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "rewrite.md").read_text() + "\n\n" + cv_writing_guide()


class Rewrite(BaseModel):
    text: str = ""
    declined: bool = False
    reason: str = ""


def rewrite_unit(llm: LLM, model: str, profile: Profile, job: Job, label: str, text: str, instruction: str) -> Rewrite:
    user = (
        f"## Profile (only source of truth)\n{profile_for_prompt(profile)}\n\n## Facts about me\n" + "\n".join(profile.facts)
        + f"\n\n## Posting\n{job_text(job)}\n\n## The piece to rewrite ({label})\n{text}\n\n## Instruction\n{instruction}"
    )
    return llm.complete_json(model=model, system=_PROMPT, user=user, schema=Rewrite, max_tokens=1200)
