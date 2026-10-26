"""Command line mirror of the MCP tools, for cron and for debugging."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

from jobgent.db import Status
from jobgent.errors import JobgentError
from jobgent.fetch import fetch_all
from jobgent.pack.create import create_pack
from jobgent.service import build_services
from jobgent.sources.ats import ATSSource
from jobgent.sources.companies import load_companies
from jobgent.tracker import set_status, weekly_stats
from jobgent.views import detail, get_job, list_jobs

app = typer.Typer(no_args_is_help=True, help="Jobgent: internship copilot.", pretty_exceptions_show_locals=False)
profile_app = typer.Typer(no_args_is_help=True, help="Profile (knowledge base) commands.", pretty_exceptions_show_locals=False)
app.add_typer(profile_app, name="profile")


@app.command()
def init() -> None:
    """Create the data directory and database."""
    s = build_services()
    typer.echo(f"Data directory: {s.settings.home}")
    typer.echo("Profile: " + ("present" if s.store.exists() else "missing (use `jobgent profile import <json>`)"))


@profile_app.command("show")
def profile_show() -> None:
    typer.echo(yaml.safe_dump(build_services().store.load().model_dump(mode="json"), sort_keys=False, allow_unicode=True))


@profile_app.command("set")
def profile_set(path: str, value: str) -> None:
    """Set a field by dotted path. Text fields take the text as is; others are parsed as YAML."""
    build_services().store.update(path, value)
    typer.echo("ok")


@profile_app.command("verify")
def profile_verify(verified: bool = True) -> None:
    build_services().store.update("verified", verified)
    typer.echo(f"verified={verified}")


@profile_app.command("import")
def profile_import(json_path: Path) -> None:
    p = build_services().store.import_jobkiller(json_path)
    typer.echo(f"Imported profile for {p.personal.name}. Review it, then `jobgent profile verify`.")


@profile_app.command("voice")
def profile_voice(text: str | None = None) -> None:
    store = build_services().store
    if text is not None:
        store.set_voice(text)
    typer.echo(store.voice())


@app.command()
def fetch(classify: bool = True, score: bool = True) -> None:
    """Run all sources, then classify and score."""
    summary = fetch_all(build_services(), classify=classify, score=score)
    for r in summary.sources:
        typer.echo(f"{r.source:40s} {r.count:4d} jobs" + (f"  ERROR {r.error}" if r.error else ""))
    for s in summary.skipped:
        typer.echo(f"skipped: {s}")
    i = summary.ingest
    typer.echo(f"inserted {i.inserted}, updated {i.updated}, duplicates {i.duplicates}; classified {summary.classified}, scored {summary.scored}")
    if summary.failed:
        raise typer.Exit(code=1)


@app.command()
def jobs(min_score: int = 0, status: str | None = None, limit: int = 30) -> None:
    """The scored feed."""
    s = build_services()
    with s.sessionmaker() as session:
        for j in list_jobs(session, s.store.load().search, min_score, status, None, limit):
            typer.echo(f"{j.id:5d}  {j.score if j.score is not None else '--':>3}  {j.status:10s} {j.title} — {j.company} ({j.location or ''})")


@app.command()
def job(job_id: int) -> None:
    s = build_services()
    with s.sessionmaker() as session:
        typer.echo(yaml.safe_dump(detail(get_job(session, job_id)).model_dump(mode="json"), sort_keys=False, allow_unicode=True))


@app.command()
def pack(job_id: int) -> None:
    """Generate CV + cover letter for one job."""
    s = build_services()
    with s.sessionmaker() as session:
        try:
            r = create_pack(s.settings, session, s.llm_factory(), s.store, job_id)
        except JobgentError as e:
            typer.echo(f"error: {e}", err=True)
            raise typer.Exit(code=1) from e
    typer.echo(f"Pack: {r.dir}\nApply: {r.apply_url}" + (f"\nEmail: {r.apply_email}" if r.apply_email else ""))
    for line in r.change_summary:
        typer.echo(f"  - {line}")


@app.command()
def status(job_id: int, new_status: str, notes: str | None = None) -> None:
    s = build_services()
    with s.sessionmaker() as session:
        a = set_status(session, job_id, Status(new_status), notes)
    typer.echo(f"job {job_id}: {a.status.value}")


@app.command()
def stats() -> None:
    s = build_services()
    with s.sessionmaker() as session:
        st = weekly_stats(session, s.store.load().preferences.weekly_goal)
    typer.echo(f"applied this week: {st.applied_this_week}/{st.goal}")
    for k, v in sorted(st.by_status.items()):
        typer.echo(f"  {k:10s} {v}")


@app.command()
def companies() -> None:
    """Check every company board in companies.yaml against the live API."""
    s = build_services()
    with s.http_client_factory() as client:
        for c in load_companies(s.settings.companies_file):
            try:
                n = len(ATSSource(c).fetch(client))
                typer.echo(f"OK    {c.name:25s} {c.ats:10s} {n} jobs")
            except Exception as e:  # noqa: BLE001 — a report, not a crash
                typer.echo(f"FAIL  {c.name:25s} {c.ats:10s} {str(e)[:120]}")


@app.command("landing-data")
def landing_data(out: Path = typer.Argument(Path("landing/data.json"))) -> None:
    """Export the current feed (title, company, city, url) as JSON for the landing page."""
    import json
    from datetime import datetime

    from jobgent.ingest import city

    s = build_services()
    with s.sessionmaker() as session:
        feed = list_jobs(session, s.store.load().search, 0, None, None, 500)
    rows = [{"title": j.title, "company": j.company, "city": city(j.location).title(), "url": j.url} for j in feed]
    payload = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "count": len(rows),
        "companies": len({r["company"] for r in rows}),
        "boards": len(load_companies(s.settings.companies_file)),
        "jobs": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    typer.echo(f"{len(rows)} jobs → {out}")


@app.command()
def mcp() -> None:
    """Run the MCP server on stdio."""
    from jobgent.mcp_server import build_mcp

    build_mcp(build_services()).run()


@app.command()
def web(host: str = "127.0.0.1", port: int = 8781) -> None:
    """Run the web UI."""
    import uvicorn

    from jobgent.web.app import create_app

    uvicorn.run(create_app(build_services()), host=host, port=port)
