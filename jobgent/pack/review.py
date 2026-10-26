"""A second agent reviews the drafts. It suggests exact replacements; code applies only those that match."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from jobgent.db import Job
from jobgent.llm import LLM
from jobgent.pack.letter import CoverLetter
from jobgent.pack.tailor import TailoredCV, job_text
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "review.md").read_text()
_UNIT = re.compile(r"^(experience|projects)\[(\d+)\]\.(bullets\[(\d+)\]|description)$")


class ReviewEdit(BaseModel):
    unit: str
    old: str
    new: str
    reason: str = ""


class Review(BaseModel):
    edits: list[ReviewEdit] = Field(default_factory=list)
    missed_keywords: str = ""
    company_angle: str = ""
    passive_phrasing: str = ""
    tone: str = ""


def review_pack(llm: LLM, model: str, profile: Profile, job: Job, cv: TailoredCV, letter: CoverLetter, tone: str) -> Review:
    user = (
        f"## Profile (only source of truth)\n{profile_for_prompt(profile)}\n\n## Posting\n{job_text(job)}\n\n"
        f"## Tailored CV (units)\n{units_text(cv)}\n\n## Cover letter (unit: letter; tone: {tone})\n{letter.body}"
    )
    return llm.complete_json(model=model, system=_PROMPT, user=user, schema=Review, max_tokens=3000)


def units_text(cv: TailoredCV) -> str:
    lines = [f"[summary] {cv.summary}"]
    for i, e in enumerate(cv.experience):
        for j, b in enumerate(e.bullets):
            lines.append(f"[experience[{i}].bullets[{j}]] {b}")
    for i, p in enumerate(cv.projects):
        lines.append(f"[projects[{i}].description] {p.description}")
    return "\n".join(lines)


def apply_review(cv: TailoredCV, letter: CoverLetter, review: Review) -> tuple[TailoredCV, CoverLetter, list[str], list[str]]:
    cv = cv.model_copy(deep=True)
    body = letter.body
    applied: list[str] = []
    skipped: list[str] = []
    for edit in review.edits:
        ok = False
        if edit.unit == "summary" and edit.old in cv.summary:
            cv.summary = cv.summary.replace(edit.old, edit.new, 1)
            ok = True
        elif edit.unit == "letter" and edit.old in body:
            body = body.replace(edit.old, edit.new, 1)
            ok = True
        else:
            m = _UNIT.match(edit.unit)
            if m:
                section, i = m.group(1), int(m.group(2))
                if section == "experience" and i < len(cv.experience) and m.group(4) is not None:
                    j = int(m.group(4))
                    bullets = cv.experience[i].bullets
                    if j < len(bullets) and edit.old in bullets[j]:
                        bullets[j] = bullets[j].replace(edit.old, edit.new, 1)
                        ok = True
                elif section == "projects" and i < len(cv.projects) and edit.old in cv.projects[i].description:
                    cv.projects[i].description = cv.projects[i].description.replace(edit.old, edit.new, 1)
                    ok = True
        (applied if ok else skipped).append(edit.unit)
    return cv, CoverLetter(body=body), applied, skipped
