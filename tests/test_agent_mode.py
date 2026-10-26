"""Agent mode: the host agent (Claude, ChatGPT) writes the AI parts; Jobgent's deterministic checks still decide."""
import asyncio
import json
from pathlib import Path

import pytest
from fastmcp import Client

from jobgent.db import Application, Job, Status
from jobgent.errors import InventedClaimError, JobgentError
from jobgent.evaluate import finalize_evaluation
from jobgent.gates import Gate
from jobgent.mcp_server import build_mcp
from jobgent.pack.create import finalize_pack
from jobgent.pack.tailor import TailoredCV
from tests.pack.test_create import FakePdf, setup
from tests.test_evaluate import MAP, REQS, job, profile

AGENT_TOOLS = {"evaluate_prompt", "evaluate_submit", "pack_prompt", "pack_submit"}


def call(mcp, name, args):
    async def go():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)

    return json.loads(asyncio.run(go())[0].text)


def test_finalize_evaluation_lets_code_decide_without_a_score(tmp_path):
    from jobgent.db import open_db
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        j = job()
        s.add(j)
        s.commit()
        ok = [Gate(name="open", status="pass", reason="")]
        ev = finalize_evaluation(s, profile(), j, ok, REQS, MAP, score=None, model="host-agent")
        assert ev.model == "host-agent" and ev.deadline == "15 Nov 2026" and ev.summary == REQS.summary
        assert ev.verdict in ("apply", "consider", "skip") and str(ev.coverage) in ev.verdict_reason
        failed = finalize_evaluation(s, profile(), j, [Gate(name="language", status="fail", reason="Dutch")], None, None, score=None, model="m")
        assert failed.verdict == "skip" and failed.requirements == []


def _cv(summary: str = "S") -> TailoredCV:
    return TailoredCV(summary=summary, skills=["Python"], change_summary=["x"])


def test_finalize_pack_writes_everything(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s:
        r = finalize_pack(settings, s, store, s.get(Job, 1), _cv(), "Dear Acme", tone="warm", pdf=FakePdf([1]))
        assert r.letter_md.read_text() == "Dear Acme" and (r.dir / "meta.json").is_file() and (r.dir / "job_posting.md").is_file()
        app = s.get(Application, 1)
        assert app is not None and app.status == Status.pack_ready


def test_finalize_pack_rejects_banned_phrases_before_pdf(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    pdf = FakePdf([1])
    with Session() as s, pytest.raises(JobgentError, match="passionate"):
        finalize_pack(settings, s, store, s.get(Job, 1), _cv(), "I am passionate about AI.", tone="warm", pdf=pdf)
    assert pdf.calls == 0


def test_finalize_pack_rejects_invented_numbers(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(InventedClaimError, match="37%"):
        finalize_pack(settings, s, store, s.get(Job, 1), _cv("Raised revenue by 37%"), "Dear Acme", tone="warm", pdf=FakePdf([1]))


def test_finalize_pack_asks_to_shorten_when_two_pages(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(JobgentError, match="(?i)shorten"):
        finalize_pack(settings, s, store, s.get(Job, 1), _cv(), "Dear Acme", tone="warm", pdf=FakePdf([2]))


@pytest.fixture
def fake_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(html: str, out: Path, fit: bool = False) -> int:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-fake")
        return 1
    monkeypatch.setattr("jobgent.pack.create.html_to_pdf", fake)


def test_agent_tools_are_listed(services):
    async def go():
        async with Client(build_mcp(services)) as c:
            return {t.name for t in await c.list_tools()}
    assert AGENT_TOOLS <= asyncio.run(go())


def test_evaluate_prompt_and_submit_need_no_llm(services):
    def boom():
        raise AssertionError("agent mode must not call Jobgent's own model")
    services.llm_factory = boom
    mcp = build_mcp(services)
    prompt = call(mcp, "evaluate_prompt", {"job_id": 1})
    assert prompt["done"] is False and "untrusted data" in prompt["posting"]
    assert {"extracted_schema", "mapped_schema", "instructions", "profile", "gates"} <= prompt.keys()
    result = call(mcp, "evaluate_submit", {"job_id": 1, "extracted": REQS.model_dump(), "mapped": {"items": []}})
    assert result["verdict"] == "skip" and len(result["requirements"]) == 4
    assert all(r["status"] == "gap" for r in result["requirements"])


def test_evaluate_prompt_short_circuits_on_a_failed_gate(services):
    with services.sessionmaker() as s:
        j = s.get(Job, 1)
        assert j is not None
        j.dutch_required = True
        s.commit()
    prompt = call(build_mcp(services), "evaluate_prompt", {"job_id": 1})
    assert prompt["done"] is True and prompt["verdict"] == "skip" and "Dutch" in prompt["verdict_reason"]


def test_pack_prompt_and_submit(services, fake_pdf):
    services.llm_factory = lambda: (_ for _ in ()).throw(AssertionError("no model calls in agent mode"))
    mcp = build_mcp(services)
    prompt = call(mcp, "pack_prompt", {"job_id": 1})
    assert {"cv_schema", "cv_instructions", "letter_instructions", "profile", "posting", "rules"} <= prompt.keys()
    assert "{voice}" not in prompt["letter_instructions"] and "{tone}" not in prompt["letter_instructions"]
    result = call(mcp, "pack_submit", {"job_id": 1, "cv": _cv().model_dump(), "letter": "Dear Acme team,\n\nI build tools."})
    assert Path(result["cv_pdf"]).is_file()
    with services.sessionmaker() as s:
        app = s.get(Application, 1)
        assert app is not None and app.status == Status.pack_ready


def test_pack_submit_names_the_invented_number(services, fake_pdf):
    with pytest.raises(Exception, match="37%"):
        call(build_mcp(services), "pack_submit", {"job_id": 1, "cv": _cv("Raised revenue by 37%").model_dump(), "letter": "Dear Acme"})
