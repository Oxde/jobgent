from datetime import date

import pytest

from stageone.errors import InventedClaimError
from stageone.llm import FakeLLM
from stageone.pack.verify import VerifyOutput, verify_against_profile
from stageone.profile.models import Personal, Profile, SearchProfile


def profile() -> Profile:
    return Profile(personal=Personal(name="T"), search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def test_unsupported_claim_raises_with_claim_named():
    llm = FakeLLM([VerifyOutput(unsupported_claims=["Kubernetes experience"])])
    with pytest.raises(InventedClaimError, match="Kubernetes") as info:
        verify_against_profile(llm, "m", profile(), "I have Kubernetes experience.")
    assert info.value.claims == ["Kubernetes experience"]


def test_clean_text_passes():
    llm = FakeLLM([VerifyOutput(unsupported_claims=[])])
    assert verify_against_profile(llm, "m", profile(), "I study maths.") is None
