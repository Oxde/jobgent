"""Evaluation of one posting: gates → requirements (posting only) → evidence mapping (profile) → verdict.
The model extracts and maps; code decides coverage and the verdict."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobgent.db import Evaluation, Job
from jobgent.gates import Gate, run_gates
from jobgent.guard import wrap_posting
from jobgent.liveness import refresh_liveness
from jobgent.llm import LLM
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt, score_job

_DIR = Path(__file__).parent / "prompts"
_EXTRACT = (_DIR / "requirements.md").read_text()
_MAP = (_DIR / "map_requirements.md").read_text()

Importance = Literal["critical", "high", "nice"]
Coverage = Literal["covered", "partial", "gap"]
Verdict = Literal["apply", "consider", "skip"]
EvidenceKind = Literal["experience", "project", "skill", "education", "language", "none"]

APPLY_AT = 70
CONSIDER_AT = 50
_WEIGHT: dict[str, int] = {"critical": 3, "high": 2, "nice": 1}


class Requirement(BaseModel):
    text: str
    kind: Literal["skill", "experience", "language", "education", "other"] = "other"
    importance: Importance = "high"
    basis: Literal["stated", "inferred"] = "stated"


class Extracted(BaseModel):
    summary: str = ""
    deadline: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)


class Mapping(BaseModel):
    index: int
    evidence_kind: EvidenceKind = "none"
    evidence_ref: int | None = None
    evidence_text: str = ""


class Mapped(BaseModel):
    items: list[Mapping] = Field(default_factory=list)


class RequirementRow(BaseModel):
    text: str
    kind: str
    importance: Importance
    basis: str
    status: Coverage
    evidence: str


def _skill_used(profile: Profile, skill: str) -> bool:
    s = skill.lower()
    for e in profile.experience:
        if any(s in b.lower() for b in e.bullets) or s in e.title.lower():
            return True
    for p in profile.projects:
        if s in p.description.lower() or any(s == t.lower() or s in t.lower() for t in p.tech):
            return True
    return False


def resolve(requirements: list[Requirement], mappings: list[Mapping], profile: Profile) -> list[RequirementRow]:
    """Turn the model's pointers into covered / partial / gap. Pointers to missing entries count as gaps."""
    by_index = {m.index: m for m in mappings}
    lists: dict[str, list[object]] = {
        "experience": list(profile.experience), "project": list(profile.projects), "skill": list(profile.skills),
        "education": list(profile.education), "language": list(profile.languages),
    }
    rows: list[RequirementRow] = []
    for i, req in enumerate(requirements):
        importance: Importance = "high" if req.importance == "critical" and req.basis == "inferred" else req.importance
        m = by_index.get(i)
        status: Coverage = "gap"
        evidence = ""
        if m and m.evidence_kind != "none" and m.evidence_ref is not None:
            items = lists[m.evidence_kind]
            if 0 <= m.evidence_ref < len(items):
                evidence = m.evidence_text
                if m.evidence_kind == "skill":
                    skill = profile.skills[m.evidence_ref].name
                    status = "covered" if _skill_used(profile, skill) else "partial"
                else:
                    status = "covered"
        rows.append(RequirementRow(text=req.text, kind=req.kind, importance=importance, basis=req.basis, status=status, evidence=evidence))
    return rows


def coverage_percent(rows: list[RequirementRow]) -> int:
    total = sum(_WEIGHT[r.importance] for r in rows)
    if not total:
        return 0
    got = sum(_WEIGHT[r.importance] * (1.0 if r.status == "covered" else 0.5 if r.status == "partial" else 0.0) for r in rows)
    return round(100 * got / total)


def decide_verdict(gates: list[Gate], rows: list[RequirementRow], score: int | None) -> tuple[Verdict, str]:
    failed = [g for g in gates if g.status == "fail"]
    if failed:
        return "skip", " ".join(g.reason for g in failed)
    critical_gaps = [r.text for r in rows if r.importance == "critical" and r.status == "gap"]
    value = score if score is not None else coverage_percent(rows)
    flags = [g.reason for g in gates if g.status == "flag"]
    tail = f" Watch out: {flags[0]}" if flags else ""
    if value >= APPLY_AT and not critical_gaps:
        strong = [r.text for r in rows if r.status == "covered"][:2]
        return "apply", f"Strong fit ({value}): you cover {', '.join(strong) or 'the main requirements'}.{tail}"
    if value >= CONSIDER_AT or (value >= APPLY_AT and critical_gaps):
        why = f"missing a must-have: {', '.join(critical_gaps)}" if critical_gaps else "a partial fit"
        return "consider", f"Possible ({value}), {why}. Apply if the role excites you and you can address it in the letter.{tail}"
    return "skip", f"Weak fit ({value}). We advise against spending time on this one.{tail}"


def evaluate_job(
    session: Session, llm: LLM, model: str, profile: Profile, job: Job, client: httpx.Client | None = None
) -> Evaluation:
    if client is not None:
        refresh_liveness(session, job, client)
    gates = run_gates(job, profile)
    rows: list[RequirementRow] = []
    summary = ""
    deadline = job.deadline
    score: int | None = None
    if not any(g.status == "fail" for g in gates):
        posting = f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location or ''}\n\n{wrap_posting(job.description[:8000])}"
        extracted = llm.complete_json(model=model, system=_EXTRACT, user=posting, schema=Extracted, max_tokens=2048)
        reqs = "\n".join(f"{i}. [{r.importance}] {r.text}" for i, r in enumerate(extracted.requirements))
        mapped = llm.complete_json(
            model=model, system=_MAP, user=f"## Profile\n{profile_for_prompt(profile)}\n\n## Requirements\n{reqs}", schema=Mapped, max_tokens=2048
        )
        rows = resolve(extracted.requirements, mapped.items, profile)
        summary, deadline = extracted.summary, extracted.deadline or job.deadline
        score = score_job(session, llm, model, profile, job).total
    verdict, reason = decide_verdict(gates, rows, score)
    ev = job.evaluation or Evaluation(job=job)
    ev.gates = [g.model_dump() for g in gates]
    ev.requirements = [r.model_dump() for r in rows]
    ev.coverage = coverage_percent(rows)
    ev.verdict, ev.verdict_reason, ev.summary, ev.deadline = verdict, reason, summary, deadline
    ev.model, ev.created_at = model, datetime.now()
    job.deadline = deadline
    session.add(ev)
    session.commit()
    return ev
