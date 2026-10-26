from datetime import date

from jobgent.config import load_settings
from jobgent.fetch import build_sources
from jobgent.profile.models import Personal, Profile, SearchProfile
from jobgent.sources.companies import Company


def profile() -> Profile:
    return Profile(personal=Personal(name="T"), search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def test_without_apify_token_linkedin_uses_the_free_guest_search(tmp_path):
    from jobgent.sources.linkedin_guest import LinkedInGuestSource

    settings = load_settings(env={"JOBGENT_HOME": str(tmp_path), "APIFY_TOKEN": "", "JOBGENT_LINKEDIN": "auto"}, secrets_file=tmp_path / "none")
    sources, skipped = build_sources(settings, profile(), [Company(name="Acme", ats="lever", board="acme")])
    assert [s.name for s in sources] == ["linkedin", "ats:lever:acme"] and isinstance(sources[0], LinkedInGuestSource) and skipped == []


def test_linkedin_mode_off_and_forced_guest(tmp_path):
    from jobgent.sources.linkedin_guest import LinkedInGuestSource

    off = load_settings(env={"JOBGENT_HOME": str(tmp_path), "APIFY_TOKEN": "t", "JOBGENT_LINKEDIN": "off"}, secrets_file=tmp_path / "none")
    sources, skipped = build_sources(off, profile(), [])
    assert sources == [] and "off" in skipped[0]
    guest = load_settings(env={"JOBGENT_HOME": str(tmp_path), "APIFY_TOKEN": "t", "JOBGENT_LINKEDIN": "guest"}, secrets_file=tmp_path / "none")
    assert isinstance(build_sources(guest, profile(), [])[0][0], LinkedInGuestSource)


def test_build_sources_with_token_includes_linkedin(tmp_path):
    from jobgent.sources.apify import ApifyLinkedInSource

    settings = load_settings(env={"JOBGENT_HOME": str(tmp_path), "APIFY_TOKEN": "t", "JOBGENT_LINKEDIN": "auto"}, secrets_file=tmp_path / "none")
    sources, skipped = build_sources(settings, profile(), [])
    assert [s.name for s in sources] == ["linkedin"] and isinstance(sources[0], ApifyLinkedInSource) and skipped == []


def test_fetch_all_without_anthropic_key_still_returns_sources(services, monkeypatch):
    from jobgent.errors import MissingSecretError
    from jobgent.fetch import fetch_all

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    monkeypatch.setattr("jobgent.fetch.load_companies", lambda p: [])
    summary = fetch_all(services)
    assert summary.classified == 0 and summary.failed == []
    assert any("ANTHROPIC_API_KEY" in s for s in summary.skipped)
    assert "failed" in summary.model_dump()
