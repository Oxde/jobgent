"""Build the application pack for one job: tailored CV (HTML + A4 PDF), cover letter, how to apply."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel
from pypdf.errors import PdfReadError
from sqlalchemy.orm import Session

from jobgent.config import Settings
from jobgent.db import Job, Status
from jobgent.errors import InventedClaimError, JobgentError, ProfileNotVerifiedError
from jobgent.llm import LLM
from jobgent.pack.ats_pdf import AtsPdfCheck, ats_check_text, keyword_buckets, pdf_text
from jobgent.pack.factguard import banned_phrases, fact_check, tidy_letter
from jobgent.pack.letter import CoverLetter, write_letter
from jobgent.pack.pdf import html_to_pdf
from jobgent.pack.render import render_cv_html
from jobgent.pack.review import apply_review, review_pack
from jobgent.pack.tailor import TailoredCV, tailor_cv
from jobgent.pack.verify import verify_against_profile
from jobgent.profile.models import Profile
from jobgent.profile.store import ProfileStore
from jobgent.sources.base import html_to_text
from jobgent.tracker import get_or_create_application

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SLUG = re.compile(r"[^a-z0-9]+")


class PackResult(BaseModel):
    job_id: int
    dir: Path
    cv_html: Path
    cv_pdf: Path
    letter_md: Path
    change_summary: list[str]
    apply_url: str
    apply_email: str | None
    created_at: datetime
    review_applied: list[str] = []
    review_skipped: list[str] = []
    review_notes: dict[str, str] = {}
    check_this: list[str] = []
    tone: str = "warm"
    ats_ok: bool = True
    ats_problems: list[str] = []
    keywords: dict[str, list[str]] = {}


def slugify(text: str) -> str:
    return _SLUG.sub("-", text.lower().replace(".", "")).strip("-")


def pack_dir_for(settings: Settings, job: Job) -> Path:
    return settings.applications_dir / f"{slugify(job.company)}-{slugify(job.title)}-{job.id}"


def load_pack(settings: Settings, job: Job) -> PackResult:
    meta = pack_dir_for(settings, job) / "meta.json"
    if not meta.is_file():
        raise JobgentError(f"No pack for job {job.id} ({job.title} at {job.company}). Run pack_create first.")
    return PackResult.model_validate_json(meta.read_text())


def _corpus(profile: Profile, job: Job) -> str:
    return yaml.safe_dump(profile.model_dump(mode="json"), allow_unicode=True) + "\n" + "\n".join(profile.facts) + "\n" + job.title + "\n" + job.company + "\n" + job.description


def _guard(cv: TailoredCV, letter_body: str, corpus: str) -> list[str]:
    """Hard: invented numbers stop the pack. Soft: unknown names are returned for the user to check."""
    report = fact_check(cv.as_text() + "\n" + letter_body, corpus)
    if report.invented_numbers:
        raise InventedClaimError([f"number not in your profile or the posting: {n}" for n in report.invented_numbers])
    return report.unverified_names


def create_pack(
    settings: Settings,
    session: Session,
    llm: LLM,
    store: ProfileStore,
    job_id: int,
    pdf: Callable[[str, Path], int] = lambda html, out: html_to_pdf(html, out, fit=True),
) -> PackResult:
    """Tailor → letter → review → banned-phrase pass → fact guard → AI fact check → one-page PDF."""
    job = session.get(Job, job_id)
    if job is None:
        raise JobgentError(f"No job with id {job_id}. Use jobs_list to find ids.")
    profile = store.load()
    if not profile.verified:
        raise ProfileNotVerifiedError()
    app = get_or_create_application(session, job.id)
    tone = app.tone or profile.preferences.tone
    requirements = [
        f"- [{r['importance']}] {r['text']}: {r['status']}" + (f" ({r['evidence']})" if r.get("evidence") else "")
        for r in (job.evaluation.requirements if job.evaluation else [])
    ]

    cv = tailor_cv(llm, settings.smart_model, profile, job)
    letter = write_letter(llm, settings.smart_model, profile, job, store.voice(), tone=tone, note=app.ai_note, requirements=requirements)
    review = review_pack(llm, settings.smart_model, profile, job, cv, letter, tone)
    cv, letter, applied, skipped = apply_review(cv, letter, review)
    banned = banned_phrases(letter.body)
    if banned:
        letter = write_letter(llm, settings.smart_model, profile, job, store.voice(), tone=tone, note=app.ai_note, requirements=requirements, fix=banned)
    letter = CoverLetter(body=tidy_letter(letter.body))

    corpus = _corpus(profile, job)
    check_this = _guard(cv, letter.body, corpus)
    verify_against_profile(llm, settings.fast_model, profile, cv.as_text())
    verify_against_profile(llm, settings.fast_model, profile, letter.body)

    out_dir = pack_dir_for(settings, job)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_html_path, cv_pdf_path, letter_path = out_dir / "cv.html", out_dir / "cv.pdf", out_dir / "cover_letter.md"
    html = render_cv_html(profile, cv, store.master_cv_path(), profile.preferences.template)
    pages = pdf(html, cv_pdf_path)
    if pages > 1:
        cv = tailor_cv(llm, settings.smart_model, profile, job, extra_instruction="The previous version overflowed one A4 page. Shorten by about 20%: fewer bullets, tighter wording. Keep the most relevant content.")
        check_this = _guard(cv, letter.body, corpus)
        verify_against_profile(llm, settings.fast_model, profile, cv.as_text())
        html = render_cv_html(profile, cv, store.master_cv_path(), profile.preferences.template)
        pages = pdf(html, cv_pdf_path)
        if pages > 1:
            raise JobgentError(f"CV is {pages} pages after one retry for job {job.id} ({job.title}). Trim the profile or the master template.")
    cv_html_path.write_text(html)
    letter_path.write_text(letter.body)
    (out_dir / "job_posting.md").write_text(f"# {job.title} at {job.company}\n\n{job.url}\n\nArchived {datetime.now():%Y-%m-%d}\n\n{job.description}")

    try:
        text_layer = pdf_text(cv_pdf_path)
        ats = ats_check_text(text_layer, profile.personal.email, profile.personal.phone)
    except PdfReadError as e:
        text_layer, ats = "", AtsPdfCheck(ok=False, problems=[f"Could not read the PDF text layer: {e}"])
    buckets = keyword_buckets(text_layer, corpus, job.match.keywords) if job.match and job.match.keywords else {}

    email_match = _EMAIL.search(html_to_text(job.description))
    result = PackResult(
        job_id=job.id,
        dir=out_dir,
        cv_html=cv_html_path,
        cv_pdf=cv_pdf_path,
        letter_md=letter_path,
        change_summary=cv.change_summary,
        apply_url=job.url,
        apply_email=email_match.group(0) if email_match else None,
        created_at=datetime.now(),
        review_applied=applied,
        review_skipped=skipped,
        review_notes={k: getattr(review, k) for k in ("missed_keywords", "company_angle", "passive_phrasing", "tone")},
        check_this=check_this,
        tone=tone,
        ats_ok=ats.ok,
        ats_problems=ats.problems,
        keywords=buckets,
    )
    (out_dir / "meta.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2))
    (out_dir / "cv.json").write_text(cv.model_dump_json(indent=2))

    app.status = Status.pack_ready
    app.pack_dir = str(out_dir)
    session.commit()
    return result
