"""SQLite schema: jobs, matches, applications."""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Status(enum.StrEnum):
    new = "new"
    liked = "liked"
    pack_ready = "pack_ready"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    skipped = "skipped"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    dedupe_key: Mapped[str] = mapped_column(String(512), index=True)
    in_region: Mapped[bool | None] = mapped_column(nullable=True)
    is_internship: Mapped[bool | None] = mapped_column(nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    dutch_required: Mapped[bool | None] = mapped_column(nullable=True)
    dutch_plus: Mapped[bool | None] = mapped_column(nullable=True)
    start_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    months: Mapped[int | None] = mapped_column(nullable=True)
    paid: Mapped[bool | None] = mapped_column(nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    live_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    live_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(64), nullable=True)

    match: Mapped[Match | None] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")
    application: Mapped[Application | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    evaluation: Mapped[Evaluation | None] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    total: Mapped[int]
    skills: Mapped[int]
    role: Mapped[int]
    lang_loc: Mapped[int]
    timing: Mapped[int]
    reasons: Mapped[list[str]] = mapped_column(JSON)
    gaps: Mapped[list[str]] = mapped_column(JSON)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    job: Mapped[Job] = relationship(back_populates="match")


class Evaluation(Base):
    """Gates, requirement table and verdict for one posting (see jobgent.evaluate)."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    gates: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    requirements: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    coverage: Mapped[int] = mapped_column(default=0)
    verdict: Mapped[str] = mapped_column(String(16))
    verdict_reason: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    deadline: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    dismissed: Mapped[bool] = mapped_column(default=False)

    job: Mapped[Job] = relationship(back_populates="evaluation")


class AgentRun(Base):
    """One run of the daily job agent."""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | done | failed
    step: Mapped[str] = mapped_column(String(64), default="")
    fetched: Mapped[int] = mapped_column(default=0)
    evaluated: Mapped[int] = mapped_column(default=0)
    queued: Mapped[int] = mapped_column(default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")


class ApplicationEvent(Base):
    """Status changes (with what to restore on undo), notes and interview dates, in order."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # status | note | interview | followup
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prev_furthest: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prev_applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Document(Base):
    """A pack document (cv / letter / email / followup) as editable units; see jobgent.documents."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("job_id", "kind", name="uq_document_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    kind: Mapped[str] = mapped_column(String(16))
    content: Mapped[dict[str, object]] = mapped_column(JSON)
    trimmed: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class DocumentVersion(Base):
    """Snapshot taken before every AI change (and before a restore), so it can be undone."""

    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    content: Mapped[dict[str, object]] = mapped_column(JSON)
    cause: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.new)
    pack_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    ai_note: Mapped[str] = mapped_column(Text, default="")  # "anything I should know?" for this application; sent to the AI
    tone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    furthest_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    interview_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    job: Mapped[Job] = relationship(back_populates="application")


def _add_missing_columns(engine: Engine) -> None:
    """Tiny forward-only migration: columns added to the models appear in existing tables.
    SQLite can only ADD COLUMN, so new columns must be nullable or have a default."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {column.type.compile(engine.dialect)}'
                if isinstance(column.type, JSON):
                    ddl += " DEFAULT '[]'"
                conn.execute(text(ddl))


def open_db(db_path: Path) -> sessionmaker[Session]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    _add_missing_columns(engine)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
