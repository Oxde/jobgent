"""Settings: where data lives, which models to use, which secrets exist."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from stageone.errors import MissingSecretError

SecretName = Literal["ANTHROPIC_API_KEY", "APIFY_TOKEN"]

DEFAULT_SECRETS_FILE = Path.home() / ".config" / "secrets" / "env"
DEFAULT_HOME = Path.home() / ".stageone"
FAST_MODEL = "claude-haiku-4-5-20251001"
SMART_MODEL = "claude-sonnet-4-5"
DEFAULT_LINKEDIN_ACTOR = "meka.im~linkedin-jobs-scraper"


class Settings(BaseModel):
    home: Path
    anthropic_api_key: str | None = Field(repr=False, exclude=True)
    apify_token: str | None = Field(repr=False, exclude=True)
    fast_model: str
    smart_model: str
    linkedin_actor: str
    companies_file: Path

    @property
    def db_path(self) -> Path:
        return self.home / "stageone.db"

    @property
    def profile_dir(self) -> Path:
        return self.home / "profile"

    @property
    def applications_dir(self) -> Path:
        return self.home / "applications"

    def require(self, name: SecretName) -> str:
        value = self.anthropic_api_key if name == "ANTHROPIC_API_KEY" else self.apify_token
        if not value:
            raise MissingSecretError(name)
        return value


def _parse_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_settings(
    env: Mapping[str, str] | None = None,
    secrets_file: Path | None = None,
) -> Settings:
    """Precedence: explicit `env` > process environment > secrets file."""
    merged = _parse_secrets_file(secrets_file or DEFAULT_SECRETS_FILE)
    merged.update(os.environ)
    if env is not None:
        merged.update(env)

    def get(name: str) -> str | None:
        value = merged.get(name)
        return value if value else None

    home = Path(get("STAGEONE_HOME") or DEFAULT_HOME).expanduser()
    return Settings(
        home=home,
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
        apify_token=get("APIFY_TOKEN"),
        fast_model=get("STAGEONE_FAST_MODEL") or FAST_MODEL,
        smart_model=get("STAGEONE_SMART_MODEL") or SMART_MODEL,
        linkedin_actor=get("STAGEONE_LINKEDIN_ACTOR") or DEFAULT_LINKEDIN_ACTOR,
        companies_file=Path(get("STAGEONE_COMPANIES") or Path(__file__).parent.parent / "data" / "companies.yaml"),
    )
