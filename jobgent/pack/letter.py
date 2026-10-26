"""Cover letter in the user's voice, from profile facts only."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from jobgent.db import Job
from jobgent.guides import cv_writing_guide
from jobgent.llm import LLM
from jobgent.pack.tailor import job_text
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "letter.md").read_text() + "\n\n" + cv_writing_guide()


class CoverLetter(BaseModel):
    body: str


def write_letter(llm: LLM, model: str, profile: Profile, job: Job, voice: str) -> CoverLetter:
    system = _PROMPT.replace("{voice}", voice.strip())
    user = f"## Profile (only source of truth)\n{profile_for_prompt(profile)}\n\n## Posting\n{job_text(job)}"
    return llm.complete_json(model=model, system=system, user=user, schema=CoverLetter, max_tokens=2048)
