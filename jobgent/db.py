"""SQLite schema: jobs, matches, applications."""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, create_engine
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

    match: Mapped[Match | None] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")
    application: Mapped[Application | None] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


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


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.new)
    pack_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    job: Mapped[Job] = relationship(back_populates="application")


def open_db(db_path: Path) -> sessionmaker[Session]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
