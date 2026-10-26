import pytest

from jobgent.config import load_settings
from jobgent.errors import MissingSecretError


def test_settings_reads_secrets_file(tmp_path):
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=sk-test\nexport APIFY_TOKEN=ap-test\n")
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path / "home")}, secrets_file=f)
    assert s.anthropic_api_key == "sk-test"
    assert s.apify_token == "ap-test"
    assert s.db_path == tmp_path / "home" / "jobgent.db"


def test_env_beats_secrets_file(tmp_path):
    f = tmp_path / "env"
    f.write_text("ANTHROPIC_API_KEY=from-file\n")
    s = load_settings(
        env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "from-env"},
        secrets_file=f,
    )
    assert s.anthropic_api_key == "from-env"


def test_require_missing_names_variable(tmp_path):
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path)}, secrets_file=tmp_path / "nope")
    with pytest.raises(MissingSecretError, match="APIFY_TOKEN"):
        s.require("APIFY_TOKEN")


def test_require_present_returns_value(tmp_path):
    s = load_settings(
        env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "sk"},
        secrets_file=tmp_path / "nope",
    )
    assert s.require("ANTHROPIC_API_KEY") == "sk"


def test_project_dotenv_is_read_and_beats_the_secrets_file(tmp_path):
    secrets = tmp_path / "secrets"
    secrets.write_text("APIFY_TOKEN=from-secrets\nANTHROPIC_API_KEY=sk-secrets\n")
    dotenv = tmp_path / ".env"
    dotenv.write_text("# my keys\nAPIFY_TOKEN=from-dotenv\n")
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path)}, secrets_file=secrets, dotenv_file=dotenv)
    assert s.apify_token == "from-dotenv" and s.anthropic_api_key == "sk-secrets"


def test_provider_choice(tmp_path):
    none = tmp_path / "none"
    a = load_settings(env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "sk", "KIE_API_KEY": "k"}, secrets_file=none)
    assert a.llm_provider == "anthropic"
    k = load_settings(env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "", "KIE_API_KEY": "k"}, secrets_file=none)
    assert k.llm_provider == "kie" and k.fast_model == "claude-sonnet-4-5" and k.smart_model == "claude-sonnet-4-5"
    n = load_settings(env={"JOBGENT_HOME": str(tmp_path), "ANTHROPIC_API_KEY": "", "KIE_API_KEY": ""}, secrets_file=none)
    assert n.llm_provider is None
