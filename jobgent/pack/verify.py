"""The no-invention gate: every claim in generated text must be backed by the profile."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from jobgent.errors import InventedClaimError
from jobgent.llm import LLM
from jobgent.profile.models import Profile
from jobgent.score import profile_for_prompt

_PROMPT = (Path(__file__).parent.parent / "prompts" / "verify.md").read_text()


class VerifyOutput(BaseModel):
    unsupported_claims: list[str] = Field(default_factory=list)


def verify_against_profile(llm: LLM, model: str, profile: Profile, text: str) -> None:
    user = f"## Profile\n{profile_for_prompt(profile)}\n\n## Generated text\n{text}"
    out = llm.complete_json(model=model, system=_PROMPT, user=user, schema=VerifyOutput)
    if out.unsupported_claims:
        raise InventedClaimError(out.unsupported_claims)
