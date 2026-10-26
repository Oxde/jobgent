"""Run sources, store jobs, drop duplicates across sources."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Job
from jobgent.sources.base import RawJob, Source, SourceResult

_NOISE = re.compile(
    r"\b(intern|internship|internships|stage|stagiair|stagiaire|m/f/d|m/w/d|f/m/x|m/v/x|2026|2027)\b"
)
_PUNCT = re.compile(r"[^\w\s]")


def _norm(text: str) -> str:
    text = _NOISE.sub(" ", text.lower())
    text = _PUNCT.sub(" ", text)
    return " ".join(w for w in text.split() if len(w) > 1)


def city(location: str | None) -> str:
    if not location:
        return ""
    first = location.split(",")[0].split(" - ")[0]
    return " ".join(w for w in _PUNCT.sub(" ", first.lower()).split() if len(w) > 1)


def dedupe_key(company: str, title: str, location: str | None = None) -> str:
    return f"{_norm(company)}|{_norm(title)}|{city(location)}"


class IngestReport(BaseModel):
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0


class FetchReport(BaseModel):
    results: list[SourceResult]
    ingest: IngestReport

    @property
    def failed(self) -> list[str]:
        return [r.source for r in self.results if r.error]


def _is_ats(source: str) -> bool:
    return source.startswith("ats:")


def upsert_jobs(session: Session, jobs: Iterable[RawJob]) -> IngestReport:
    report = IngestReport()
    now = datetime.now()
    for raw in jobs:
        existing = session.scalar(select(Job).where(Job.source == raw.source, Job.external_id == raw.external_id))
        if existing is not None:
            existing.description = raw.description
            existing.posted_at = raw.posted_at
            existing.url = raw.url
            existing.fetched_at = now
            report.updated += 1
            continue
        key = dedupe_key(raw.company, raw.title, raw.location)
        twin = session.scalar(select(Job).where(Job.dedupe_key == key))
        if twin is not None:
            report.duplicates += 1
            if _is_ats(raw.source) and not _is_ats(twin.source):
                twin.source = raw.source
                twin.external_id = raw.external_id
                twin.url = raw.url
                twin.description = raw.description
                twin.posted_at = raw.posted_at
                twin.fetched_at = now
            continue
        session.add(
            Job(
                source=raw.source,
                external_id=raw.external_id,
                url=raw.url,
                title=raw.title,
                company=raw.company,
                location=raw.location,
                description=raw.description,
                posted_at=raw.posted_at,
                fetched_at=now,
                dedupe_key=key,
            )
        )
        report.inserted += 1
    session.commit()
    return report


def run_fetch(session: Session, sources: list[Source], client: httpx.Client) -> FetchReport:
    results: list[SourceResult] = []
    for source in sources:
        try:
            jobs = source.fetch(client)
        except Exception as e:  # noqa: BLE001 — one broken source must not stop the others
            results.append(SourceResult(source=source.name, jobs=[], error=f"{type(e).__name__}: {e}"))
            continue
        results.append(SourceResult(source=source.name, jobs=jobs))
    # ATS first so cross-source duplicates resolve to the company's own posting.
    ordered = sorted(results, key=lambda r: not _is_ats(r.source))
    ingest = upsert_jobs(session, (j for r in ordered for j in r.jobs))
    return FetchReport(results=results, ingest=ingest)
