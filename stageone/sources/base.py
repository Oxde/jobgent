"""Common contract for every job source."""

from __future__ import annotations

from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Protocol

import httpx
from pydantic import BaseModel


class RawJob(BaseModel):
    source: str
    external_id: str
    url: str
    title: str
    company: str
    location: str | None
    description: str
    posted_at: datetime | None


class SourceResult(BaseModel):
    source: str
    jobs: list[RawJob]
    error: str | None = None


class Source(Protocol):
    name: str

    def fetch(self, client: httpx.Client) -> list[RawJob]: ...


_BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "ul", "ol"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Plain text from HTML (handles double-escaped HTML as Greenhouse ships it)."""
    text = html
    if "<" not in text and "&lt;" in text:
        text = unescape(text)
    parser = _TextExtractor()
    parser.feed(text)
    joined = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in joined.splitlines()]
    return "\n".join(line for line in lines if line)
