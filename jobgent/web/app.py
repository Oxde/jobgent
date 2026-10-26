"""Small local web UI: feed, job detail with pack, tracker."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jobgent.db import Status
from jobgent.errors import JobgentError
from jobgent.pack.create import create_pack, load_pack, pack_dir_for
from jobgent.service import Services
from jobgent.tracker import set_status, weekly_stats
from jobgent.views import detail, get_job, list_applications, list_jobs

_HERE = Path(__file__).parent


def create_app(services: Services) -> FastAPI:
    app = FastAPI(title="Jobgent")
    templates = Jinja2Templates(directory=str(_HERE / "templates"))
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    def page(request: Request, name: str, **ctx: object) -> HTMLResponse:
        with services.sessionmaker() as s:
            stats = weekly_stats(s, services.store.load().preferences.weekly_goal)
        return templates.TemplateResponse(request, name, {"stats": stats, "statuses": [st.value for st in Status], **ctx})

    @app.get("/", response_class=HTMLResponse)
    def feed(request: Request, min_score: int = 0, status: str | None = None) -> HTMLResponse:
        with services.sessionmaker() as s:
            jobs = list_jobs(s, services.store.load().search, min_score, status or None, None, 100)
        return page(request, "feed.html", jobs=jobs, min_score=min_score, status=status or "")

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: int) -> HTMLResponse:
        with services.sessionmaker() as s:
            try:
                job = detail(get_job(s, job_id))
                db_job = get_job(s, job_id)
                pack = None
                if (pack_dir_for(services.settings, db_job) / "meta.json").is_file():
                    pack = load_pack(services.settings, db_job)
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
        letter = pack.letter_md.read_text() if pack and pack.letter_md.is_file() else None
        return page(request, "job.html", job=job, pack=pack, letter=letter)

    @app.post("/jobs/{job_id}/pack", response_class=HTMLResponse)
    def make_pack(request: Request, job_id: int) -> HTMLResponse:
        with services.sessionmaker() as s:
            try:
                pack = create_pack(services.settings, s, services.llm_factory(), services.store, job_id)
            except (JobgentError, RuntimeError) as e:
                return templates.TemplateResponse(request, "_pack.html", {"pack": None, "letter": None, "error": str(e), "job_id": job_id})
        return templates.TemplateResponse(request, "_pack.html", {"pack": pack, "letter": pack.letter_md.read_text(), "error": None, "job_id": job_id})

    @app.post("/jobs/{job_id}/status")
    def change_status(
        job_id: int, status: str = Form(...), notes: str | None = Form(None), next: str | None = Form(None)
    ) -> RedirectResponse:
        try:
            new_status = Status(status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Unknown status {status!r}. One of: {', '.join(st.value for st in Status)}") from e
        with services.sessionmaker() as s:
            try:
                set_status(s, job_id, new_status, notes)
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
        target = next if next and next.startswith("/") and not next.startswith("//") else f"/jobs/{job_id}"
        return RedirectResponse(url=target, status_code=303)

    @app.get("/tracker", response_class=HTMLResponse)
    def tracker(request: Request) -> HTMLResponse:
        with services.sessionmaker() as s:
            apps = list_applications(s)
        columns = [st.value for st in Status if st not in (Status.new,)]
        return page(request, "tracker.html", apps=apps, columns=columns)

    @app.get("/packs/{job_id}/cv.pdf")
    def pack_pdf(job_id: int) -> FileResponse:
        with services.sessionmaker() as s:
            try:
                pack = load_pack(services.settings, get_job(s, job_id))
            except JobgentError as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
        return FileResponse(pack.cv_pdf, media_type="application/pdf", filename=f"cv-{job_id}.pdf")

    return app
