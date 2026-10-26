"""The daily run: every source → DB → classify → score."""

from __future__ import annotations

from pydantic import BaseModel, computed_field

from jobgent.classify import classify_jobs
from jobgent.config import Settings
from jobgent.errors import MissingSecretError
from jobgent.ingest import IngestReport, run_fetch
from jobgent.profile.models import Profile
from jobgent.score import score_jobs
from jobgent.service import Services
from jobgent.sources.apify import ApifyLinkedInSource
from jobgent.sources.ats import ATSSource
from jobgent.sources.base import Source
from jobgent.sources.linkedin_guest import LinkedInGuestSource
from jobgent.sources.companies import Company, load_companies


class SourceSummary(BaseModel):
    source: str
    count: int
    error: str | None = None


class FetchSummary(BaseModel):
    sources: list[SourceSummary]
    ingest: IngestReport
    skipped: list[str]
    classified: int
    scored: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failed(self) -> list[str]:
        return [s.source for s in self.sources if s.error]


def linkedin_reason(settings: Settings) -> str:
    if settings.linkedin_mode == "off":
        return "JOBGENT_LINKEDIN=off"
    if settings.linkedin_mode == "apify" and not settings.apify_token:
        return "JOBGENT_LINKEDIN=apify but APIFY_TOKEN is not set"
    return "unknown JOBGENT_LINKEDIN value: " + settings.linkedin_mode


def linkedin_source(settings: Settings, keywords: list[str], locations: list[str], max_per_query: int = 100) -> Source | None:
    """auto: Apify when a token is set (paid, robust), else LinkedIn's free guest search (low volume)."""
    mode = settings.linkedin_mode
    if mode in ("apify", "auto") and settings.apify_token:
        return ApifyLinkedInSource(token=settings.apify_token, keywords=keywords, locations=locations, max_per_query=max_per_query, actor=settings.linkedin_actor)
    if mode in ("guest", "auto"):
        return LinkedInGuestSource(keywords=keywords, locations=locations, max_pages=max(1, max_per_query // 10))
    return None


def build_sources(settings: Settings, profile: Profile, companies: list[Company]) -> tuple[list[Source], list[str]]:
    sources: list[Source] = []
    skipped: list[str] = []
    li = linkedin_source(settings, profile.search.keywords, profile.search.locations)
    if li is None:
        skipped.append(f"linkedin: off ({linkedin_reason(settings)})")
    else:
        sources.append(li)
    sources.extend(ATSSource(c) for c in companies)
    return sources, skipped


def fetch_all(services: Services, classify: bool = True, score: bool = True) -> FetchSummary:
    profile = services.store.load()
    companies = load_companies(services.settings.companies_file)
    sources, skipped = build_sources(services.settings, profile, companies)
    with services.sessionmaker() as session, services.http_client_factory() as client:
        report = run_fetch(session, sources, client)
        classified = scored = 0
        if classify:
            try:
                llm = services.llm_factory()
            except MissingSecretError as e:
                skipped.append(f"classify/score: {e.name} not set, jobs saved but not classified or scored")
            else:
                classified = classify_jobs(session, llm, services.settings.fast_model)
                if score:
                    scored = score_jobs(session, llm, services.settings.fast_model, profile)
    return FetchSummary(
        sources=[SourceSummary(source=r.source, count=len(r.jobs), error=r.error) for r in report.results],
        ingest=report.ingest,
        skipped=skipped,
        classified=classified,
        scored=scored,
    )
