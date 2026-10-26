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
from jobgent.agent import QueueItem, agent_queue, run_agent
from jobgent.evaluate import EXTRACT_PROMPT, MAP_PROMPT, Extracted, Mapped, evaluate_job, finalize_evaluation, posting_text
from jobgent.gates import run_gates
from jobgent.insights import LearningGap, learning_gaps
from jobgent.interview import InterviewPrep, prepare_interview
from jobgent.fetch import FetchSummary, fetch_all
from jobgent.pack.create import PackResult, create_pack, finalize_pack, load_pack, requirement_lines
from jobgent.pack.letter import letter_instructions
from jobgent.guides import cv_writing_guide
from jobgent.pack.pdf import html_to_pdf
from jobgent.pack.render import render_cv_html
from jobgent.pack.tailor import TAILOR_PROMPT, TailoredCV, general_cv, job_text
from jobgent.profile.models import Profile
from jobgent.profile.store import outline
from jobgent.score import profile_for_prompt, score_job
from jobgent.search import SearchResult, search_jobs
from jobgent.service import Services, build_services
from jobgent.sources.manual import add_job_from_text, add_job_from_url
from jobgent.tracker import WeeklyStats, get_or_create_application, set_status, weekly_stats
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
            "jobs_fetch → jobs_list → job_get → pack_create → the user applies → application_set_status(applied). "
            "Agent mode: if Jobgent has no AI key (job_evaluate / pack_create fail with a missing-key error) or you prefer "
            "to write yourself, use evaluate_prompt → evaluate_submit and pack_prompt → pack_submit. You do the writing; "
            "Jobgent still runs the gates, decides coverage and the verdict, blocks invented numbers and banned phrases, "
            "and renders the one-page PDF. When a submit is refused, fix what the message names and submit again."
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

    @mcp.tool(name="agent_run")
    @in_thread
    def agent_run_tool(max_evaluate: int = 15, min_score: int = 65) -> dict[str, object]:
        """Run the job agent once: fetch new postings, score them, evaluate the best `max_evaluate` new ones (score ≥ min_score)
        and queue those worth applying to. Never applies or sends anything. Then call agent_queue."""
        run = run_agent(services, max_evaluate, min_score)
        return {k: getattr(run, k) for k in ("status", "fetched", "evaluated", "queued", "note")}

    @mcp.tool(name="agent_queue")
    @surface_errors
    def agent_queue_tool() -> list[QueueItem]:
        """Postings the agent recommends (apply first, then consider), with its reason and any red flags."""
        with services.sessionmaker() as s:
            return agent_queue(s)

    @mcp.tool(name="learning_gaps")
    @surface_errors
    def learning_gaps_tool() -> list[LearningGap]:
        """What to learn next: requirements the student lacks, weighted by importance and how often they cost a job.
        Skills already in the profile are excluded (those are CV-wording problems, not learning gaps)."""
        with services.sessionmaker() as s:
            return learning_gaps(s, services.store.load())

    @mcp.tool(name="interview_prep")
    @in_thread
    def interview_prep_tool(job_id: int, stage: str = "first round") -> InterviewPrep:
        """Interview prep for one application: likely questions, STAR stories from profile facts only, consistency
        reminders against the CV and letter that were sent, questions to ask, gaps to prepare."""
        profile = services.store.load()
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            gaps = [str(r.get("text")) for r in (job.evaluation.requirements if job.evaluation else []) if r.get("status") == "gap"]
            return prepare_interview(services.llm_factory(), services.settings.smart_model, profile, job, stage, gaps, "", "")

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
    def job_evaluate(job_id: int) -> dict[str, object]:
        """Full evaluation of one posting: checks it is still open, runs the gates (language, location, work rights,
        red flags, integrity), builds the requirement → evidence table (covered / partial / gap, decided by code) and
        returns a verdict apply / consider / skip with the reason. Use before pack_create."""
        profile = services.store.load()
        llm = services.llm_factory()
        with services.sessionmaker() as s, services.http_client_factory() as client:
            ev = evaluate_job(s, llm, services.settings.fast_model, profile, get_job(s, job_id), client)
            return {k: getattr(ev, k) for k in ("verdict", "verdict_reason", "summary", "deadline", "coverage", "gates", "requirements")}

    @mcp.tool()
    @surface_errors
    def evaluate_prompt(job_id: int) -> dict[str, object]:
        """Agent mode, step 1 of evaluation: everything you need to evaluate a posting with your own model.
        Runs the deterministic gates first; if one fails the job is skipped right away (done=true, no work for you).
        Otherwise follow `instructions`: extract the requirements (extracted_schema) from `posting` only, then map each
        to evidence in `profile` (mapped_schema, indexes into the profile lists), and call evaluate_submit."""
        profile = services.store.load()
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            gates = run_gates(job, profile)
            if any(g.status == "fail" for g in gates):
                ev = finalize_evaluation(s, profile, job, gates, None, None, None, "host-agent")
                return {"done": True, "verdict": ev.verdict, "verdict_reason": ev.verdict_reason, "gates": ev.gates}
            return {
                "done": False,
                "gates": [g.model_dump() for g in gates],
                "instructions": "## Step A: extract requirements\n" + EXTRACT_PROMPT + "\n\n## Step B: map requirements to evidence\n" + MAP_PROMPT,
                "posting": posting_text(job),
                "profile": profile_for_prompt(profile),
                "extracted_schema": Extracted.model_json_schema(),
                "mapped_schema": Mapped.model_json_schema(),
            }

    @mcp.tool()
    @surface_errors
    def evaluate_submit(job_id: int, extracted: Extracted, mapped: Mapped) -> dict[str, object]:
        """Agent mode, step 2 of evaluation: submit your extraction and mapping. Jobgent re-runs the gates, checks every
        evidence pointer against the profile (pointers to entries that do not exist count as gaps), resolves
        covered / partial / gap, and decides the verdict from coverage."""
        profile = services.store.load()
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            ev = finalize_evaluation(s, profile, job, run_gates(job, profile), extracted, mapped, None, "host-agent")
            return {k: getattr(ev, k) for k in ("verdict", "verdict_reason", "summary", "deadline", "coverage", "gates", "requirements")}

    @mcp.tool()
    @surface_errors
    def pack_prompt(job_id: int) -> dict[str, object]:
        """Agent mode, step 1 of the pack: everything you need to write the tailored CV and cover letter yourself.
        Write the CV as JSON matching cv_schema (cv_instructions), the letter as plain text (letter_instructions),
        then call pack_submit. Use only facts from `profile` and `facts`."""
        profile = services.store.load()
        if not profile.verified:
            raise JobgentError("Profile is not verified. Review it with the user, then call profile_set_verified(true).")
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            app = get_or_create_application(s, job.id)
            tone = app.tone or profile.preferences.tone
            s.commit()
            return {
                "cv_instructions": TAILOR_PROMPT,
                "letter_instructions": letter_instructions(services.store.voice(), tone),
                "tone": tone,
                "profile": profile_for_prompt(profile),
                "facts": profile.facts,
                "note": app.ai_note,
                "requirements": requirement_lines(job),
                "posting": job_text(job),
                "cv_schema": TailoredCV.model_json_schema(),
                "rules": [
                    "Never invent numbers, employers, tools or names: every number must appear in the profile or the posting, or the submit is refused.",
                    "The CV must fit one A4 page; if it does not, the submit is refused and you shorten it.",
                    "No cliches in the letter (passionate, team player, dynamic, leverage, ...); they are refused.",
                    "Paragraphs in the letter are separated by a blank line.",
                ],
            }

    @mcp.tool()
    @in_thread
    def pack_submit(job_id: int, cv: TailoredCV, letter: str) -> PackResult:
        """Agent mode, step 2 of the pack: submit your CV (cv_schema) and letter. Jobgent blocks invented numbers and
        banned phrases, renders the one-page A4 PDF, runs the ATS check, saves the documents (with undo) and marks the
        job pack_ready. If refused, fix exactly what the error names and submit again."""
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            profile = services.store.load()
            tone = (job.application.tone if job.application else "") or profile.preferences.tone
            return finalize_pack(services.settings, s, services.store, job, cv, letter, tone=tone)

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
