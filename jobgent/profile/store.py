"""Reads and writes the profile directory: profile.yaml, voice.md, notes.md, master_cv.html."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import yaml

from jobgent.profile.models import (
    Education,
    Experience,
    Language,
    Personal,
    Profile,
    Project,
    SearchProfile,
    Skill,
)

_DEFAULT_VOICE = Path(__file__).parent / "default_voice.md"
_PATH_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def _parse_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    pos = 0
    for m in _PATH_TOKEN.finditer(path):
        if m.start() != pos and path[pos:m.start()] != ".":
            raise KeyError(path)
        tokens.append(m.group(1) if m.group(1) is not None else int(m.group(2)))
        pos = m.end()
    if pos != len(path) or not tokens:
        raise KeyError(path)
    return tokens


class ProfileStore:
    def __init__(self, profile_dir: Path) -> None:
        self.dir = profile_dir
        self.profile_path = profile_dir / "profile.yaml"
        self.voice_path = profile_dir / "voice.md"
        self.notes_path = profile_dir / "notes.md"
        self.cv_path = profile_dir / "master_cv.html"

    def exists(self) -> bool:
        return self.profile_path.is_file()

    def load(self) -> Profile:
        if not self.exists():
            raise FileNotFoundError(
                f"No profile at {self.profile_path}. Run profile_import_jobkiller (or `jobgent profile import`) first."
            )
        data = yaml.safe_load(self.profile_path.read_text())
        return Profile.model_validate(data)

    def save(self, profile: Profile) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(
            yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        )

    def update(self, path: str, value: object) -> Profile:
        data = self.load().model_dump(mode="json")
        tokens = _parse_path(path)
        node: object = data
        for token in tokens[:-1]:
            node = _child(node, token, path)
        last = tokens[-1]
        if isinstance(node, dict) and isinstance(last, str):
            if last not in node:
                raise KeyError(f"{path} (valid keys here: {', '.join(node)})")
            node[last] = _coerce(node[last], value)
        elif isinstance(node, list) and isinstance(last, int) and last < len(node):
            node[last] = _coerce(node[last], value)
        else:
            raise KeyError(path)
        profile = Profile.model_validate(data)
        self.save(profile)
        return profile

    def import_jobkiller(self, json_path: Path) -> Profile:
        raw = json.loads(json_path.read_text())
        info = raw["user_info"] if "user_info" in raw else raw
        pi = info.get("personal_information", {})
        skills: list[Skill] = []
        for group in info.get("technical_skills", {}).values():
            evidence = str(group.get("experience") or group.get("description") or "")
            for tool in group.get("tools", []):
                skills.append(Skill(name=str(tool), evidence=evidence))
        year = date.today().year + 1
        profile = Profile(
            verified=False,
            personal=Personal(
                name=str(pi.get("name", "")),
                location=str(pi.get("location", "")),
                email=str(pi.get("email", "")),
                phone=str(pi.get("phone", "")),
                linkedin=str(pi.get("linkedin", "")),
                github=str(pi.get("github", "")),
            ),
            education=[
                Education(
                    institution=str(e.get("institution", "")),
                    degree=str(e.get("degree", "")),
                    period=str(e.get("period", "")),
                    status=str(e.get("status", "")),
                    gpa=str(e.get("gpa", "")),
                    details=str(e.get("details", "")),
                )
                for e in info.get("education", [])
            ],
            experience=[
                Experience(
                    company=str(w.get("company", "")),
                    title=str(w.get("position") or w.get("title", "")),
                    period=str(w.get("period", "")),
                    bullets=[str(b) for b in w.get("responsibilities") or w.get("bullets") or []],
                )
                for w in info.get("work_experience", [])
            ],
            projects=[
                Project(
                    name=str(p.get("name", "")),
                    description=str(p.get("description", "")),
                    tech=[str(t) for t in p.get("technologies") or p.get("tech") or []],
                    link=str(p.get("link", "")),
                )
                for p in info.get("projects", [])
            ],
            skills=skills,
            languages=[
                Language(name=str(l.get("language") or l.get("name", "")), level=str(l.get("level", "")))
                for l in info.get("languages", [])
            ],
            search=SearchProfile(start_from=date(year, 2, 1), start_to=date(year, 4, 1)),
        )
        self.save(profile)
        return profile

    def voice(self) -> str:
        if self.voice_path.is_file():
            return self.voice_path.read_text()
        return _DEFAULT_VOICE.read_text()

    def set_voice(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.voice_path.write_text(text)

    def notes_append(self, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.notes_path.open("a") as f:
            f.write(f"\n## {stamp}\n\n{text.strip()}\n")

    def master_cv_path(self) -> Path | None:
        return self.cv_path if self.cv_path.is_file() else None

    def set_master_cv(self, html: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cv_path.write_text(html)


def _coerce(current: object, value: object) -> object:
    """Text fields keep the text as given ('+31…' stays a string); other fields parse YAML from a string."""
    if isinstance(current, str):
        return value if isinstance(value, str) else str(value)
    if isinstance(value, str):
        return yaml.safe_load(value)
    return value


def _child(node: object, token: str | int, path: str) -> object:
    if isinstance(node, dict) and isinstance(token, str) and token in node:
        return node[token]
    if isinstance(node, list) and isinstance(token, int) and token < len(node):
        return node[token]
    raise KeyError(path)
