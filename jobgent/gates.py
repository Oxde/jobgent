"""Checks before any scoring. Deterministic: each gate passes, flags (proceed with a warning) or fails (skip)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from jobgent.db import Job
from jobgent.guard import sanitize_posting
from jobgent.profile.models import Profile
from jobgent.views import in_cities

GateStatus = Literal["pass", "flag", "fail"]


class Gate(BaseModel):
    name: str
    status: GateStatus
    reason: str


_WORK_RIGHTS = re.compile(
    r"(right to work|eligible to work|work permit|without (visa )?sponsorship|eu (citizen|passport)|"
    r"valid (work|residence) permit|werkvergunning|no visa sponsorship)",
    re.IGNORECASE,
)
_RED_FLAGS: list[tuple[str, re.Pattern[str]]] = [
    ("unpaid", re.compile(r"\b(unpaid|no (internship )?(allowance|compensation|stipend)|onbetaald|geen stagevergoeding)\b", re.I)),
    ("fee", re.compile(r"\b(placement fee|registration fee|you (will )?pay (a|an) fee|fee (of|is) [€$]?\d+|kosten voor de kandidaat)\b", re.I)),
    ("agency", re.compile(r"\b(on behalf of our client|our client is looking|recruitment agency)\b", re.I)),
]


def run_gates(job: Job, profile: Profile) -> list[Gate]:
    gates: list[Gate] = []

    if job.live_status == "closed":
        gates.append(Gate(name="open", status="fail", reason="The posting is closed or removed."))
    else:
        gates.append(Gate(name="open", status="pass", reason="Still listed." if job.live_status == "open" else "Not checked yet; assumed open."))

    if job.dutch_required:
        gates.append(Gate(name="language", status="fail", reason="The posting requires Dutch."))
    elif job.dutch_plus:
        gates.append(Gate(name="language", status="flag", reason="Dutch is a plus, not required."))
    else:
        gates.append(Gate(name="language", status="pass", reason="Works in English."))

    if in_cities(job.location, profile.search):
        gates.append(Gate(name="location", status="pass", reason=f"{job.location or 'Location not stated'}."))
    else:
        gates.append(Gate(name="location", status="fail", reason=f"{job.location} is outside {', '.join(profile.search.locations)}."))

    if _WORK_RIGHTS.search(job.description) and profile.preferences.eu_citizen is not True:
        why = "you are not an EU citizen" if profile.preferences.eu_citizen is False else "your work rights are not in your profile"
        gates.append(Gate(name="work_rights", status="flag", reason=f"The posting asks about the right to work and {why}."))
    else:
        gates.append(Gate(name="work_rights", status="pass", reason="No work-rights requirement that blocks you."))

    hits = [name for name, pattern in _RED_FLAGS if pattern.search(job.description)]
    if hits:
        labels = {"unpaid": "unpaid internship", "fee": "asks the candidate to pay a fee", "agency": "posted by an agency for an unnamed client"}
        gates.append(Gate(name="red_flags", status="flag", reason="; ".join(labels[h] for h in hits) + "."))
    else:
        gates.append(Gate(name="red_flags", status="pass", reason="No red flags found."))

    _, integrity = sanitize_posting(job.description)
    if integrity:
        gates.append(Gate(name="integrity", status="flag", reason="Posting text: " + "; ".join(integrity) + "."))
    else:
        gates.append(Gate(name="integrity", status="pass", reason="Posting text looks normal."))
    return gates
