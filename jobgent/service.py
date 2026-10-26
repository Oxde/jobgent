"""Shared construction for the MCP server, the CLI and the web UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session, sessionmaker

from jobgent.config import Settings, load_settings
from jobgent.db import open_db
from jobgent.llm import LLM, AnthropicLLM
from jobgent.profile.store import ProfileStore


@dataclass
class Services:
    settings: Settings
    sessionmaker: sessionmaker[Session]
    store: ProfileStore
    llm_factory: Callable[[], LLM]
    http_client_factory: Callable[[], httpx.Client]


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or load_settings()
    settings.home.mkdir(parents=True, exist_ok=True)

    def llm_factory() -> LLM:
        return AnthropicLLM(api_key=settings.require("ANTHROPIC_API_KEY"))

    return Services(
        settings=settings,
        sessionmaker=open_db(settings.db_path),
        store=ProfileStore(settings.profile_dir),
        llm_factory=llm_factory,
        http_client_factory=lambda: httpx.Client(follow_redirects=True),
    )
