"""Read models for Home and Applications: what needs doing, grouped by stage."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Application, Job, Status
from jobgent.profile.models import Profile
from jobgent.profile.store import ChecklistItem, completeness
from jobgent.tracker import WeeklyStats, weekly_stats
from jobgent.views import JobSummary, list_jobs, summary

NO_ANSWER_DAYS = 14
ActionKind = Literal["make_pack", "send", "follow_up"]


class ActionItem(BaseModel):
    kind: ActionKind
    job: JobSummary
    days_since: int | None
    text: str


class HomeData(BaseModel):
    top_matches: list[JobSummary]
    actions: list[ActionItem]
    stats: WeeklyStats
    checklist: list[ChecklistItem]
    weeks_left: int
    start_from: str


class Card(BaseModel):
    job: JobSummary
    days_since: int | None
    applied_at: datetime | None
    notes: str
    has_pack: bool


class Column(BaseModel):
    key: str
    title: str
    cards: list[Card]


def _days(since: datetime | None) -> int | None:
    return (datetime.now() - since).days if since else None


def needs_action(session: Session) -> list[ActionItem]:
    items: list[ActionItem] = []
    apps = list(session.scalars(select(Application).join(Job).order_by(Application.updated_at.desc())))
    for a in apps:
        job = summary(a.job)
        if a.status == Status.liked:
            items.append(ActionItem(kind="make_pack", job=job, days_since=None, text="Kept, no application pack yet"))
        elif a.status == Status.pack_ready:
            items.append(ActionItem(kind="send", job=job, days_since=None, text="Pack ready, not sent"))
        elif a.status == Status.applied:
            d = _days(a.applied_at)
            if d is not None and d >= NO_ANSWER_DAYS:
                items.append(ActionItem(kind="follow_up", job=job, days_since=d, text=f"Applied {d} days ago, no answer: follow up"))
    order = {"send": 0, "make_pack": 1, "follow_up": 2}
    return sorted(items, key=lambda i: order[i.kind])


def home_data(session: Session, profile: Profile) -> HomeData:
    start = profile.search.start_from
    weeks_left = max(0, (datetime.combine(start, datetime.min.time()) - datetime.now()).days // 7)
    return HomeData(
        top_matches=list_jobs(session, profile.search, 0, None, None, 6),
        actions=needs_action(session),
        stats=weekly_stats(session, profile.preferences.weekly_goal),
        checklist=completeness(profile),
        weeks_left=weeks_left,
        start_from=start.strftime("%B %Y"),
    )


STAGES: list[tuple[str, str]] = [
    ("liked", "Saved"),
    ("pack_ready", "Pack ready"),
    ("applied", "Applied"),
    ("no_answer", "No answer"),
    ("interview", "Interviewing"),
    ("offer", "Offer"),
    ("rejected", "Rejected"),
]


def applications_board(session: Session) -> list[Column]:
    columns = {key: Column(key=key, title=title, cards=[]) for key, title in STAGES}
    apps = list(session.scalars(select(Application).join(Job).order_by(Application.updated_at.desc())))
    for a in apps:
        if a.status in (Status.new, Status.skipped):
            continue
        key = a.status.value
        d = _days(a.applied_at)
        if a.status == Status.applied and d is not None and d >= NO_ANSWER_DAYS:
            key = "no_answer"
        columns[key].cards.append(
            Card(job=summary(a.job), days_since=d, applied_at=a.applied_at, notes=a.notes, has_pack=bool(a.pack_dir))
        )
    return list(columns.values())
