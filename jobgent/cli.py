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
    p = build_services().store.import_any(json_path.expanduser())
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
def search(query: str, location: str = "Amsterdam", limit: int = 30, linkedin: bool = True) -> None:
    """Search now: LinkedIn for QUERY in LOCATION (if APIFY_TOKEN is set) plus everything saved."""
    from jobgent.search import search_jobs

    r = search_jobs(build_services(), query, location, limit, linkedin)
    typer.echo(f"LinkedIn: {r.fetched} fetched" + (f" ({r.source_error})" if r.source_error else ""))
    for j in r.jobs:
        typer.echo(f"{j.id:5d}  {j.score if j.score is not None else '--':>3}  {j.title} — {j.company} ({j.location or ''})")


@app.command()
def agent(schedule: str | None = typer.Option(None, help="HH:MM: print how to run the agent every day at that time (macOS launchd).")) -> None:
    """Run the job agent once (fetch, score, evaluate the best new postings, queue them). Never sends anything."""
    if schedule:
        hour, _, minute = schedule.partition(":")
        repo = Path(__file__).resolve().parent.parent
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.jobgent.agent</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>-lc</string><string>cd {repo} && uv run jobgent agent</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{int(hour)}</integer><key>Minute</key><integer>{int(minute or 0)}</integer></dict>
  <key>StandardOutPath</key><string>{Path.home()}/.jobgent/agent.log</string>
  <key>StandardErrorPath</key><string>{Path.home()}/.jobgent/agent.log</string>
</dict></plist>"""
        typer.echo("Save this as ~/Library/LaunchAgents/com.jobgent.agent.plist, then run:\n  launchctl load ~/Library/LaunchAgents/com.jobgent.agent.plist\n")
        typer.echo(plist)
        return
    from jobgent.agent import agent_queue, run_agent

    s = build_services()
    run = run_agent(s)
    typer.echo(f"fetched {run.fetched}, evaluated {run.evaluated}, queued {run.queued}")
    if run.note:
        typer.echo(run.note)
    with s.sessionmaker() as session:
        for q in agent_queue(session)[:15]:
            typer.echo(f"{q.job.id:5d}  {q.verdict:8s} {q.job.title} — {q.job.company}: {q.reason}")


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


@app.command("eval")
def eval_cmd() -> None:
    """Run the golden cases against the real model and report agreement with the expected gates and verdicts."""
    from jobgent.db import open_db
    from jobgent.demo import PROFILE
    from jobgent.errors import MissingSecretError
    from jobgent.evals import CASES_DIR, case_job, load_cases
    from jobgent.evaluate import evaluate_job
    import tempfile

    services = build_services()
    try:
        llm = services.llm_factory()
    except MissingSecretError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=1) from e
    cases = load_cases(CASES_DIR)
    agree = 0
    with tempfile.TemporaryDirectory() as tmp:
        session = open_db(Path(tmp) / "eval.db")()
        for case in cases:
            job = case_job(case)
            session.add(job)
            session.commit()
            ev = evaluate_job(session, llm, services.settings.fast_model, PROFILE, job)
            gates = {g["name"]: g["status"] for g in ev.gates}
            ok = ev.verdict == case.expect.verdict and all(gates.get(k) == v for k, v in case.expect.gates.items())
            agree += ok
            typer.echo(f"{'OK  ' if ok else 'DIFF'} {case.id:18s} expected {case.expect.verdict:8s} got {ev.verdict:8s} {ev.verdict_reason[:70]}")
    typer.echo(f"\n{agree}/{len(cases)} agree with the expected verdicts and gates.")


@app.command()
def demo(home: Path = typer.Option(Path.home() / ".jobgent-demo", help="Where to create the demo (never your real ~/.jobgent).")) -> None:
    """Create a complete demo with a made-up student (no API key or personal data needed)."""
    from jobgent.demo import build_demo

    build_demo(home.expanduser())
    typer.echo(f"Demo ready in {home}. Open it with:\n  JOBGENT_HOME={home} uv run jobgent web")


@app.command()
def mcp(http: bool = typer.Option(False, help="Serve over streamable HTTP (for ChatGPT and other remote clients) instead of stdio."),
        port: int = 8790) -> None:
    """Run the MCP server: stdio for Claude Code / Claude Desktop / Cursor, --http for ChatGPT connectors."""
    from jobgent.mcp_server import build_mcp

    server = build_mcp(build_services())
    if http:
        server.run(transport="streamable-http", host="127.0.0.1", port=port)
    else:
        server.run()


@app.command()
def web(host: str = "127.0.0.1", port: int = 8781) -> None:
    """Run the web UI."""
    import uvicorn

    from jobgent.web.app import create_app

    uvicorn.run(create_app(build_services()), host=host, port=port)
