from datetime import date

from stageone.config import load_settings
from stageone.fetch import build_sources
from stageone.profile.models import Personal, Profile, SearchProfile
from stageone.sources.companies import Company


def profile() -> Profile:
    return Profile(personal=Personal(name="T"), search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def test_build_sources_without_apify_token_skips_linkedin(tmp_path):
    settings = load_settings(env={"STAGEONE_HOME": str(tmp_path), "APIFY_TOKEN": ""}, secrets_file=tmp_path / "none")
    sources, skipped = build_sources(settings, profile(), [Company(name="Acme", ats="lever", board="acme")])
    assert [s.name for s in sources] == ["ats:lever:acme"]
    assert len(skipped) == 1 and "APIFY_TOKEN" in skipped[0] and skipped[0].startswith("linkedin")


def test_build_sources_with_token_includes_linkedin(tmp_path):
    settings = load_settings(env={"STAGEONE_HOME": str(tmp_path), "APIFY_TOKEN": "t"}, secrets_file=tmp_path / "none")
    sources, skipped = build_sources(settings, profile(), [])
    assert [s.name for s in sources] == ["linkedin"] and skipped == []


def test_fetch_all_without_anthropic_key_still_returns_sources(services, monkeypatch):
    from stageone.errors import MissingSecretError
    from stageone.fetch import fetch_all

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    monkeypatch.setattr("stageone.fetch.load_companies", lambda p: [])
    summary = fetch_all(services)
    assert summary.classified == 0 and summary.failed == []
    assert any("ANTHROPIC_API_KEY" in s for s in summary.skipped)
    assert "failed" in summary.model_dump()
