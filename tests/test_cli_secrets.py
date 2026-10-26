from typer.testing import CliRunner

from jobgent.cli import app
from jobgent.config import load_settings


def test_cli_error_never_prints_secrets(services, monkeypatch, tmp_path):
    services.settings = load_settings(env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "sk-SUPERSECRET", "APIFY_TOKEN": "ap-SUPERSECRET"}, secrets_file=tmp_path / "none")
    monkeypatch.setattr("jobgent.cli.build_services", lambda: services)
    r = CliRunner().invoke(app, ["pack", "999"])
    assert r.exit_code != 0
    assert "SUPERSECRET" not in r.output
    assert "999" in r.output


def test_settings_repr_hides_secrets(tmp_path):
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "sk-SUPERSECRET"}, secrets_file=tmp_path / "none")
    assert "SUPERSECRET" not in repr(s) and "SUPERSECRET" not in str(s)
    assert s.require("ANTHROPIC_API_KEY") == "sk-SUPERSECRET"
