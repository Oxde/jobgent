"""Select and rephrase profile facts for one posting. Never adds facts."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from stageone.db import Job
from stageone.llm import LLM
from stageone.profile.models import Education, Experience, Profile, Project
from stageone.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "tailor.md").read_text()


class TailoredCV(BaseModel):
    summary: str
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)

    def as_text(self) -> str:
        lines = [self.summary]
        for e in self.experience:
            lines.append(f"{e.title}, {e.company} ({e.period})")
            lines.extend(e.bullets)
        for p in self.projects:
            lines.append(f"{p.name}: {p.description} [{', '.join(p.tech)}]")
        for ed in self.education:
            lines.append(f"{ed.degree}, {ed.institution} ({ed.period}) {ed.gpa} {ed.details}".strip())
        lines.append("Skills: " + ", ".join(self.skills))
        return "\n".join(lines)


def job_text(job: Job) -> str:
    return (
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location or ''}\n"
        f"Start: {job.start_hint or 'not stated'}\n\n{job.description[:6000]}"
    )


def tailor_cv(llm: LLM, model: str, profile: Profile, job: Job, extra_instruction: str = "") -> TailoredCV:
    user = f"## Profile (only source of truth)\n{profile_for_prompt(profile)}\n\n## Posting\n{job_text(job)}"
    if extra_instruction:
        user += f"\n\n## Extra instruction\n{extra_instruction}"
    return llm.complete_json(model=model, system=_PROMPT, user=user, schema=TailoredCV, max_tokens=4096)
