"""Keyword match between a posting and a CV text: the part of 'ATS' that is real and checkable."""

from __future__ import annotations

import re

from pydantic import BaseModel


class AtsReport(BaseModel):
    percent: int
    matched: list[str]
    missing: list[str]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+#.]+", " ", text.lower())


def _present(cv: str, keyword: str) -> bool:
    k = _norm(keyword).strip()
    if not k:
        return False
    # allow a trailing s/es on the last word so "pipeline" matches "pipelines"
    pattern = r"(?<![a-z0-9])" + re.escape(k) + r"(?:e?s)?(?![a-z0-9])"
    return re.search(pattern, cv) is not None


def ats_report(cv_text: str, keywords: list[str]) -> AtsReport:
    cv = _norm(cv_text)
    matched = [k for k in keywords if _present(cv, k)]
    missing = [k for k in keywords if k not in matched]
    percent = round(100 * len(matched) / len(keywords)) if keywords else 0
    return AtsReport(percent=percent, matched=matched, missing=missing)
