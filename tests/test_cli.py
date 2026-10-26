from typer.testing import CliRunner

from jobgent.cli import app


def test_stats_and_jobs(services, monkeypatch):
    monkeypatch.setattr("jobgent.cli.build_services", lambda: services)
    r = CliRunner().invoke(app, ["stats"])
    assert r.exit_code == 0, r.output
    assert "0/10" in r.output
    r = CliRunner().invoke(app, ["jobs"])
    assert r.exit_code == 0 and "Data Intern" in r.output


def test_landing_data_exports_feed_json(services, monkeypatch, tmp_path):
    import json

    monkeypatch.setattr("jobgent.cli.build_services", lambda: services)
    out = tmp_path / "data.json"
    r = CliRunner().invoke(app, ["landing-data", str(out)])
    assert r.exit_code == 0, r.output
    data = json.loads(out.read_text())
    assert data["count"] == 2 and data["companies"] >= 1 and data["boards"] >= 20 and "updated" in data
    assert data["jobs"][0]["title"] == "Data Intern" and set(data["jobs"][0]) == {"title", "company", "city", "url"}
