"""Golden evals: synthetic postings with expected gates and verdicts, replayed with recorded model output ($0)."""

from pathlib import Path

import pytest

from jobgent.db import open_db
from jobgent.evals import CASES_DIR, case_job, load_cases, recorded_llm
from jobgent.demo import PROFILE
from jobgent.evaluate import evaluate_job

CASES = load_cases(CASES_DIR)


def test_there_are_ten_cases():
    assert len(CASES) == 10


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_golden_case(case, tmp_path):
    s = open_db(tmp_path / "t.db")()
    job = case_job(case)
    s.add(job)
    s.commit()
    llm = recorded_llm(case)
    ev = evaluate_job(s, llm, "recorded", PROFILE, job)
    gates = {g["name"]: g["status"] for g in ev.gates}
    for name, status in case.expect.gates.items():
        assert gates[name] == status, f"{case.id}: gate {name} is {gates[name]}, expected {status}"
    assert ev.verdict == case.expect.verdict, f"{case.id}: verdict {ev.verdict} ({ev.verdict_reason})"
    assert llm.calls == case.expect.ai_calls
