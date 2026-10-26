"""Deterministic checks on generated text. Numbers must come from the profile or the posting (hard rule);
unknown names and tools are marked for the user to check (soft rule)."""

from __future__ import annotations

import re

from pydantic import BaseModel

_NUMBER = re.compile(r"[$€£]?\d[\d,.]*\s?(?:%|[kKmM]\b|x\b|\+)?")
_NAME = re.compile(r"\b[A-Z][A-Za-z0-9+#.&-]*[A-Za-z0-9+#]\b|\b[A-Z]\b")
_COMMON = {
    "i", "the", "a", "an", "my", "in", "at", "on", "for", "with", "and", "but", "as", "to", "of", "by", "from", "we", "you",
    "your", "our", "this", "that", "these", "it", "its", "is", "are", "was", "dear", "hello", "hi", "best", "regards",
    "kind", "sincerely", "thank", "thanks", "looking", "built", "developed", "taught", "ran", "led", "used", "worked",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
    "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "present",
    "monday", "tuesday", "wednesday", "thursday", "friday", "netherlands", "amsterdam", "english", "dutch",
    "internship", "intern", "team", "summary", "skills", "projects", "education", "experience", "ai", "cv", "please",
    "happy", "currently", "during", "since", "when", "if", "while", "after", "before", "also", "then", "both",
}

BANNED = [
    "i am writing to express my interest", "i am writing to apply", "to whom it may concern", "passionate",
    "team player", "hard-working", "hardworking", "go-getter", "think outside the box", "synergy", "leverage",
    "dynamic", "detail-oriented", "results-driven", "self-starter", "i believe i would be a great fit",
    "perfect fit", "dream job", "just checking in", "fast-paced environment",
]


class FactReport(BaseModel):
    invented_numbers: list[str]
    unverified_names: list[str]


def _digits(token: str) -> str:
    return re.sub(r"\D", "", token)


def fact_check(text: str, corpus: str) -> FactReport:
    corpus_digits = {_digits(m.group(0)) for m in _NUMBER.finditer(corpus)}
    corpus_lower = corpus.lower()
    numbers: list[str] = []
    for m in _NUMBER.finditer(text):
        token = m.group(0).strip().rstrip(".,")
        d = _digits(token)
        if d and d not in corpus_digits and token not in numbers:
            numbers.append(token)
    names: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
        words = list(_NAME.finditer(sentence))
        for i, m in enumerate(words):
            token = m.group(0)
            if i == 0 and m.start() == len(sentence) - len(sentence.lstrip()):
                continue  # first word of a sentence is capitalised anyway
            if token.lower() in _COMMON or token.lower() in corpus_lower or token in names:
                continue
            names.append(token)
    return FactReport(invented_numbers=numbers, unverified_names=names)


def banned_phrases(text: str) -> list[str]:
    lower = text.lower()
    return [p for p in BANNED if p in lower]


def tidy_letter(text: str) -> str:
    """No em dashes (the most recognisable AI tell); normalise spaces."""
    text = re.sub(r"\s*—\s*", ", ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
