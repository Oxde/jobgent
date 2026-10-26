"""Learning from the search itself, without AI calls: what to learn next, and whether the scores predict answers."""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Application, Evaluation, Job
from jobgent.profile.models import Profile

_IMPORTANCE = {"critical": 3.0, "high": 2.0, "nice": 1.0}
_VERDICT = {"skip": 1.5, "consider": 1.2, "apply": 1.0}  # gaps on jobs you could not go for count more


class LearningGap(BaseModel):
    skill: str
    jobs: int
    weight: float
    examples: list[str]


def learning_gaps(session: Session, profile: Profile, limit: int = 12) -> list[LearningGap]:
    have = {s.name.lower() for s in profile.skills}
    acc: dict[str, LearningGap] = {}
    for ev in session.scalars(select(Evaluation)):
        for r in ev.requirements:
            if r.get("status") != "gap" or r.get("kind") not in ("skill", "experience", None):
                continue
            text = str(r.get("text", "")).strip()
            key = text.lower()
            if not key or key in have:
                continue
            w = _IMPORTANCE.get(str(r.get("importance")), 1.0) * _VERDICT.get(ev.verdict, 1.0)
            gap = acc.setdefault(key, LearningGap(skill=text, jobs=0, weight=0.0, examples=[]))
            gap.jobs += 1
            gap.weight = round(gap.weight + w, 2)
            title = f"{ev.job.title} ({ev.job.company})"
            if len(gap.examples) < 3 and title not in gap.examples:
                gap.examples.append(title)
    return sorted(acc.values(), key=lambda g: (-g.weight, -g.jobs, g.skill))[:limit]


class CalibrationRow(BaseModel):
    group: str
    sent: int
    heard_back: int
    interviews: int


def calibration(session: Session) -> list[CalibrationRow]:
    """Advisory only: how sent applications did, grouped by the agent's verdict and by score band."""
    groups: dict[str, CalibrationRow] = {}
    for app in session.scalars(select(Application).join(Job)):
        stage = app.furthest_stage or ""
        if app.applied_at is None and stage not in ("applied", "interview", "offer"):
            continue
        interview = stage in ("interview", "offer")
        heard = interview or app.status.value == "rejected"
        keys = []
        if app.job.evaluation:
            keys.append(app.job.evaluation.verdict)
        if app.job.match:
            t = app.job.match.total
            keys.append("score 70+" if t >= 70 else "score 50-69" if t >= 50 else "score <50")
        for k in keys:
            row = groups.setdefault(k, CalibrationRow(group=k, sent=0, heard_back=0, interviews=0))
            row.sent += 1
            row.heard_back += int(heard)
            row.interviews += int(interview)
    order = ["apply", "consider", "skip", "score 70+", "score 50-69", "score <50"]
    return sorted(groups.values(), key=lambda r: order.index(r.group) if r.group in order else 99)
