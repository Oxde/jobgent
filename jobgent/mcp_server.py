"""MCP server: the primary interface. An agent drives the whole loop through these tools."""


import functools
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import ParamSpec, TypeVar

import anyio
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from jobgent.errors import JobgentError

from jobgent.classify import classify_jobs
from jobgent.db import Status
from jobgent.fetch import FetchSummary, fetch_all
from jobgent.pack.create import PackResult, create_pack, load_pack
from jobgent.guides import cv_writing_guide
from jobgent.pack.pdf import html_to_pdf
from jobgent.pack.render import render_cv_html
from jobgent.pack.tailor import general_cv
from jobgent.profile.models import Profile
from jobgent.profile.store import outline
from jobgent.score import score_job
from jobgent.search import SearchResult, search_jobs
from jobgent.service import Services, build_services
from jobgent.sources.manual import add_job_from_text, add_job_from_url
from jobgent.tracker import WeeklyStats, set_status, weekly_stats
from jobgent.views import JobDetail, JobSummary, detail, get_job, list_applications, list_jobs


P = ParamSpec("P")
R = TypeVar("R")

_PASS_THROUGH = (JobgentError, ValueError, KeyError, FileNotFoundError)


def surface_errors(fn: Callable[P, R]) -> Callable[P, R]:
    """fastmcp hides exception text from the client; our messages are the whole point, so re-raise as ToolError."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except _PASS_THROUGH as e:
            raise ToolError(str(e)) from e

    return wrapper


def in_thread(fn: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    """Slow, blocking work (HTTP, LLM calls, Chromium) runs in a worker thread so the stdio loop stays alive
    and sync Playwright is legal."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await anyio.to_thread.run_sync(functools.partial(surface_errors(fn), *args, **kwargs))

    return wrapper


def build_mcp(services: Services) -> FastMCP:
    mcp = FastMCP(
        "jobgent",
        instructions=(
            "Jobgent finds internships in the Netherlands, scores them against the user's profile, "
            "and prepares a tailored CV + cover letter per job. The user reviews and submits every application "
            "themselves. Typical loop: profile_get (fix with profile_update, then profile_set_verified) → "
            "jobs_fetch → jobs_list → job_get → pack_create → the user applies → application_set_status(applied)."
        ),
    )

    @mcp.tool()
    @surface_errors
    def profile_get() -> Profile:
        """The user's knowledge base (profile.yaml): facts, preferences and search settings. Read this first."""
        return services.store.load()

    @mcp.tool()
    @surface_errors
    def profile_update(path: str, value: str) -> Profile:
        """Change one field by dotted path, e.g. 'preferences.weekly_goal' = '12', 'search.keywords' = '[data intern, AI intern]',
        'education[0].period' = '2023 – 2027'. Text fields are stored as given; numbers, lists and booleans are parsed from YAML."""
        return services.store.update(path, value)

    @mcp.tool()
    @surface_errors
    def profile_add_item(section: str, item: dict[str, object]) -> Profile:
        """Append one entry to a list section: experience {company, title, period, bullets[]}, education {institution,
        degree, period, gpa, details}, projects {name, description, tech[], link}, skills {name, evidence},
        languages {name, level}. Only add facts the user told you."""
        return services.store.append(section, item)

    @mcp.tool()
    @surface_errors
    def profile_remove_item(section: str, index: int) -> Profile:
        """Remove entry `index` (0-based) from a list section. Check cv_outline for indexes first."""
        return services.store.remove(section, index)

    @mcp.tool(name="cv_writing_guide")
    @surface_errors
    def cv_writing_guide_tool() -> str:
        """Read this BEFORE writing or tailoring any CV text: ATS rules, structure, bullet formula, the user's own
        tailoring pattern, cover-letter rules. Never invent facts."""
        return cv_writing_guide()

    @mcp.tool()
    @surface_errors
    def cv_outline() -> str:
        """The whole CV/profile as `path: value` lines. Use the paths with profile_update to change any line,
        e.g. `experience[0].bullets[1]`. The web app at /me shows the result live."""
        return outline(services.store.load())

    @mcp.tool()
    @in_thread
    def cv_export_pdf(template: str | None = None) -> str:
        """Render the general (untailored) CV to an A4 PDF and return its path. Template ids: see profile_get preferences
        or the web app; default is the user's chosen one."""
        profile = services.store.load()
        tid = template or profile.preferences.template
        html = render_cv_html(profile, general_cv(profile), services.store.master_cv_path(), tid)
        out = services.settings.home / "cv" / f"cv-{tid}.pdf"
        pages = html_to_pdf(html, out, fit=True)
        return f"{out} ({pages} page{'s' if pages != 1 else ''})"

    @mcp.tool()
    @surface_errors
    def profile_set_verified(verified: bool) -> Profile:
        """Mark the profile as reviewed by the user. pack_create refuses to run while it is false."""
        return services.store.update("verified", verified)

    @mcp.tool()
    @surface_errors
    def profile_import_jobkiller(json_path: str) -> Profile:
        """Bootstrap the profile from a JobKiller user_info .json or a CV .html made by JobKiller. Leaves verified=false."""
        return services.store.import_any(Path(json_path).expanduser())

    @mcp.tool()
    @surface_errors
    def profile_get_voice() -> str:
        """The writing-style guide used for cover letters."""
        return services.store.voice()

    @mcp.tool()
    @surface_errors
    def profile_set_voice(text: str) -> str:
        """Replace the writing-style guide for cover letters."""
        services.store.set_voice(text)
        return services.store.voice()

    @mcp.tool()
    @surface_errors
    def profile_notes_append(text: str) -> str:
        """Append raw notes from the user (onboarding answers, voice-note transcripts). Kept verbatim in notes.md."""
        services.store.notes_append(text)
        return "ok"

    @mcp.tool()
    @surface_errors
    def profile_set_master_cv(html: str) -> str:
        """Set a custom CV template (Jinja2 HTML using personal, cv, languages). Default template is used otherwise."""
        services.store.set_master_cv(html)
        return str(services.store.cv_path)

    @mcp.tool()
    @in_thread
    def jobs_fetch(classify: bool = True, score: bool = True) -> FetchSummary:
        """Run every job source (company boards, LinkedIn via Apify if configured), then classify and score new jobs.
        Check `skipped` and each result's `error`: a source can fail without stopping the others."""
        return fetch_all(services, classify=classify, score=score)

    @mcp.tool()
    @in_thread
    def jobs_search(query: str, location: str = "Amsterdam", limit: int = 30, use_linkedin: bool = True) -> SearchResult:
        """Search internships now: runs a LinkedIn search for `query` in `location` (via Apify, if configured), saves what
        it finds, then returns matching internships from everything saved (company boards included), best first.
        Example: query="AI engineering intern", location="Amsterdam". Check `source_error` if LinkedIn failed."""
        return search_jobs(services, query, location, limit, use_linkedin)

    @mcp.tool()
    @surface_errors
    def jobs_list(min_score: int = 0, status: str | None = None, source: str | None = None, limit: int = 30) -> list[JobSummary]:
        """The feed: internships in English, no Dutch required, sorted by match score. Skipped/rejected are hidden unless status is given."""
        with services.sessionmaker() as s:
            return list_jobs(s, services.store.load().search, min_score, status, source, limit)

    @mcp.tool()
    @surface_errors
    def job_get(job_id: int) -> JobDetail:
        """Full posting plus score reasons, gaps and classification."""
        with services.sessionmaker() as s:
            return detail(get_job(s, job_id))

    @mcp.tool()
    @in_thread
    def job_add(url: str | None = None, text: str | None = None) -> JobDetail:
        """Add a posting by URL or pasted text (for anything the search missed, e.g. a LinkedIn link). Classifies and scores it."""
        if not url and not text:
            raise ValueError("Give url or text.")
        llm = services.llm_factory()
        profile = services.store.load()
        with services.sessionmaker() as s:
            if url and not text:
                with services.http_client_factory() as client:
                    job = add_job_from_url(s, llm, services.settings.fast_model, client, url)
            else:
                job = add_job_from_text(s, llm, services.settings.fast_model, text or "", url)
            classify_jobs(s, llm, services.settings.fast_model, job_ids=[job.id])
            s.refresh(job)
            if job.is_internship and job.language in profile.search.languages and not job.dutch_required:
                score_job(s, llm, services.settings.fast_model, profile, job)
            return detail(job)

    @mcp.tool()
    @in_thread
    def job_score(job_id: int) -> JobDetail:
        """Re-score one job against the current profile."""
        llm = services.llm_factory()
        profile = services.store.load()
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            score_job(s, llm, services.settings.fast_model, profile, job)
            return detail(job)

    @mcp.tool()
    @in_thread
    def pack_create(job_id: int) -> PackResult:
        """Generate the application pack: tailored one-page A4 CV (PDF + HTML), cover letter, and how to apply.
        Every claim is checked against the profile; fails loudly if anything unsupported slips in."""
        with services.sessionmaker() as s:
            return create_pack(services.settings, s, services.llm_factory(), services.store, job_id)

    @mcp.tool()
    @surface_errors
    def pack_get(job_id: int) -> PackResult:
        """Paths and summary of an existing pack."""
        with services.sessionmaker() as s:
            return load_pack(services.settings, get_job(s, job_id))

    @mcp.tool()
    @surface_errors
    def application_set_status(job_id: int, status: str, notes: str | None = None) -> JobSummary:
        """Track progress. status: new, liked, pack_ready, applied, interview, offer, rejected, skipped."""
        with services.sessionmaker() as s:
            set_status(s, job_id, Status(status), notes)
            return detail(get_job(s, job_id))

    @mcp.tool()
    @surface_errors
    def applications_list(status: str | None = None) -> list[JobSummary]:
        """Everything with a status other than new, most recently updated first."""
        with services.sessionmaker() as s:
            return list_applications(s, status)

    @mcp.tool()
    @surface_errors
    def stats() -> WeeklyStats:
        """Applications sent this week versus the weekly goal, plus counts per status."""
        with services.sessionmaker() as s:
            return weekly_stats(s, services.store.load().preferences.weekly_goal)

    return mcp


def main() -> None:
    build_mcp(build_services()).run()


if __name__ == "__main__":
    main()
