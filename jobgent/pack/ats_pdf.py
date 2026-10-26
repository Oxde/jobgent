"""What an applicant tracking system sees: the PDF's text layer, not our HTML."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel
from pypdf import PdfReader


class AtsPdfCheck(BaseModel):
    ok: bool
    problems: list[str]
    keywords: dict[str, list[str]] = {}


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def _norm_phone(s: str) -> str:
    return re.sub(r"\D", "", s)


def ats_check_text(text: str, email: str, phone: str) -> AtsPdfCheck:
    problems: list[str] = []
    if email and email.lower() not in text.lower():
        problems.append(f"Your email ({email}) is not readable as text in the PDF.")
    if phone and _norm_phone(phone) and _norm_phone(phone) not in _norm_phone(text):
        problems.append(f"Your phone number ({phone}) is not readable as text in the PDF.")
    if "(cid:" in text or "�" in text:
        problems.append("Some characters come out unreadable (font not embedded properly).")
    if re.search(r"\d{4}\s*[–—]\s*[A-Za-z0-9]", text):
        problems.append("Date ranges use an en/em dash; some ATS (e.g. Workday) drop them. Plain hyphens are safer.")
    return AtsPdfCheck(ok=not problems, problems=problems)


def keyword_buckets(pdf_text: str, profile_text: str, keywords: list[str]) -> dict[str, list[str]]:
    """covered: in the CV · missing_but_in_profile: you have it, the CV does not say it · gap: not in your profile."""
    def has(text: str, k: str) -> bool:
        return re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])", text.lower()) is not None

    out: dict[str, list[str]] = {"covered": [], "missing_but_in_profile": [], "gap": []}
    for k in keywords:
        if has(pdf_text, k):
            out["covered"].append(k)
        elif has(profile_text, k):
            out["missing_but_in_profile"].append(k)
        else:
            out["gap"].append(k)
    return out
