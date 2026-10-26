"""Read models for Home and Applications: what needs doing, grouped by stage."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Application, ApplicationEvent, Job, Status
from jobgent.profile.models import Profile
from jobgent.profile.store import ChecklistItem, completeness
from jobgent.tracker import WeeklyStats, weekly_stats
from jobgent.views import JobSummary, list_jobs, summary

NO_ANSWER_DAYS = 14
FOLLOW_UP_AFTER_DAYS = 7
MAX_FOLLOW_UPS = 2
ActionKind = Literal["offer", "interview_soon", "send", "make_pack", "follow_up"]
_DEADLINE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%d-%m-%Y", "%d/%m/%Y")


class ActionItem(BaseModel):
    kind: ActionKind
    job: JobSummary
    days_since: int | None
    text: str


class Funnel(BaseModel):
    sent: int
    heard_back: int
    interview: int
    offer: int
    response_rate: int


class WeekCount(BaseModel):
    week_start: date
    sent: int


class HomeData(BaseModel):
    top_matches: list[JobSummary]
    actions: list[ActionItem]
    stats: WeeklyStats
    checklist: list[ChecklistItem]
    weeks_left: int
    start_from: str
    funnel: Funnel | None = None
    weekly: list[WeekCount] = []


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


def parse_deadline(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _deadline_note(job_deadline: str | None) -> str:
    d = parse_deadline(job_deadline)
    if d is None:
        return ""
    days = (d - date.today()).days
    if days < 0:
        return " The deadline has passed."
    return " Closes today." if days == 0 else f" Closes in {days} day{'s' if days != 1 else ''}."


def worth_a_look(session: Session) -> list[ActionItem]:
    """What needs the student now, most urgent first."""
    now = datetime.now()
    apps = list(session.scalars(select(Application).join(Job)))
    followups: dict[int, list[datetime]] = {}
    for e in session.scalars(select(ApplicationEvent).where(ApplicationEvent.kind == "followup")):
        followups.setdefault(e.job_id, []).append(e.at)
    items: list[tuple[int, int, ActionItem]] = []
    for a in apps:
        job = summary(a.job)
        deadline = parse_deadline(a.job.deadline)
        due = (deadline - date.today()).days if deadline else 9999
        note = _deadline_note(a.job.deadline)
        if a.status == Status.offer:
            items.append((0, 0, ActionItem(kind="offer", job=job, days_since=None, text="Offer waiting for your decision.")))
        elif a.status == Status.interview and a.interview_at and now <= a.interview_at <= now + timedelta(days=2):
            when = "today" if a.interview_at.date() == now.date() else "tomorrow" if a.interview_at.date() == (now + timedelta(days=1)).date() else a.interview_at.strftime("%A")
            items.append((1, 0, ActionItem(kind="interview_soon", job=job, days_since=None, text=f"Interview {when} at {a.interview_at:%H:%M}. Re-read your letter and the posting first.")))
        elif a.status == Status.pack_ready:
            items.append((2, due, ActionItem(kind="send", job=job, days_since=None, text=("Pack ready, not sent." + note).replace("Closes", "closes").replace(". closes", ", closes"))))
        elif a.status == Status.liked:
            items.append((3, due, ActionItem(kind="make_pack", job=job, days_since=None, text=("Saved, no pack yet." + note).replace(". Closes", ", closes"))))
        elif a.status == Status.applied and a.applied_at:
            sent = followups.get(a.job_id, [])
            last = max([a.applied_at, *sent])
            days = (now - a.applied_at).days
            if len(sent) < MAX_FOLLOW_UPS and (now - last).days >= FOLLOW_UP_AFTER_DAYS:
                items.append((4, -days, ActionItem(kind="follow_up", job=job, days_since=days, text=f"No answer after {days} days: send a short follow-up ({len(sent) + 1} of {MAX_FOLLOW_UPS}).")))
    return [i for _, _, i in sorted(items, key=lambda t: (t[0], t[1]))]


def funnel(session: Session) -> Funnel:
    apps = list(session.scalars(select(Application)))
    order = {"applied": 1, "interview": 2, "offer": 3}
    sent = [a for a in apps if order.get(a.furthest_stage or "", 0) >= 1 or a.applied_at is not None]
    interview = [a for a in sent if order.get(a.furthest_stage or "", 0) >= 2]
    offer = [a for a in sent if order.get(a.furthest_stage or "", 0) >= 3]
    heard = [a for a in sent if a in interview or a.status == Status.rejected]
    rate = round(100 * len(heard) / len(sent)) if sent else 0
    return Funnel(sent=len(sent), heard_back=len(heard), interview=len(interview), offer=len(offer), response_rate=rate)


def weekly_sent(session: Session, weeks: int = 8) -> list[WeekCount]:
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    starts = [this_monday - timedelta(weeks=w) for w in range(weeks - 1, -1, -1)]
    counts = {s: 0 for s in starts}
    for a in session.scalars(select(Application).where(Application.applied_at.is_not(None))):
        assert a.applied_at is not None
        d = a.applied_at.date()
        monday = d - timedelta(days=d.weekday())
        if monday in counts:
            counts[monday] += 1
    return [WeekCount(week_start=s, sent=counts[s]) for s in starts]


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
        actions=worth_a_look(session),
        stats=weekly_stats(session, profile.preferences.weekly_goal),
        checklist=completeness(profile),
        weeks_left=weeks_left,
        start_from=start.strftime("%B %Y"),
        funnel=funnel(session),
        weekly=weekly_sent(session),
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
