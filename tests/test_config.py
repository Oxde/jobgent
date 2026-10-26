import pytest

from stageone.config import load_settings
from stageone.errors import MissingSecretError


def test_settings_reads_secrets_file(tmp_path):
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=sk-test\nexport APIFY_TOKEN=ap-test\n")
    s = load_settings(env={"STAGEONE_HOME": str(tmp_path / "home")}, secrets_file=f)
    assert s.anthropic_api_key == "sk-test"
    assert s.apify_token == "ap-test"
    assert s.db_path == tmp_path / "home" / "stageone.db"


def test_env_beats_secrets_file(tmp_path):
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=from-file\n")
    s = load_settings(
        env={"STAGEONE_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "from-env"},
        secrets_file=f,
    )
    assert s.anthropic_api_key == "from-env"


def test_require_missing_names_variable(tmp_path):
    s = load_settings(env={"STAGEONE_HOME": str(tmp_path)}, secrets_file=tmp_path / "nope")
    with pytest.raises(MissingSecretError, match="APIFY_TOKEN"):
        s.require("APIFY_TOKEN")


def test_require_present_returns_value(tmp_path):
    s = load_settings(
        env={"STAGEONE_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "sk"},
        secrets_file=tmp_path / "nope",
    )
    assert s.require("ANTHROPIC_API_KEY") == "sk"
