"""Pack documents as units. Hand edits change the current content; every AI change and every restore first
saves a version, so it can be undone. Capped at 50 versions per document."""

from __future__ import annotations

import copy
import re

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.db import Document, DocumentVersion
from jobgent.errors import JobgentError
from jobgent.pack.tailor import TailoredCV

MAX_VERSIONS = 50
_PATH = re.compile(r"^(experience|projects)\[(\d+)\]\.(bullets\[(\d+)\]|description)$")


class DocumentError(JobgentError):
    pass


class Unit(BaseModel):
    id: str
    label: str
    text: str


def cv_units(cv: TailoredCV) -> list[Unit]:
    units = [Unit(id="summary", label="Summary", text=cv.summary)]
    for i, e in enumerate(cv.experience):
        for j, b in enumerate(e.bullets):
            units.append(Unit(id=f"experience[{i}].bullets[{j}]", label=f"{e.company or e.title}, bullet {j + 1}", text=b))
    for i, p in enumerate(cv.projects):
        units.append(Unit(id=f"projects[{i}].description", label=f"Project: {p.name}", text=p.description))
    units.append(Unit(id="skills", label="Skills", text=", ".join(cv.skills)))
    return units


def units_of(kind: str, content: dict[str, object]) -> list[Unit]:
    if kind == "cv":
        return cv_units(TailoredCV.model_validate(content))
    if kind in ("letter", "followup"):
        paragraphs = content.get("paragraphs", [])
        assert isinstance(paragraphs, list)
        return [Unit(id=f"p{i}", label=f"Paragraph {i + 1}", text=str(t)) for i, t in enumerate(paragraphs)]
    if kind == "email":
        return [Unit(id="subject", label="Subject", text=str(content.get("subject", ""))), Unit(id="body", label="Body", text=str(content.get("body", "")))]
    raise DocumentError(f"Unknown document kind {kind!r}")


def load_document(session: Session, job_id: int, kind: str) -> Document:
    doc = session.scalar(select(Document).where(Document.job_id == job_id, Document.kind == kind))
    if doc is None:
        raise DocumentError(f"No {kind} for job {job_id} yet. Write the application pack first.")
    return doc


def versions(session: Session, job_id: int, kind: str) -> list[DocumentVersion]:
    doc = load_document(session, job_id, kind)
    return list(session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id).order_by(DocumentVersion.id)))


def _snapshot(session: Session, doc: Document, cause: str, detail: str = "") -> None:
    session.add(DocumentVersion(document_id=doc.id, content=copy.deepcopy(doc.content), cause=cause, detail=detail))
    session.flush()
    old = versions(session, doc.job_id, doc.kind)
    for v in old[: max(0, len(old) - MAX_VERSIONS)]:
        session.delete(v)


def save_document(session: Session, job_id: int, kind: str, content: dict[str, object], cause: str) -> Document:
    """Write a whole document (e.g. a new pack). The written state is the first version."""
    doc = session.scalar(select(Document).where(Document.job_id == job_id, Document.kind == kind))
    if doc is None:
        doc = Document(job_id=job_id, kind=kind, content=content, trimmed=[])
        session.add(doc)
        session.flush()
    else:
        _snapshot(session, doc, f"before {cause}")
        doc.content, doc.trimmed = content, []
    _snapshot(session, doc, cause)
    session.commit()
    return doc


def _set(kind: str, content: dict[str, object], unit: str, text: str) -> dict[str, object]:
    c = copy.deepcopy(content)
    if kind == "cv":
        if unit == "summary":
            c["summary"] = text
            return c
        if unit == "skills":
            c["skills"] = [s.strip() for s in text.split(",") if s.strip()]
            return c
        m = _PATH.match(unit)
        if m:
            section, i = m.group(1), int(m.group(2))
            items = c.get(section)
            if isinstance(items, list) and i < len(items):
                item = items[i]
                assert isinstance(item, dict)
                if m.group(4) is not None:
                    bullets = item.get("bullets")
                    j = int(m.group(4))
                    if isinstance(bullets, list) and j < len(bullets):
                        bullets[j] = text
                        return c
                elif section == "projects":
                    item["description"] = text
                    return c
    elif kind in ("letter", "followup"):
        paragraphs = c.get("paragraphs")
        m2 = re.match(r"^p(\d+)$", unit)
        if isinstance(paragraphs, list) and m2 and int(m2.group(1)) < len(paragraphs):
            paragraphs[int(m2.group(1))] = text
            return c
    elif kind == "email" and unit in ("subject", "body"):
        c[unit] = text
        return c
    raise DocumentError(f"No unit {unit!r} in this {kind}.")


def set_unit(session: Session, job_id: int, kind: str, unit: str, text: str, cause: str | None, detail: str = "") -> Document:
    """cause=None for a hand edit (no version); otherwise the AI change is snapshotted first so it can be undone."""
    doc = load_document(session, job_id, kind)
    new = _set(kind, doc.content, unit, text)
    if cause is not None:
        _snapshot(session, doc, cause, detail)
    doc.content = new
    session.commit()
    return doc


def undo_last(session: Session, job_id: int, kind: str) -> Document:
    doc = load_document(session, job_id, kind)
    history = versions(session, job_id, kind)
    if len(history) <= 1:
        raise DocumentError("Nothing to undo.")
    last = history[-1]
    doc.content = copy.deepcopy(last.content)
    session.delete(last)
    session.commit()
    return doc


def restore_version(session: Session, job_id: int, kind: str, version_id: int) -> Document:
    doc = load_document(session, job_id, kind)
    target = session.get(DocumentVersion, version_id)
    if target is None or target.document_id != doc.id:
        raise DocumentError(f"No version {version_id} for this {kind}.")
    _snapshot(session, doc, "before restore")
    doc.content = copy.deepcopy(target.content)
    session.commit()
    return doc


def leave_out(session: Session, job_id: int, kind: str, unit: str) -> Document:
    """Remove a project or a bullet from the CV; it can be put back."""
    doc = load_document(session, job_id, kind)
    c = copy.deepcopy(doc.content)
    m = _PATH.match(unit)
    if kind != "cv" or not m:
        raise DocumentError("Only CV bullets and projects can be left out.")
    section, i = m.group(1), int(m.group(2))
    items = c.get(section)
    if not isinstance(items, list) or i >= len(items):
        raise DocumentError(f"No unit {unit!r} in this CV.")
    if section == "projects":
        removed = items.pop(i)
        assert isinstance(removed, dict)
        entry: dict[str, object] = {"label": f"Project: {removed.get('name')}", "section": "projects", "index": i, "item": removed}
    else:
        item = items[i]
        assert isinstance(item, dict)
        bullets = item.get("bullets")
        j = int(m.group(4) or 0)
        if not isinstance(bullets, list) or j >= len(bullets):
            raise DocumentError(f"No unit {unit!r} in this CV.")
        text = bullets.pop(j)
        entry = {"label": f"Bullet: {str(text)[:60]}", "section": "bullet", "index": i, "position": j, "item": text}
    _snapshot(session, doc, "left out", unit)
    doc.content = c
    doc.trimmed = [*doc.trimmed, entry]
    session.commit()
    return doc


def put_back(session: Session, job_id: int, kind: str, trimmed_index: int) -> Document:
    doc = load_document(session, job_id, kind)
    if not 0 <= trimmed_index < len(doc.trimmed):
        raise DocumentError("Nothing to put back there.")
    entry = doc.trimmed[trimmed_index]
    c = copy.deepcopy(doc.content)
    if entry["section"] == "projects":
        projects = c.setdefault("projects", [])
        assert isinstance(projects, list)
        projects.insert(min(int(str(entry["index"])), len(projects)), entry["item"])
    else:
        experience = c.get("experience")
        assert isinstance(experience, list)
        item = experience[int(str(entry["index"]))]
        assert isinstance(item, dict)
        bullets = item.setdefault("bullets", [])
        assert isinstance(bullets, list)
        bullets.insert(min(int(str(entry["position"])), len(bullets)), entry["item"])
    _snapshot(session, doc, "put back", str(entry["label"]))
    doc.content = c
    doc.trimmed = [t for k, t in enumerate(doc.trimmed) if k != trimmed_index]
    session.commit()
    return doc
