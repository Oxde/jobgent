"""Adapters for the public JSON job feeds of common applicant-tracking systems."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import httpx

from jobgent.errors import SourceError
from jobgent.sources.base import RawJob, html_to_text
from jobgent.sources.companies import Company

JsonDict = dict[str, object]


def _s(d: JsonDict, key: str) -> str:
    v = d.get(key)
    return "" if v is None else str(v)


def _dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC).replace(tzinfo=None)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _loc(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        d = cast(JsonDict, value)
        parts = [_s(d, k) for k in ("name", "city", "country") if _s(d, k)]
        return ", ".join(parts) or None
    return str(value)


def _list(data: object, key: str | None) -> list[JsonDict]:
    if key is None:
        return cast(list[JsonDict], data)
    return cast(list[JsonDict], cast(JsonDict, data).get(key, []))


class _Spec:
    def __init__(
        self,
        url: Callable[[str], str],
        items: Callable[[object], list[JsonDict]],
        job: Callable[[JsonDict], tuple[str, str, str, str | None, str, datetime | None]],
    ) -> None:
        self.url = url
        self.items = items
        self.job = job


SPECS: dict[str, _Spec] = {
    "greenhouse": _Spec(
        lambda b: f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=true",
        lambda d: _list(d, "jobs"),
        lambda j: (_s(j, "id"), _s(j, "absolute_url"), _s(j, "title"), _loc(j.get("location")), _s(j, "content"), _dt(j.get("updated_at"))),
    ),
    "lever": _Spec(
        lambda b: f"https://api.lever.co/v0/postings/{b}?mode=json",
        lambda d: _list(d, None),
        lambda j: (_s(j, "id"), _s(j, "hostedUrl"), _s(j, "text"), _loc(cast(JsonDict, j.get("categories") or {}).get("location")), _s(j, "description"), _dt(j.get("createdAt"))),
    ),
    "recruitee": _Spec(
        lambda b: f"https://{b}.recruitee.com/api/offers/",
        lambda d: _list(d, "offers"),
        lambda j: (_s(j, "id"), _s(j, "careers_url"), _s(j, "title"), _loc(j.get("location")), _s(j, "description") + "\n" + _s(j, "requirements"), _dt(j.get("created_at"))),
    ),
    "homerun": _Spec(
        lambda b: f"https://{b}.homerun.co/api/v1/jobs",
        lambda d: _list(d, "data"),
        lambda j: (_s(j, "id"), _s(j, "url"), _s(j, "title"), _loc(j.get("location")), _s(j, "description"), _dt(j.get("published_at"))),
    ),
    "ashby": _Spec(
        lambda b: f"https://api.ashbyhq.com/posting-api/job-board/{b}",
        lambda d: _list(d, "jobs"),
        lambda j: (_s(j, "id"), _s(j, "jobUrl"), _s(j, "title"), _loc(j.get("location")), _s(j, "descriptionHtml"), _dt(j.get("publishedAt"))),
    ),
    "workable": _Spec(
        lambda b: f"https://apply.workable.com/api/v1/widget/accounts/{b}",
        lambda d: _list(d, "results"),
        lambda j: (_s(j, "shortcode") or _s(j, "id"), _s(j, "url"), _s(j, "title"), _loc(j.get("location")), _s(j, "description"), _dt(j.get("published"))),
    ),
}


class ATSSource:
    def __init__(self, company: Company) -> None:
        self.company = company
        self.name = f"ats:{company.ats}:{company.board}"
        self.spec = SPECS[company.ats]

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        url = self.spec.url(self.company.board)
        try:
            resp = client.get(url, timeout=30, headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"request failed for {url}: {e}") from e
        if resp.status_code >= 300:
            body = " ".join(resp.text.split())[:120]
            raise SourceError(self.name, f"HTTP {resp.status_code} from {url}: {body}")
        try:
            items = self.spec.items(resp.json())
        except (ValueError, AttributeError, TypeError) as e:
            raise SourceError(self.name, f"unexpected JSON from {url}: {e}") from e
        jobs: list[RawJob] = []
        for item in items:
            external_id, job_url, title, location, html, posted_at = self.spec.job(item)
            if not title:
                continue
            jobs.append(
                RawJob(
                    source=self.name,
                    external_id=external_id,
                    url=job_url,
                    title=title,
                    company=self.company.name,
                    location=location,
                    description=html_to_text(html),
                    posted_at=posted_at,
                )
            )
        return jobs
