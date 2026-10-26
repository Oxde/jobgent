from typer.testing import CliRunner

from stageone.cli import app


def test_stats_and_jobs(services, monkeypatch):
    monkeypatch.setattr("stageone.cli.build_services", lambda: services)
    r = CliRunner().invoke(app, ["stats"])
    assert r.exit_code == 0, r.output
    assert "0/10" in r.output
    r = CliRunner().invoke(app, ["jobs"])
    assert r.exit_code == 0 and "Data Intern" in r.output
