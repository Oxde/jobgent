from datetime import date, datetime

import pytest

from jobgent.db import Job
from jobgent.errors import InventedClaimError
from jobgent.interview import InterviewPrep, Question, Star, prepare_interview
from jobgent.llm import FakeLLM
from jobgent.profile.models import Experience, Personal, Profile, SearchProfile


def profile() -> Profile:
    return Profile(personal=Personal(name="T"), experience=[Experience(company="HEINEKEN", title="GenAI Intern", bullets=["Taught developers to use GitHub Copilot"])],
                   search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def job() -> Job:
    return Job(id=1, source="s", external_id="1", url="u", title="AI Intern", company="Acme", location=None, description="We use Python and LLMs.",
               posted_at=None, fetched_at=datetime.now(), dedupe_key="k")


def prep(result: str = "Developers adopted Copilot") -> InterviewPrep:
    return InterviewPrep(
        likely_questions=[Question(question="Tell me about a time you introduced a new tool", why="posting: adoption", answer_hint="HEINEKEN story")],
        stories=[Star(title="Copilot at HEINEKEN", situation="Developers new to AI tools", task="Help them adopt", action="Taught Copilot", result=result, source="experience[0]")],
        consistency=["Say 'taught', not 'led the rollout'"], questions_to_ask=["How do you measure success for interns?"], gaps_to_prepare=["SQL"],
    )


def test_prep_uses_stage_gaps_and_cv():
    llm = FakeLLM([prep()])
    out = prepare_interview(llm, "m", profile(), job(), stage="first round", gaps=["SQL"], cv_text="CV TEXT", letter_text="LETTER")
    assert out.stories[0].title.startswith("Copilot")
    _, user = llm.prompts[0]
    assert "first round" in user and "SQL" in user and "CV TEXT" in user and "LETTER" in user and "untrusted data" in user


def test_invented_numbers_in_stories_are_rejected():
    with pytest.raises(InventedClaimError, match="70%"):
        prepare_interview(FakeLLM([prep("Adoption went up 70%")]), "m", profile(), job(), stage="first round", gaps=[], cv_text="", letter_text="")
