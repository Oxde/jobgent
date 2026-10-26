"""The list of companies whose own job boards we read directly."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

ATS = Literal["greenhouse", "lever", "recruitee", "homerun", "ashby", "workable"]


class Company(BaseModel):
    name: str
    ats: ATS
    board: str


class _CompaniesFile(BaseModel):
    companies: list[Company]


def load_companies(path: Path) -> list[Company]:
    if not path.is_file():
        raise FileNotFoundError(f"Companies file not found: {path}")
    data = yaml.safe_load(path.read_text())
    return _CompaniesFile.model_validate(data).companies
