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


TONES: dict[str, str] = {
    "warm": "Warm: friendly and personal, still concise. Sign off with 'Warm regards,'.",
    "direct": "Direct: short sentences, straight to the point, confident. Sign off with 'Best,'.",
    "formal": "Formal: polite and complete, no slang. Sign off with 'Kind regards,'.",
}


def letter_instructions(voice: str, tone: str) -> str:
    return _PROMPT.replace("{voice}", voice.strip()).replace("{tone}", TONES.get(tone, TONES["warm"]))


def write_letter(
    llm: LLM,
    model: str,
    profile: Profile,
    job: Job,
    voice: str,
    tone: str = "warm",
    note: str = "",
    requirements: list[str] | None = None,
    fix: list[str] | None = None,
) -> CoverLetter:
    system = letter_instructions(voice, tone)
    parts = [f"## Profile (only source of truth)\n{profile_for_prompt(profile)}"]
    if profile.facts:
        parts.append("## Facts about me (use, never invent beyond them)\n" + "\n".join(f"- {f}" for f in profile.facts))
    if note:
        parts.append(f"## The student's note for this application\n{note}")
    if requirements:
        parts.append("## Requirements and how the profile covers them\n" + "\n".join(requirements))
    parts.append(f"## Posting\n{job_text(job)}")
    if fix:
        parts.append("## Rewrite needed\nThe previous draft used banned phrases: " + ", ".join(fix) + ". Write it again without them.")
    return llm.complete_json(model=model, system=system, user="\n\n".join(parts), schema=CoverLetter, max_tokens=2048)
