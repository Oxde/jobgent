"""Build the application pack for one job: tailored CV (HTML + A4 PDF), cover letter, how to apply."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobgent.config import Settings
from jobgent.db import Job, Status
from jobgent.errors import ProfileNotVerifiedError, JobgentError
from jobgent.llm import LLM
from jobgent.pack.letter import write_letter
from jobgent.pack.pdf import html_to_pdf
from jobgent.pack.render import render_cv_html
from jobgent.pack.tailor import tailor_cv
from jobgent.pack.verify import verify_against_profile
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


def slugify(text: str) -> str:
    return _SLUG.sub("-", text.lower().replace(".", "")).strip("-")


def pack_dir_for(settings: Settings, job: Job) -> Path:
    return settings.applications_dir / f"{slugify(job.company)}-{slugify(job.title)}-{job.id}"


def load_pack(settings: Settings, job: Job) -> PackResult:
    meta = pack_dir_for(settings, job) / "meta.json"
    if not meta.is_file():
        raise JobgentError(f"No pack for job {job.id} ({job.title} at {job.company}). Run pack_create first.")
    return PackResult.model_validate_json(meta.read_text())


def create_pack(
    settings: Settings,
    session: Session,
    llm: LLM,
    store: ProfileStore,
    job_id: int,
    pdf: Callable[[str, Path], int] = html_to_pdf,
) -> PackResult:
    job = session.get(Job, job_id)
    if job is None:
        raise JobgentError(f"No job with id {job_id}. Use jobs_list to find ids.")
    profile = store.load()
    if not profile.verified:
        raise ProfileNotVerifiedError()

    out_dir = pack_dir_for(settings, job)
    out_dir.mkdir(parents=True, exist_ok=True)
    cv_html_path, cv_pdf_path, letter_path = out_dir / "cv.html", out_dir / "cv.pdf", out_dir / "cover_letter.md"

    cv = tailor_cv(llm, settings.smart_model, profile, job)
    verify_against_profile(llm, settings.fast_model, profile, cv.as_text())
    html = render_cv_html(profile, cv, store.master_cv_path())
    pages = pdf(html, cv_pdf_path)
    if pages > 1:
        cv = tailor_cv(llm, settings.smart_model, profile, job, extra_instruction="The previous version overflowed one A4 page. Shorten by about 20%: fewer bullets, tighter wording. Keep the most relevant content.")
        verify_against_profile(llm, settings.fast_model, profile, cv.as_text())
        html = render_cv_html(profile, cv, store.master_cv_path())
        pages = pdf(html, cv_pdf_path)
        if pages > 1:
            raise JobgentError(f"CV is {pages} pages after one retry for job {job.id} ({job.title}). Trim the profile or the master template.")
    cv_html_path.write_text(html)

    letter = write_letter(llm, settings.smart_model, profile, job, store.voice())
    verify_against_profile(llm, settings.fast_model, profile, letter.body)
    letter_path.write_text(letter.body)

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
    )
    (out_dir / "meta.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2))

    app = get_or_create_application(session, job.id)
    app.status = Status.pack_ready
    app.pack_dir = str(out_dir)
    session.commit()
    return result
