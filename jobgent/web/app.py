"""JSON API for the React app, plus serving the built app itself."""

from __future__ import annotations

from pathlib import Path
from typing import get_args, get_origin

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from jobgent.assistant import Turn, chat
from jobgent.ats import AtsReport, ats_report
from jobgent.dashboard import Column, HomeData, applications_board, home_data
from jobgent.db import Status
from jobgent.errors import JobgentError, MissingSecretError
from jobgent.pack.create import PackResult, create_pack, load_pack, pack_dir_for
from jobgent.pack.render import TemplateInfo, list_templates, render_cv_html, template_file
from jobgent.pack.tailor import general_cv
from jobgent.profile.models import Education, Experience, Language, Profile, Project, Skill
from jobgent.profile.store import ChecklistItem, completeness
from jobgent.service import Services
from jobgent.sources.companies import load_companies
from jobgent.tracker import WeeklyStats, set_status, weekly_stats
from jobgent.views import JobDetail, JobSummary, detail, get_job, list_jobs

DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"

SECTIONS: dict[str, type[BaseModel]] = {
    "education": Education,
    "experience": Experience,
    "projects": Project,
    "skills": Skill,
    "languages": Language,
}


class FieldSpec(BaseModel):
    name: str
    kind: str  # "text" | "lines"


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
            kind = "lines" if get_origin(ann) is list and get_args(ann) == (str,) else "text"
            fields.append(FieldSpec(name=name, kind=kind))
        specs.append(SectionSpec(key=key, title=titles[key], fields=fields))
    return specs


class Dim(BaseModel):
    name: str
    value: int
    max: int


class JobPage(BaseModel):
    job: JobDetail
    dims: list[Dim] | None
    ats: AtsReport | None
    pack: PackResult | None
    letter: str | None


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
        letter = pack.letter_md.read_text() if pack and pack.letter_md.is_file() else None
        return JobPage(job=job, dims=dims, ats=_ats_for(job_id), pack=pack, letter=letter)

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
            return services.store.import_jobkiller(path)
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
    def cv_preview(template: str | None = None) -> HTMLResponse:
        profile = services.store.load()
        tid = template or profile.preferences.template
        try:
            template_file(tid)
        except KeyError as e:
            raise _bad(e) from e
        return HTMLResponse(render_cv_html(profile, general_cv(profile), services.store.master_cv_path(), tid))

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
