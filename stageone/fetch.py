"""The daily run: every source → DB → classify → score."""

from __future__ import annotations

from pydantic import BaseModel, computed_field

from stageone.classify import classify_jobs
from stageone.config import Settings
from stageone.errors import MissingSecretError
from stageone.ingest import IngestReport, run_fetch
from stageone.profile.models import Profile
from stageone.score import score_jobs
from stageone.service import Services
from stageone.sources.apify import ApifyLinkedInSource
from stageone.sources.ats import ATSSource
from stageone.sources.base import Source
from stageone.sources.companies import Company, load_companies


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


def build_sources(settings: Settings, profile: Profile, companies: list[Company]) -> tuple[list[Source], list[str]]:
    sources: list[Source] = []
    skipped: list[str] = []
    if settings.apify_token:
        sources.append(
            ApifyLinkedInSource(
                token=settings.apify_token,
                keywords=profile.search.keywords,
                locations=profile.search.locations,
                actor=settings.linkedin_actor,
            )
        )
    else:
        skipped.append("linkedin: APIFY_TOKEN not set, LinkedIn search skipped")
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
