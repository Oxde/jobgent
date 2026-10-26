"""Is the posting still open? Checked before scoring and before writing a pack."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

import httpx
from sqlalchemy.orm import Session

from jobgent.db import Job
from jobgent.sources.manual import assert_public_http_url
from jobgent.errors import SourceError

Liveness = Literal["open", "closed", "unknown"]

_CLOSED = re.compile(
    r"(no longer accepting applications|no longer available|job (has )?expired|position has been filled|"
    r"this (job|vacancy|position) (is )?(closed|no longer)|vacature is (gesloten|niet meer beschikbaar)|"
    r"we are not accepting applications)",
    re.IGNORECASE,
)


def check_liveness(job: Job, client: httpx.Client) -> Liveness:
    """404/410 or closed wording = closed. Rate limits and server errors = unknown, never closed."""
    if not job.url:
        return "unknown"
    try:
        assert_public_http_url(job.url)
        resp = client.get(job.url, timeout=20, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Jobgent)"})
    except (httpx.HTTPError, SourceError):
        return "unknown"
    if resp.status_code in (404, 410):
        return "closed"
    if resp.status_code >= 400:
        return "unknown"
    return "closed" if _CLOSED.search(resp.text[:200_000]) else "open"


def refresh_liveness(session: Session, job: Job, client: httpx.Client) -> Liveness:
    status = check_liveness(job, client)
    job.live_status = status
    job.live_checked_at = datetime.now()
    session.commit()
    return status
