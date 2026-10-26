"""LinkedIn's public guest job search: no login, no paid service. Low volume only (LinkedIn's terms do not
allow scraping); backs off on 429/5xx and stops with a clear error instead of hammering."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from html import unescape

import httpx

from jobgent.errors import SourceError
from jobgent.sources.apify import linkedin_place
from jobgent.sources.base import RawJob, html_to_text

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}
_CARD = re.compile(r'data-entity-urn="urn:li:jobPosting:(\d+)"(.*?)</li>', re.S)
_CLOSED = re.compile(r"no longer accepting applications", re.I)
PAGE_SIZE = 10


def _field(pattern: str, html: str) -> str:
    m = re.search(pattern, html, re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()) if m else ""


class LinkedInGuestSource:
    name = "linkedin"

    def __init__(
        self,
        keywords: list[str],
        locations: list[str],
        max_pages: int = 3,
        days: int = 30,
        fetch_details: bool = True,
        max_details: int = 60,
        delay: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.keywords, self.locations = keywords, locations
        self.max_pages, self.days = max_pages, days
        self.fetch_details, self.max_details = fetch_details, max_details
        self.delay, self.sleep = delay, sleep

    def _get(self, client: httpx.Client, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        wait = 0.5
        for _ in range(5):
            try:
                resp = client.get(url, params=params, headers=_HEADERS, timeout=30, follow_redirects=True)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"request failed for {url}: {e}") from e
            if resp.status_code == 429 or resp.status_code >= 500:
                self.sleep(wait)
                wait = min(wait * 2, 8.0)
                continue
            return resp
        raise SourceError(self.name, f"LinkedIn kept answering {resp.status_code} (rate limited) for {url}; try again later or use Apify.")

    def _search(self, client: httpx.Client, keyword: str, location: str) -> list[RawJob]:
        jobs: list[RawJob] = []
        for page in range(self.max_pages):
            params = {"keywords": keyword, "location": linkedin_place(location), "f_TPR": f"r{self.days * 86400}", "start": str(page * PAGE_SIZE)}
            resp = self._get(client, SEARCH_URL, params)
            if resp.status_code >= 400:
                raise SourceError(self.name, f"HTTP {resp.status_code} from LinkedIn guest search: {resp.text[:120]}")
            cards = _CARD.findall(resp.text)
            for job_id, card in cards:
                link = _field(r'class="base-card__full-link[^"]*"\s+href="([^"]+)"', card) or re.search(r'href="([^"]+/jobs/view/[^"]+)"', card)
                href = link if isinstance(link, str) else (link.group(1) if link else "")
                posted = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', card)
                jobs.append(RawJob(
                    source=self.name,
                    external_id=job_id,
                    url=unescape(href).split("?")[0],
                    title=_field(r'class="base-search-card__title">(.*?)</h3>', card),
                    company=_field(r'class="base-search-card__subtitle">(.*?)</h4>', card),
                    location=_field(r'class="job-search-card__location">(.*?)</span>', card) or None,
                    description="",
                    posted_at=datetime.fromisoformat(posted.group(1)) if posted else None,
                ))
            if len(cards) < PAGE_SIZE:
                break
            self.sleep(self.delay)
        return jobs

    def fetch(self, client: httpx.Client) -> list[RawJob]:
        found: dict[str, RawJob] = {}
        for keyword in self.keywords:
            for location in self.locations:
                for job in self._search(client, keyword, location):
                    found.setdefault(job.external_id, job)
                self.sleep(self.delay)
        if not self.fetch_details:
            return list(found.values())
        kept: list[RawJob] = []
        for i, job in enumerate(found.values()):
            if i >= self.max_details:
                kept.append(job)  # description left empty; add or open it later
                continue
            resp = self._get(client, DETAIL_URL.format(id=job.external_id))
            if resp.status_code < 400:
                if _CLOSED.search(resp.text):
                    continue
                m = re.search(r'class="description__text[^"]*">(.*?)</section>', resp.text, re.S)
                job.description = html_to_text(m.group(1)) if m else ""
            kept.append(job)
            self.sleep(self.delay)
        return kept
