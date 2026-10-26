"""The knowledge base about the user. Single source of truth for every CV and letter."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

InternshipType = Literal["graduation", "work_placement", "any"]

DEFAULT_KEYWORDS = [
    "data science intern",
    "AI intern",
    "machine learning intern",
    "software engineering intern",
    "AI automation intern",
]


class Personal(BaseModel):
    name: str
    headline: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""


class Education(BaseModel):
    institution: str
    degree: str
    period: str = ""
    status: str = ""
    gpa: str = ""
    details: str = ""


class Experience(BaseModel):
    company: str
    title: str
    period: str = ""
    bullets: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str
    description: str = ""
    tech: list[str] = Field(default_factory=list)
    link: str = ""


class Skill(BaseModel):
    name: str
    evidence: str = ""


class Language(BaseModel):
    name: str
    level: str = ""


def _default_types() -> list[InternshipType]:
    return ["any"]


class Preferences(BaseModel):
    weekly_goal: int = 10
    template: str = "default"
    remote_ok: bool = True
    eu_citizen: bool | None = None


class SearchProfile(BaseModel):
    keywords: list[str] = Field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    locations: list[str] = Field(default_factory=lambda: ["Netherlands"])
    internship_types: list[InternshipType] = Field(default_factory=_default_types)
    months_min: int = 4
    months_max: int = 6
    paid_required: bool = False
    start_from: date
    start_to: date
    languages: list[str] = Field(default_factory=lambda: ["en"])


class Profile(BaseModel):
    verified: bool = False
    personal: Personal
    summary: str = ""
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    search: SearchProfile
