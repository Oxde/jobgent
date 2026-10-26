"""Application status per job and the weekly goal."""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from stageone.db import Application, Job, Status
from stageone.errors import StageOneError


class WeeklyStats(BaseModel):
    applied_this_week: int
    goal: int
    by_status: dict[str, int]


def get_or_create_application(session: Session, job_id: int) -> Application:
    app = session.scalar(select(Application).where(Application.job_id == job_id))
    if app is None:
        if session.get(Job, job_id) is None:
            raise StageOneError(f"No job with id {job_id}. Use jobs_list to find ids.")
        app = Application(job_id=job_id)
        session.add(app)
        session.commit()
    return app


def set_status(session: Session, job_id: int, status: Status, notes: str | None) -> Application:
    app = get_or_create_application(session, job_id)
    app.status = status
    if status == Status.applied and app.applied_at is None:
        app.applied_at = datetime.now()
    if notes is not None:
        app.notes = notes
    session.commit()
    return app


def week_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def weekly_stats(session: Session, goal: int) -> WeeklyStats:
    apps = list(session.scalars(select(Application)))
    start = week_start()
    applied = sum(1 for a in apps if a.applied_at is not None and a.applied_at >= start)
    by_status: dict[str, int] = {}
    for a in apps:
        by_status[a.status.value] = by_status.get(a.status.value, 0) + 1
    return WeeklyStats(applied_this_week=applied, goal=goal, by_status=by_status)
