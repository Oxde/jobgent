"""LinkedIn public job search through an Apify actor. The user's LinkedIn account is never involved."""

from __future__ import annotations

import re
from datetime import datetime
from typing import cast

import httpx

from jobgent.config import DEFAULT_LINKEDIN_ACTOR
from jobgent.errors import SourceError
from jobgent.sources.base import RawJob, html_to_text

JsonDict = dict[str, object]
_JOB_ID = re.compile(r"/jobs/view/(\d+)")


def _first(d: JsonDict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v:
            return str(v)
    return ""


def _posted(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


class ApifyLinkedInSource:
    name = "linkedin"

    def __init__(
        self,
        token: str,
        keywords: list[str],
        locations: list[str],
        max_per_query: int = 100,
        actor: str = DEFAULT_LINKEDIN_ACTOR,
    ) -> None:
        self.token = token
        self.keywords = keywords
        self.locations = locations
        self.max_per_query = max_per_query
        self.actor = actor

    def _run(self, client: httpx.Client, keyword: str, location: str) -> list[JsonDict]:
        url = f"https://api.apify.com/v2/acts/{self.actor}/run-sync-get-dataset-items"
        payload: JsonDict = {
            "keywords": keyword,
            "location": location,
            "limitPerSource": self.max_per_query,
            "datePosted": "pastMonth",
            "scrapeCompany": False,
        }
        try:
            resp = client.post(url, headers={"Authorization": f"Bearer {self.token}"}, json=payload, timeout=300)
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"APIFY request failed ({keyword!r} in {location!r}): {e}") from e
        if resp.status_code >= 300:
            raise SourceError(
                self.name,
                f"APIFY actor {self.actor} returned HTTP {resp.status_code} for {keyword!r} in {location!r}: {resp.text[:200]}",
            )
        data = resp.json()
        if not isinstance(data, list):
            raise SourceError(self.name, f"APIFY returned non-list dataset: {str(data)[:200]}")
        return cast(list[JsonDict], data)

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        jobs: dict[str, RawJob] = {}
        for keyword in self.keywords:
            for location in self.locations:
                for item in self._run(client, keyword, location):
                    link = _first(item, "link", "url", "jobUrl", "applyUrl")
                    m = _JOB_ID.search(link)
                    external_id = m.group(1) if m else _first(item, "id", "jobId")
                    if not external_id or external_id in jobs:
                        continue
                    html = _first(item, "descriptionHtml", "description")
                    text = _first(item, "descriptionText") or html_to_text(html)
                    jobs[external_id] = RawJob(
                        source=self.name,
                        external_id=external_id,
                        url=link,
                        title=_first(item, "title", "jobTitle"),
                        company=_first(item, "companyName", "company"),
                        location=_first(item, "location") or None,
                        description=text,
                        posted_at=_posted(_first(item, "postedAt", "publishedAt", "postedDate")),
                    )
        return list(jobs.values())
