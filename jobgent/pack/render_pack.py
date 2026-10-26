"""Rebuild a pack's files from its documents after every change."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.config import Settings
from jobgent.db import Document, Job
from jobgent.documents import load_document
from jobgent.pack.create import pack_dir_for
from jobgent.pack.render import render_cv_html
from jobgent.pack.tailor import TailoredCV
from jobgent.profile.store import ProfileStore


def letter_text(doc: Document) -> str:
    paragraphs = doc.content.get("paragraphs", [])
    assert isinstance(paragraphs, list)
    return "\n\n".join(str(p) for p in paragraphs)


def rerender(settings: Settings, session: Session, store: ProfileStore, job: Job) -> Path:
    """Write cv.html and cover_letter.md from the documents. The PDF is rebuilt lazily when it is older than the HTML."""
    out = pack_dir_for(settings, job)
    out.mkdir(parents=True, exist_ok=True)
    profile = store.load()
    cv = TailoredCV.model_validate(load_document(session, job.id, "cv").content)
    (out / "cv.html").write_text(render_cv_html(profile, cv, store.master_cv_path(), profile.preferences.template))
    letter = session.scalar(select(Document).where(Document.job_id == job.id, Document.kind == "letter"))
    if letter is not None:
        (out / "cover_letter.md").write_text(letter_text(letter))
    return out
