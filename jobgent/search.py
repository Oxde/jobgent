"""Search on demand: run LinkedIn for one query now, then answer from everything saved."""

from __future__ import annotations

import re

from pydantic import BaseModel
from sqlalchemy import select

from jobgent.db import Job
from jobgent.ingest import run_fetch
from jobgent.service import Services
from jobgent.fetch import linkedin_reason, linkedin_source
from jobgent.views import JobSummary, list_jobs

_GENERIC = {"intern", "interns", "internship", "internships", "stage", "stagiair", "job", "jobs", "role", "position", "in", "for", "and", "the", "a"}


class SearchResult(BaseModel):
    query: str
    location: str
    fetched: int
    source_error: str | None
    jobs: list[JobSummary]


def search_jobs(services: Services, query: str, location: str, limit: int = 30, use_linkedin: bool = True) -> SearchResult:
    fetched = 0
    error: str | None = None
    fresh_ids: set[int] = set()
    settings = services.settings
    source = linkedin_source(settings, [query], [location], max_per_query=50) if use_linkedin else None
    if use_linkedin and source is None:
        error = f"linkedin: {linkedin_reason(settings)}; searched saved jobs only"
    elif source is not None:
        with services.sessionmaker() as s, services.http_client_factory() as client:
            report = run_fetch(s, [source], client)
            result = report.results[0]
            fetched, error = len(result.jobs), result.error
            ids = [j.external_id for j in result.jobs]
            if ids:
                fresh_ids = set(s.scalars(select(Job.id).where(Job.source == source.name, Job.external_id.in_(ids))))

    profile = services.store.load()
    search = profile.search.model_copy(update={"locations": [location]}) if location else profile.search
    words = [w for w in re.findall(r"[a-z0-9+#]+", query.lower()) if w not in _GENERIC]

    def matches(j: JobSummary) -> bool:
        title = j.title.lower()
        return j.id in fresh_ids or all(re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", title) for w in words)

    with services.sessionmaker() as s:
        rows = [j for j in list_jobs(s, search, limit=1000) if matches(j)]
    return SearchResult(query=query, location=location, fetched=fetched, source_error=error, jobs=rows[:limit])
