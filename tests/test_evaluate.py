from datetime import date, datetime

from jobgent.db import Job, open_db
from jobgent.evaluate import (Extracted, Mapped, Mapping, Requirement, decide_verdict, evaluate_job, resolve)
from jobgent.gates import Gate
from jobgent.llm import FakeLLM
from jobgent.profile.models import Experience, Personal, Preferences, Profile, Project, SearchProfile, Skill
from jobgent.score import ScoreOutput


def profile() -> Profile:
    return Profile(
        personal=Personal(name="T"), preferences=Preferences(eu_citizen=True),
        experience=[Experience(company="HEINEKEN", title="GenAI Intern", bullets=["Taught developers to use GitHub Copilot and Claude"])],
        projects=[Project(name="Trading bot", description="Python asyncio bot", tech=["Python", "Docker"])],
        skills=[Skill(name="Python"), Skill(name="SQL"), Skill(name="Docker")],
        search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1), locations=["Amsterdam"]),
    )


def job(**kw: object) -> Job:
    base: dict[str, object] = dict(source="s", external_id="1", url="", title="AI Intern", company="Acme", location="Amsterdam",
                                   description="We want Python, SQL, Kubernetes. Experience with LLM tools.", posted_at=None,
                                   fetched_at=datetime.now(), dedupe_key="k", is_internship=True, language="en",
                                   dutch_required=False, dutch_plus=False, classified_at=datetime.now())
    base.update(kw)
    return Job(**base)


REQS = Extracted(summary="AI intern building internal tools", deadline="15 Nov 2026", requirements=[
    Requirement(text="Python", kind="skill", importance="critical", basis="stated"),
    Requirement(text="SQL", kind="skill", importance="high", basis="stated"),
    Requirement(text="Kubernetes", kind="skill", importance="nice", basis="stated"),
    Requirement(text="Experience with LLM coding tools", kind="experience", importance="critical", basis="inferred"),
])
MAP = Mapped(items=[
    Mapping(index=0, evidence_kind="project", evidence_ref=0, evidence_text="Trading bot in Python"),
    Mapping(index=1, evidence_kind="skill", evidence_ref=1, evidence_text="SQL listed"),
    Mapping(index=2, evidence_kind="none", evidence_ref=None, evidence_text=""),
    Mapping(index=3, evidence_kind="experience", evidence_ref=0, evidence_text="Copilot and Claude at HEINEKEN"),
])


def test_code_decides_coverage_and_demotes_inferred_critical():
    rows = resolve(REQS.requirements, MAP.items, profile())
    assert [(r.text, r.status) for r in rows] == [("Python", "covered"), ("SQL", "partial"), ("Kubernetes", "gap"), ("Experience with LLM coding tools", "covered")]
    assert rows[3].importance == "high"  # inferred can never be critical


def test_model_cannot_point_at_evidence_that_does_not_exist():
    bad = Mapped(items=[Mapping(index=0, evidence_kind="experience", evidence_ref=7, evidence_text="made up")])
    rows = resolve(REQS.requirements[:1], bad.items, profile())
    assert rows[0].status == "gap"


def test_skill_used_in_a_role_or_project_counts_as_covered():
    m = Mapped(items=[Mapping(index=0, evidence_kind="skill", evidence_ref=2, evidence_text="Docker")])
    r = resolve([Requirement(text="Docker", kind="skill", importance="high", basis="stated")], m.items, profile())
    assert r[0].status == "covered"  # Docker is in the trading-bot project's tech


def test_verdict_rules():
    ok = [Gate(name="open", status="pass", reason="")]
    rows = resolve(REQS.requirements, MAP.items, profile())
    assert decide_verdict(ok, rows, 80)[0] == "apply"
    assert decide_verdict(ok, rows, 60)[0] == "consider"
    assert decide_verdict(ok, rows, 40)[0] == "skip"
    assert decide_verdict([Gate(name="language", status="fail", reason="Dutch")], rows, 95)[0] == "skip"
    critical_gap = resolve([Requirement(text="Rust", kind="skill", importance="critical", basis="stated")], [Mapping(index=0, evidence_kind="none")], profile())
    assert decide_verdict(ok, critical_gap, 90)[0] == "consider"


def test_evaluate_job_stores_everything_and_skips_llm_when_a_gate_fails(tmp_path):
    Session = open_db(tmp_path / "t.db")
    score = ScoreOutput(skills=40, role=18, lang_loc=14, timing=10, reasons=["r"], gaps=["Kubernetes"], keywords=["Python"])
    with Session() as s:
        j = job()
        s.add(j)
        s.commit()
        llm = FakeLLM([REQS, MAP, score])
        ev = evaluate_job(s, llm, "m", profile(), j)
        assert ev.verdict == "apply" and ev.coverage > 0 and ev.deadline == "15 Nov 2026" and llm.calls == 3
        assert "untrusted data" in llm.prompts[0][1]
        assert j.evaluation is not None and j.deadline == "15 Nov 2026"

        dutch = job(external_id="2", dutch_required=True)
        s.add(dutch)
        s.commit()
        llm2 = FakeLLM([])
        ev2 = evaluate_job(s, llm2, "m", profile(), dutch)
        assert ev2.verdict == "skip" and llm2.calls == 0 and "Dutch" in ev2.verdict_reason
