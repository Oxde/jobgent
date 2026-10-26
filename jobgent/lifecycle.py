"""Application history: undoable status changes, the furthest stage reached, notes and interview dates."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Application, ApplicationEvent, Status
from jobgent.errors import JobgentError

STAGE_ORDER = ["new", "liked", "pack_ready", "applied", "interview", "offer"]


def further(a: str | None, b: str) -> str:
    """The later of two stages; rejected / skipped never move the furthest stage."""
    if b not in STAGE_ORDER:
        return a or "new"
    if a is None or a not in STAGE_ORDER:
        return b
    return b if STAGE_ORDER.index(b) > STAGE_ORDER.index(a) else a


def record_status(session: Session, app: Application, new: Status) -> None:
    session.add(ApplicationEvent(
        job_id=app.job_id, kind="status", from_status=app.status.value if app.status else None, to_status=new.value,
        prev_furthest=app.furthest_stage, prev_applied_at=app.applied_at, text=f"Moved to {new.value.replace('_', ' ')}",
    ))
    app.furthest_stage = further(app.furthest_stage, new.value)


def undo_status(session: Session, job_id: int) -> Application:
    event = session.scalar(
        select(ApplicationEvent).where(ApplicationEvent.job_id == job_id, ApplicationEvent.kind == "status").order_by(ApplicationEvent.id.desc())
    )
    app = session.scalar(select(Application).where(Application.job_id == job_id))
    if event is None or app is None or event.from_status is None:
        raise JobgentError("Nothing to undo for this application.")
    app.status = Status(event.from_status)
    app.furthest_stage = event.prev_furthest
    app.applied_at = event.prev_applied_at
    session.delete(event)
    session.commit()
    return app


def add_note(session: Session, job_id: int, text: str) -> None:
    session.add(ApplicationEvent(job_id=job_id, kind="note", text=text))
    session.commit()


def set_interview(session: Session, job_id: int, at: datetime) -> Application:
    app = session.scalar(select(Application).where(Application.job_id == job_id))
    if app is None:
        raise JobgentError(f"No application for job {job_id}.")
    app.interview_at = at
    session.add(ApplicationEvent(job_id=job_id, kind="interview", text=f"Interview on {at:%a %d %b, %H:%M}"))
    session.commit()
    return app


class TimelineItem(BaseModel):
    kind: str
    text: str
    at: datetime


def timeline(session: Session, job_id: int) -> list[TimelineItem]:
    events = session.scalars(select(ApplicationEvent).where(ApplicationEvent.job_id == job_id).order_by(ApplicationEvent.id))
    return [TimelineItem(kind=e.kind, text=e.text, at=e.at) for e in events]
