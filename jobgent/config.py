"""Settings: where data lives, which models to use, which secrets exist."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from jobgent.errors import MissingSecretError

SecretName = Literal["ANTHROPIC_API_KEY", "APIFY_TOKEN", "KIE_API_KEY"]

DEFAULT_SECRETS_FILE = Path.home() / ".config" / "secrets" / "env"
DEFAULT_DOTENV_FILE = Path(__file__).parent.parent / ".env"  # <repo>/.env, git-ignored
DEFAULT_HOME = Path.home() / ".jobgent"
FAST_MODEL = "claude-haiku-4-5-20251001"
SMART_MODEL = "claude-sonnet-4-5"
KIE_MODEL = "claude-sonnet-4-5"  # the model KIE documents on its Anthropic-compatible endpoint
DEFAULT_LINKEDIN_ACTOR = "meka.im~linkedin-jobs-scraper"


class Settings(BaseModel):
    home: Path
    anthropic_api_key: str | None = Field(repr=False, exclude=True)
    apify_token: str | None = Field(repr=False, exclude=True)
    kie_api_key: str | None = Field(default=None, repr=False, exclude=True)
    fast_model: str
    smart_model: str
    linkedin_actor: str
    linkedin_mode: str  # auto (Apify if a token is set, else guest search) | apify | guest | off
    companies_file: Path

    @property
    def db_path(self) -> Path:
        return self.home / "jobgent.db"

    @property
    def profile_dir(self) -> Path:
        return self.home / "profile"

    @property
    def applications_dir(self) -> Path:
        return self.home / "applications"

    @property
    def llm_provider(self) -> str | None:
        """anthropic if its key is set, else kie (Claude through KIE's Anthropic-compatible API), else none."""
        if self.anthropic_api_key:
            return "anthropic"
        if self.kie_api_key:
            return "kie"
        return None

    def require(self, name: SecretName) -> str:
        value = {"ANTHROPIC_API_KEY": self.anthropic_api_key, "APIFY_TOKEN": self.apify_token, "KIE_API_KEY": self.kie_api_key}[name]
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
    dotenv_file: Path | None = None,
) -> Settings:
    """Precedence: explicit `env` > process environment > <repo>/.env > ~/.config/secrets/env."""
    merged = _parse_secrets_file(secrets_file or DEFAULT_SECRETS_FILE)
    merged.update({k: v for k, v in _parse_secrets_file(dotenv_file or DEFAULT_DOTENV_FILE).items() if v})
    merged.update(os.environ)
    if env is not None:
        merged.update(env)

    def get(name: str) -> str | None:
        value = merged.get(name)
        return value if value else None

    home = Path(get("JOBGENT_HOME") or DEFAULT_HOME).expanduser()
    return Settings(
        home=home,
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
        apify_token=get("APIFY_TOKEN"),
        kie_api_key=get("KIE_API_KEY"),
        fast_model=get("JOBGENT_FAST_MODEL") or (FAST_MODEL if get("ANTHROPIC_API_KEY") or not get("KIE_API_KEY") else KIE_MODEL),
        smart_model=get("JOBGENT_SMART_MODEL") or (SMART_MODEL if get("ANTHROPIC_API_KEY") or not get("KIE_API_KEY") else KIE_MODEL),
        linkedin_actor=get("JOBGENT_LINKEDIN_ACTOR") or DEFAULT_LINKEDIN_ACTOR,
        linkedin_mode=(get("JOBGENT_LINKEDIN") or "auto").lower(),
        companies_file=Path(get("JOBGENT_COMPANIES") or Path(__file__).parent.parent / "data" / "companies.yaml"),
    )
