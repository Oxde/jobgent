"""Add one job by hand: from a URL or pasted text."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Job
from jobgent.errors import SourceError
from jobgent.ingest import dedupe_key
from jobgent.llm import LLM
from jobgent.sources.base import html_to_text

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


_MAX_REDIRECTS = 5


def assert_public_http_url(url: str) -> None:
    """Only public http(s) hosts may be fetched: never loopback, private, link-local or reserved addresses.
    Matters once the tool is hosted for other users (SSRF); harmless locally."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        raise SourceError(SOURCE, f"{url!r} is not a public http(s) URL. Paste the posting text instead.")
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SourceError(SOURCE, f"could not resolve {host}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]))
        if not ip.is_global:
            raise SourceError(SOURCE, f"{url!r} resolves to {ip}, not a public http(s) host. Paste the posting text instead.")


def safe_get(client: httpx.Client, url: str, timeout: float = 30) -> httpx.Response:
    """GET a public http(s) URL, following redirects by hand and re-checking every hop (no SSRF via redirects)."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        assert_public_http_url(current)
        try:
            resp = client.get(current, timeout=timeout, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (Jobgent)"})
        except httpx.HTTPError as e:
            raise SourceError(SOURCE, f"could not fetch {current}: {e}") from e
        if resp.is_redirect:
            location = resp.headers.get("Location")
            if not location:
                raise SourceError(SOURCE, f"redirect without Location from {current}")
            current = urljoin(current, location)
            continue
        return resp
    raise SourceError(SOURCE, f"too many redirects fetching {url}")


def add_job_from_url(session: Session, llm: LLM, model: str, client: httpx.Client, url: str) -> Job:
    resp = safe_get(client, url)
    if resp.status_code >= 300:
        raise SourceError(SOURCE, f"HTTP {resp.status_code} fetching {url}: {resp.text[:200]}. Paste the posting text instead.")
    return add_job_from_text(session, llm, model, text=html_to_text(resp.text), url=url)
