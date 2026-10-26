"""Through the real fastmcp transport: errors must reach the agent, and slow tools must run off the loop."""
import asyncio
import json
from datetime import date

import pytest
from fastmcp import Client

from jobgent.llm import FakeLLM
from jobgent.mcp_server import build_mcp
from jobgent.pack.letter import CoverLetter
from jobgent.pack.review import Review
from jobgent.pack.tailor import TailoredCV
from jobgent.pack.verify import VerifyOutput
from jobgent.profile.models import Personal, Profile, SearchProfile


def call(mcp, name, args):
    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)

    return asyncio.run(go())


def test_unverified_profile_message_reaches_agent(services):
    services.store.save(Profile(verified=False, personal=Personal(name="T"),
                                search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))))
    with pytest.raises(Exception, match="not verified"):
        call(build_mcp(services), "pack_create", {"job_id": 1})


def test_invented_claim_is_named_for_agent(services):
    fake = FakeLLM([TailoredCV(summary="S", skills=["Kubernetes"], change_summary=["x"]), CoverLetter(body="Dear Acme"), Review(),
                    VerifyOutput(unsupported_claims=["Kubernetes experience"])])
    services.llm_factory = lambda: fake
    with pytest.raises(Exception, match="Kubernetes"):
        call(build_mcp(services), "pack_create", {"job_id": 1})


def test_missing_key_is_named_for_agent(services):
    from jobgent.errors import MissingSecretError

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    with pytest.raises(Exception, match="ANTHROPIC_API_KEY"):
        call(build_mcp(services), "job_score", {"job_id": 1})


@pytest.mark.slow
def test_pack_create_renders_real_pdf_inside_mcp_loop(services):
    pytest.importorskip("playwright")
    fake = FakeLLM([TailoredCV(summary="S", skills=["Python"], change_summary=["x"]), CoverLetter(body="Dear Acme"), Review(),
                    VerifyOutput(), VerifyOutput()])
    services.llm_factory = lambda: fake
    try:
        result = call(build_mcp(services), "pack_create", {"job_id": 1})
    except Exception as e:  # chromium missing on this machine
        if "install chromium" in str(e):
            pytest.skip(str(e))
        raise
    data = json.loads(result[0].text)
    assert data["cv_pdf"].endswith("cv.pdf")


def test_profile_update_keeps_strings_raw(services):
    mcp = build_mcp(services)
    out = json.loads(call(mcp, "profile_update", {"path": "personal.phone", "value": "+31612345678"})[0].text)
    assert out["personal"]["phone"] == "+31612345678"
    out = json.loads(call(mcp, "profile_update", {"path": "preferences.weekly_goal", "value": "7"})[0].text)
    assert out["preferences"]["weekly_goal"] == 7


def test_jobs_fetch_without_anthropic_key_returns_report(services, monkeypatch):
    from jobgent.errors import MissingSecretError

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    monkeypatch.setattr("jobgent.fetch.load_companies", lambda p: [])
    data = json.loads(call(build_mcp(services), "jobs_fetch", {})[0].text)
    assert data["classified"] == 0 and any("ANTHROPIC_API_KEY" in s for s in data["skipped"])
    assert "failed" in data and "sources" in data and "report" not in data
