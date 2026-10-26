"""JSON API for the React app, plus serving the built app itself."""

from __future__ import annotations

from datetime import datetime
from collections.abc import Callable
from pathlib import Path
from typing import get_args, get_origin

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import yaml
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobgent.assistant import Turn, chat
from jobgent.ats import AtsReport, ats_report
from jobgent.dashboard import Column, HomeData, applications_board, home_data
from jobgent.db import ApplicationEvent, Document, Status
from jobgent.lifecycle import TimelineItem, add_note, set_interview, timeline, undo_status
from jobgent.pack.followup import FollowUp, write_followup
from jobgent.documents import save_document
from jobgent.documents import leave_out, load_document, put_back, restore_version, set_unit, undo_last, units_of, versions, Unit
from jobgent.errors import JobgentError, MissingSecretError
from jobgent.evaluate import evaluate_job
from jobgent.pack.create import PackResult, create_pack, load_pack, pack_dir_for
from jobgent.pack.factguard import fact_check
from jobgent.pack.pdf import html_to_pdf
from jobgent.pack.render_pack import rerender
from jobgent.pack.rewrite import rewrite_unit
from jobgent.pack.render import EDITABLE_TEMPLATES, TemplateInfo, list_templates, render_cv_html, template_file
from jobgent.pack.tailor import general_cv
from jobgent.profile.models import Education, Experience, Language, Profile, Project, Skill
from jobgent.profile.store import ChecklistItem, completeness
from jobgent.service import Services
from jobgent.sources.companies import load_companies
from jobgent.tracker import WeeklyStats, set_status, weekly_stats
from jobgent.views import JobDetail, JobSummary, detail, get_job, list_jobs

DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

# Injected into the CV preview when ?edit=1: every [data-path] element becomes editable in place and saves on blur.
EDIT_SNIPPET = """
<style>
[data-path] { border-radius: 2px; outline: 1px dashed transparent; outline-offset: 1px; transition: outline-color .12s, background-color .12s; }
[data-path]:hover { outline-color: rgba(255,90,31,.55); cursor: text; }
[data-path]:focus { outline: 2px solid #ff5a1f; background: rgba(255,90,31,.06); }
[data-path].jg-saved { background: rgba(62,207,122,.18); }
[data-path].jg-error { outline: 2px solid #ff6b61; }
</style>
<script>
(function () {
  const post = (msg) => parent.postMessage(Object.assign({ source: "jobgent-cv" }, msg), "*");
  document.querySelectorAll("[data-path]").forEach((el) => {
    el.setAttribute("contenteditable", "plaintext-only");
    el.setAttribute("spellcheck", "true");
    let before = el.textContent;
    el.addEventListener("focus", () => { before = el.textContent; });
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); el.blur(); }
      if (e.key === "Escape") { el.textContent = before; el.blur(); }
    });
    el.addEventListener("blur", async () => {
      const value = el.textContent.trim();
      if (value === before.trim()) return;
      const path = el.getAttribute("data-path");
      const res = await fetch("/api/profile", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, value }) });
      if (res.ok) {
        before = value; el.classList.add("jg-saved"); setTimeout(() => el.classList.remove("jg-saved"), 900);
        post({ type: "saved", path });
      } else {
        let detail = res.statusText; try { detail = (await res.json()).detail; } catch (_) {}
        el.classList.add("jg-error"); post({ type: "error", path, detail: String(detail) });
      }
    });
  });
  post({ type: "ready" });
})();
</script>
"""

SECTIONS: dict[str, type[BaseModel]] = {
    "education": Education,
    "experience": Experience,
    "projects": Project,
    "skills": Skill,
    "languages": Language,
}


class FieldSpec(BaseModel):
    name: str
    kind: str  # "text" | "lines" | "bool"


class SectionSpec(BaseModel):
    key: str
    title: str
    fields: list[FieldSpec]


def section_specs() -> list[SectionSpec]:
    titles = {"education": "Education", "experience": "Experience", "projects": "Projects", "skills": "Skills", "languages": "Languages"}
    specs: list[SectionSpec] = []
    for key, model in SECTIONS.items():
        fields = []
        for name, field in model.model_fields.items():
            ann = field.annotation
            kind = "bool" if ann is bool else "lines" if get_origin(ann) is list and get_args(ann) == (str,) else "text"
            fields.append(FieldSpec(name=name, kind=kind))
        specs.append(SectionSpec(key=key, title=titles[key], fields=fields))
    return specs


class Dim(BaseModel):
    name: str
    value: int
    max: int


class EvaluationView(BaseModel):
    verdict: str
    verdict_reason: str
    summary: str
    deadline: str | None
    coverage: int
    gates: list[dict[str, str]]
    requirements: list[dict[str, str]]
    created_at: datetime


class JobPage(BaseModel):
    job: JobDetail
    dims: list[Dim] | None
    ats: AtsReport | None
    pack: PackResult | None
    letter: str | None
    evaluation: EvaluationView | None = None


class TextBody(BaseModel):
    text: str


class InstructionBody(BaseModel):
    instruction: str


class VersionView(BaseModel):
    id: int
    cause: str
    detail: str
    created_at: datetime


class DocumentView(BaseModel):
    units: list[Unit]
    trimmed: list[dict[str, object]]
    versions: list[VersionView]


class AiEditResult(BaseModel):
    declined: bool
    reason: str
    check_this: list[str]


class InterviewBody(BaseModel):
    at: datetime


class StatusBody(BaseModel):
    status: str
    notes: str | None = None


class PatchBody(BaseModel):
    path: str
    value: str


class VoiceBody(BaseModel):
    text: str


class ImportBody(BaseModel):
    json_path: str


class MessageBody(BaseModel):
    message: str


class ChatMessage(BaseModel):
    role: str
    text: str


class ChatResponse(BaseModel):
    reply: str
    applied: list[str]
    failed: list[str]
    history: list[ChatMessage]


class ProfilePage(BaseModel):
    profile: Profile
    checklist: list[ChecklistItem]
    voice: str
    templates: list[TemplateInfo]
    sections: list[SectionSpec]
    master_cv: bool


class KeyStatus(BaseModel):
    name: str
    present: bool
    hint: str


class SettingsPage(BaseModel):
    keys: list[KeyStatus]
    home_dir: str
    companies: int
    fast_model: str
    smart_model: str


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


def build_api(services: Services) -> APIRouter:
    api = APIRouter(prefix="/api")
    history: list[Turn] = []

    def _ats_for(job_id: int) -> AtsReport | None:
        profile = services.store.load()
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            keywords = job.match.keywords if job.match else []
            pack_dir = pack_dir_for(services.settings, job)
        if not keywords:
            return None
        cv_html = pack_dir / "cv.html"
        text = cv_html.read_text() if cv_html.is_file() else general_cv(profile).as_text()
        return ats_report(text, keywords)

    @api.get("/home")
    def home() -> HomeData:
        with services.sessionmaker() as s:
            return home_data(s, services.store.load())

    @api.get("/stats")
    def stats() -> WeeklyStats:
        with services.sessionmaker() as s:
            return weekly_stats(s, services.store.load().preferences.weekly_goal)

    @api.get("/jobs")
    def jobs(min_score: int = 0, status: str | None = None, q: str | None = None, limit: int = 300) -> list[JobSummary]:
        with services.sessionmaker() as s:
            rows = list_jobs(s, services.store.load().search, min_score, status or None, None, limit)
        if q:
            needle = q.lower()
            rows = [j for j in rows if needle in j.title.lower() or needle in j.company.lower()]
        return rows

    @api.get("/jobs/{job_id}")
    def job_page(job_id: int) -> JobPage:
        with services.sessionmaker() as s:
            try:
                db_job = get_job(s, job_id)
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            job = detail(db_job)
            dims = None
            if db_job.match:
                m = db_job.match
                dims = [Dim(name="Skills", value=m.skills, max=50), Dim(name="Role", value=m.role, max=20),
                        Dim(name="Language & location", value=m.lang_loc, max=15), Dim(name="Timing", value=m.timing, max=15)]
            pack = load_pack(services.settings, db_job) if (pack_dir_for(services.settings, db_job) / "meta.json").is_file() else None
            evaluation = EvaluationView.model_validate(db_job.evaluation, from_attributes=True) if db_job.evaluation else None
        letter = pack.letter_md.read_text() if pack and pack.letter_md.is_file() else None
        return JobPage(job=job, dims=dims, ats=_ats_for(job_id), pack=pack, letter=letter, evaluation=evaluation)

    @api.post("/jobs/{job_id}/evaluate")
    def evaluate(job_id: int, check_open: bool = True) -> EvaluationView:
        profile = services.store.load()
        try:
            llm = services.llm_factory()
        except MissingSecretError as e:
            raise _bad(e) from e
        with services.sessionmaker() as s, services.http_client_factory() as client:
            try:
                db_job = get_job(s, job_id)
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            ev = evaluate_job(s, llm, services.settings.fast_model, profile, db_job, client if check_open else None)
            return EvaluationView.model_validate(ev, from_attributes=True)

    @api.get("/jobs/{job_id}/cv", response_class=HTMLResponse)
    def job_cv(job_id: int) -> HTMLResponse:
        """The CV for this job: the tailored one if a pack exists, otherwise the general CV in the chosen template."""
        with services.sessionmaker() as s:
            try:
                db_job = get_job(s, job_id)
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            tailored = pack_dir_for(services.settings, db_job) / "cv.html"
        if tailored.is_file():
            return HTMLResponse(tailored.read_text())
        profile = services.store.load()
        return HTMLResponse(render_cv_html(profile, general_cv(profile), services.store.master_cv_path(), profile.preferences.template))

    def _doc_view(s: Session, job_id: int, kind: str) -> DocumentView | None:
        doc = s.scalar(select(Document).where(Document.job_id == job_id, Document.kind == kind))
        if doc is None:
            return None
        return DocumentView(
            units=units_of(kind, doc.content), trimmed=doc.trimmed,
            versions=[VersionView.model_validate(v, from_attributes=True) for v in versions(s, job_id, kind)],
        )

    def _after_change(s: Session, job_id: int) -> None:
        rerender(services.settings, s, services.store, get_job(s, job_id))

    @api.get("/jobs/{job_id}/documents")
    def documents(job_id: int) -> dict[str, DocumentView | None]:
        with services.sessionmaker() as s:
            get_job(s, job_id)
            return {kind: _doc_view(s, job_id, kind) for kind in ("cv", "letter", "email", "followup")}

    @api.patch("/jobs/{job_id}/documents/{kind}")
    def edit_unit(job_id: int, kind: str, unit: str, body: TextBody) -> DocumentView:
        with services.sessionmaker() as s:
            try:
                set_unit(s, job_id, kind, unit, body.text, cause=None)
                _after_change(s, job_id)
            except JobgentError as e:
                raise _bad(e) from e
            view = _doc_view(s, job_id, kind)
            assert view is not None
            return view

    @api.post("/jobs/{job_id}/documents/{kind}/ai")
    def ai_edit_unit(job_id: int, kind: str, unit: str, body: InstructionBody) -> AiEditResult:
        profile = services.store.load()
        try:
            llm = services.llm_factory()
        except MissingSecretError as e:
            raise _bad(e) from e
        with services.sessionmaker() as s:
            try:
                job = get_job(s, job_id)
                doc = load_document(s, job_id, kind)
                current = next((u for u in units_of(kind, doc.content) if u.id == unit), None)
                if current is None:
                    raise JobgentError(f"No unit {unit!r} in this {kind}.")
                out = rewrite_unit(llm, services.settings.smart_model, profile, job, current.label, current.text, body.instruction)
                if out.declined:
                    return AiEditResult(declined=True, reason=out.reason, check_this=[])
                corpus = yaml.safe_dump(profile.model_dump(mode="json"), allow_unicode=True) + "\n".join(profile.facts) + job.description
                report = fact_check(out.text, corpus)
                if report.invented_numbers:
                    raise JobgentError("Not applied: the rewrite contains numbers that are not in your profile or the posting: " + ", ".join(report.invented_numbers))
                set_unit(s, job_id, kind, unit, out.text, cause="refined", detail=body.instruction)
                _after_change(s, job_id)
            except JobgentError as e:
                raise _bad(e) from e
            return AiEditResult(declined=False, reason="", check_this=report.unverified_names)

    @api.post("/jobs/{job_id}/documents/{kind}/undo")
    def undo_doc(job_id: int, kind: str) -> DocumentView:
        return _doc_action(job_id, kind, lambda s: undo_last(s, job_id, kind))

    @api.post("/jobs/{job_id}/documents/{kind}/leave-out")
    def leave_out_unit(job_id: int, kind: str, unit: str) -> DocumentView:
        return _doc_action(job_id, kind, lambda s: leave_out(s, job_id, kind, unit))

    @api.post("/jobs/{job_id}/documents/{kind}/put-back/{index}")
    def put_back_unit(job_id: int, kind: str, index: int) -> DocumentView:
        return _doc_action(job_id, kind, lambda s: put_back(s, job_id, kind, index))

    @api.post("/jobs/{job_id}/documents/{kind}/restore/{version_id}")
    def restore_doc(job_id: int, kind: str, version_id: int) -> DocumentView:
        return _doc_action(job_id, kind, lambda s: restore_version(s, job_id, kind, version_id))

    def _doc_action(job_id: int, kind: str, action: Callable[[Session], object]) -> DocumentView:
        with services.sessionmaker() as s:
            try:
                action(s)
                _after_change(s, job_id)
            except JobgentError as e:
                raise _bad(e) from e
            view = _doc_view(s, job_id, kind)
            assert view is not None
            return view

    @api.post("/jobs/{job_id}/pack")
    def make_pack(job_id: int) -> PackResult:
        with services.sessionmaker() as s:
            try:
                return create_pack(services.settings, s, services.llm_factory(), services.store, job_id)
            except (JobgentError, RuntimeError) as e:
                raise _bad(e) from e

    @api.post("/jobs/{job_id}/status")
    def change_status(job_id: int, body: StatusBody) -> JobSummary:
        try:
            new_status = Status(body.status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Unknown status {body.status!r}. One of: {', '.join(st.value for st in Status)}") from e
        with services.sessionmaker() as s:
            try:
                set_status(s, job_id, new_status, body.notes)
                return detail(get_job(s, job_id))
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e

    @api.post("/jobs/{job_id}/status/undo")
    def status_undo(job_id: int) -> JobSummary:
        with services.sessionmaker() as s:
            try:
                undo_status(s, job_id)
                return detail(get_job(s, job_id))
            except JobgentError as e:
                raise _bad(e) from e

    @api.post("/jobs/{job_id}/interview")
    def interview(job_id: int, body: InterviewBody) -> JobSummary:
        with services.sessionmaker() as s:
            try:
                set_interview(s, job_id, body.at)
                return detail(get_job(s, job_id))
            except JobgentError as e:
                raise _bad(e) from e

    @api.post("/jobs/{job_id}/notes")
    def note(job_id: int, body: TextBody) -> list[TimelineItem]:
        with services.sessionmaker() as s:
            get_job(s, job_id)
            add_note(s, job_id, body.text)
            return timeline(s, job_id)

    @api.get("/jobs/{job_id}/timeline")
    def job_timeline(job_id: int) -> list[TimelineItem]:
        with services.sessionmaker() as s:
            return timeline(s, job_id)

    @api.post("/jobs/{job_id}/followup")
    def followup(job_id: int) -> FollowUp:
        profile = services.store.load()
        try:
            llm = services.llm_factory()
        except MissingSecretError as e:
            raise _bad(e) from e
        with services.sessionmaker() as s:
            job = get_job(s, job_id)
            app = job.application
            if app is None or app.applied_at is None:
                raise HTTPException(status_code=400, detail="Mark the application as sent first.")
            done = len([e for e in timeline(s, job_id) if e.kind == "followup"])
            draft = write_followup(llm, services.settings.smart_model, profile, job, (datetime.now() - app.applied_at).days, done + 1)
            paragraphs = [p.strip() for p in draft.body.split("\n\n") if p.strip()]
            save_document(s, job_id, "followup", {"subject": draft.subject, "paragraphs": paragraphs}, cause="written")
            return draft

    @api.post("/jobs/{job_id}/followup/sent")
    def followup_sent(job_id: int) -> list[TimelineItem]:
        with services.sessionmaker() as s:
            get_job(s, job_id)
            s.add(ApplicationEvent(job_id=job_id, kind="followup", text="Follow-up sent"))
            s.commit()
            return timeline(s, job_id)

    @api.get("/applications")
    def applications() -> list[Column]:
        with services.sessionmaker() as s:
            return applications_board(s)

    @api.get("/profile")
    def profile_page() -> ProfilePage:
        profile = services.store.load()
        return ProfilePage(profile=profile, checklist=completeness(profile), voice=services.store.voice(),
                           templates=list_templates(), sections=section_specs(), master_cv=services.store.master_cv_path() is not None)

    @api.patch("/profile")
    def profile_patch(body: PatchBody) -> Profile:
        try:
            return services.store.update(body.path, body.value)
        except (KeyError, ValidationError) as e:
            raise _bad(e) from e

    @api.post("/profile/voice")
    def profile_voice(body: VoiceBody) -> dict[str, str]:
        services.store.set_voice(body.text)
        return {"voice": services.store.voice()}

    @api.post("/profile/import")
    def profile_import(body: ImportBody) -> Profile:
        path = Path(body.json_path).expanduser()
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"No file at {path}")
        try:
            return services.store.import_any(path)
        except (KeyError, ValueError, ValidationError) as e:
            raise _bad(e) from e

    def _section(section: str) -> type[BaseModel]:
        model = SECTIONS.get(section)
        if model is None:
            raise HTTPException(status_code=404, detail=f"No section {section!r}. One of: {', '.join(SECTIONS)}")
        return model

    @api.post("/profile/{section}")
    def section_add(section: str, item: dict[str, object]) -> Profile:
        _section(section)
        try:
            return services.store.append(section, item)
        except (KeyError, ValidationError) as e:
            raise _bad(e) from e

    @api.put("/profile/{section}/{index}")
    def section_put(section: str, index: int, item: dict[str, object]) -> Profile:
        _section(section)
        try:
            return services.store.update(f"{section}[{index}]", item)
        except (KeyError, ValidationError) as e:
            raise _bad(e) from e

    @api.delete("/profile/{section}/{index}")
    def section_delete(section: str, index: int) -> Profile:
        _section(section)
        try:
            return services.store.remove(section, index)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @api.get("/templates")
    def templates() -> list[TemplateInfo]:
        return list_templates()

    @api.get("/cv/preview", response_class=HTMLResponse)
    def cv_preview(template: str | None = None, edit: bool = False) -> HTMLResponse:
        profile = services.store.load()
        tid = template or profile.preferences.template
        try:
            template_file(tid)
        except KeyError as e:
            raise _bad(e) from e
        editable = edit and tid in EDITABLE_TEMPLATES and services.store.master_cv_path() is None
        html = render_cv_html(profile, general_cv(profile), services.store.master_cv_path(), tid, editable=editable)
        if editable:
            html = html.replace("</body>", EDIT_SNIPPET + "</body>")
        return HTMLResponse(html)

    @api.get("/cv/pdf")
    def cv_pdf(template: str | None = None) -> FileResponse:
        profile = services.store.load()
        tid = template or profile.preferences.template
        try:
            template_file(tid)
        except KeyError as e:
            raise _bad(e) from e
        html = render_cv_html(profile, general_cv(profile), services.store.master_cv_path(), tid)
        out = services.settings.home / "cv" / f"cv-{tid}.pdf"
        try:
            html_to_pdf(html, out, fit=True)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        name = (profile.personal.name or "cv").replace(" ", "_")
        return FileResponse(out, media_type="application/pdf", filename=f"{name}_CV.pdf")

    @api.get("/profile/version")
    def profile_version() -> dict[str, str]:
        return {"version": services.store.version()}

    @api.get("/assistant")
    def assistant_history() -> list[ChatMessage]:
        return [ChatMessage(role=r, text=t) for r, t in history]

    @api.delete("/assistant")
    def assistant_clear() -> list[ChatMessage]:
        history.clear()
        return []

    @api.post("/assistant")
    def assistant(body: MessageBody) -> ChatResponse:
        history.append(("user", body.message))
        applied: list[str] = []
        failed: list[str] = []
        try:
            result = chat(services.llm_factory(), services.settings.fast_model, services.store, history[:-1], body.message)
            reply, applied, failed = result.reply, result.applied, result.failed
        except MissingSecretError as e:
            reply = str(e)
        except JobgentError as e:
            reply = f"Something went wrong: {e}"
        history.append(("assistant", reply))
        return ChatResponse(reply=reply, applied=applied, failed=failed, history=[ChatMessage(role=r, text=t) for r, t in history])

    @api.get("/settings")
    def settings_page() -> SettingsPage:
        st = services.settings
        try:
            companies = len(load_companies(st.companies_file))
        except FileNotFoundError:
            companies = 0
        return SettingsPage(
            keys=[KeyStatus(name="ANTHROPIC_API_KEY", present=bool(st.anthropic_api_key), hint="Required for matching, CVs and letters."),
                  KeyStatus(name="APIFY_TOKEN", present=bool(st.apify_token), hint="Optional. Turns on LinkedIn search.")],
            home_dir=str(st.home), companies=companies, fast_model=st.fast_model, smart_model=st.smart_model,
        )

    return api


def create_app(services: Services) -> FastAPI:
    app = FastAPI(title="Jobgent")
    app.include_router(build_api(services))

    @app.get("/packs/{job_id}/cv.pdf")
    def pack_pdf(job_id: int) -> FileResponse:
        with services.sessionmaker() as s:
            try:
                pack = load_pack(services.settings, get_job(s, job_id))
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
        html_path = pack.cv_html
        if html_path.is_file() and (not pack.cv_pdf.is_file() or html_path.stat().st_mtime > pack.cv_pdf.stat().st_mtime):
            html_to_pdf(html_path.read_text(), pack.cv_pdf, fit=True)  # edited since the last PDF
        return FileResponse(pack.cv_pdf, media_type="application/pdf", filename=f"cv-{job_id}.pdf")

    dist = DIST
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def spa(path: str) -> HTMLResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such API route")
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(
                "<h1>Jobgent</h1><p>The web app is not built yet. Run <code>cd frontend && npm ci && npm run build</code>, "
                "or use the MCP server / CLI.</p>", status_code=503,
            )
        return HTMLResponse(index.read_text())

    return app
