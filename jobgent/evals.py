"""Golden evaluation cases (evals/golden/*.yaml): replayed in tests with recorded output, or live with `jobgent eval`."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from jobgent.db import Job
from jobgent.evaluate import Extracted, Mapped
from jobgent.llm import FakeLLM
from jobgent.score import ScoreOutput

CASES_DIR = Path(__file__).parent.parent / "evals" / "golden"


class Classification(BaseModel):
    language: str = "en"
    dutch_required: bool = False
    dutch_plus: bool = False


class Posting(BaseModel):
    title: str
    company: str
    location: str
    description: str
    classification: Classification
    live_status: str | None = None


class Recorded(BaseModel):
    extracted: Extracted
    mapped: Mapped
    score: ScoreOutput


class Expect(BaseModel):
    gates: dict[str, str]
    verdict: str
    ai_calls: int


class Case(BaseModel):
    id: str
    name: str
    posting: Posting
    recorded: Recorded | None
    expect: Expect


def load_cases(folder: Path) -> list[Case]:
    cases = []
    for path in sorted(folder.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        cases.append(Case.model_validate({"id": path.stem, **data}))
    return cases


def case_job(case: Case) -> Job:
    p = case.posting
    return Job(
        source="eval", external_id=case.id, url="", title=p.title, company=p.company, location=p.location, description=p.description,
        posted_at=None, fetched_at=datetime.now(), dedupe_key=case.id, is_internship=True, in_region=True,
        language=p.classification.language, dutch_required=p.classification.dutch_required, dutch_plus=p.classification.dutch_plus,
        classified_at=datetime.now(), live_status=p.live_status,
    )


def recorded_llm(case: Case) -> FakeLLM:
    if case.recorded is None:
        return FakeLLM([])
    return FakeLLM([case.recorded.extracted, case.recorded.mapped, case.recorded.score])
