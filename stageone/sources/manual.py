"""Add one job by hand: from a URL or pasted text."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from stageone.db import Job
from stageone.errors import SourceError
from stageone.ingest import dedupe_key
from stageone.llm import LLM
from stageone.sources.base import html_to_text

_PROMPT = (Path(__file__).parent.parent / "prompts" / "extract_job.md").read_text()
SOURCE = "manual"


class ExtractedJob(BaseModel):
    title: str
    company: str
    location: str | None
    description: str
    posted_at: datetime | None


def _external_id(url: str | None, text: str) -> str:
    return hashlib.sha1((url or text).encode()).hexdigest()


def add_job_from_text(session: Session, llm: LLM, model: str, text: str, url: str | None) -> Job:
    external_id = _external_id(url, text)
    existing = session.scalar(select(Job).where(Job.source == SOURCE, Job.external_id == external_id))
    if existing is not None:
        return existing
    extracted = llm.complete_json(model=model, system=_PROMPT, user=text[:20000], schema=ExtractedJob, max_tokens=8192)
    job = Job(
        source=SOURCE,
        external_id=external_id,
        url=url or "",
        title=extracted.title,
        company=extracted.company,
        location=extracted.location,
        description=extracted.description,
        posted_at=extracted.posted_at,
        fetched_at=datetime.now(),
        dedupe_key=dedupe_key(extracted.company, extracted.title, extracted.location),
    )
    session.add(job)
    session.commit()
    return job


def add_job_from_url(session: Session, llm: LLM, model: str, client: httpx.Client, url: str) -> Job:
    try:
        resp = client.get(url, timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (StageOne)"})
    except httpx.HTTPError as e:
        raise SourceError(SOURCE, f"could not fetch {url}: {e}") from e
    if resp.status_code >= 300:
        raise SourceError(SOURCE, f"HTTP {resp.status_code} fetching {url}: {resp.text[:200]}. Paste the posting text instead.")
    return add_job_from_text(session, llm, model, text=html_to_text(resp.text), url=url)
