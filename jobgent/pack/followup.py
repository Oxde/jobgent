"""Follow-up email after N days without an answer. At most two per application (see dashboard)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from jobgent.db import Job
from jobgent.llm import LLM
from jobgent.pack.factguard import banned_phrases, tidy_letter
from jobgent.pack.tailor import job_text
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "followup.md").read_text()


class FollowUp(BaseModel):
    subject: str
    body: str


def write_followup(llm: LLM, model: str, profile: Profile, job: Job, days: int, number: int) -> FollowUp:
    base = (
        f"## Profile\n{profile_for_prompt(profile)}\n\n## Facts about me\n" + "\n".join(profile.facts)
        + f"\n\n## Posting\n{job_text(job)}\n\nApplied {days} days ago. This is follow-up {number} of 2."
    )
    draft = llm.complete_json(model=model, system=_PROMPT, user=base, schema=FollowUp, max_tokens=800)
    bad = banned_phrases(draft.body)
    if bad:
        draft = llm.complete_json(model=model, system=_PROMPT, user=base + "\n\nRewrite without: " + ", ".join(bad), schema=FollowUp, max_tokens=800)
    return FollowUp(subject=draft.subject.strip(), body=tidy_letter(draft.body))
