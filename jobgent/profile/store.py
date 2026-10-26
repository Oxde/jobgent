"""Reads and writes the profile directory: profile.yaml, voice.md, notes.md, master_cv.html."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path

import yaml
from pydantic import BaseModel

from jobgent.profile.models import (
    Education,
    Experience,
    Language,
    Personal,
    Preferences,
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

    def append(self, section: str, item: dict[str, object]) -> Profile:
        data = self.load().model_dump(mode="json")
        target = data.get(section)
        if not isinstance(target, list):
            raise KeyError(f"{section} is not a list section (lists: {', '.join(k for k, v in data.items() if isinstance(v, list))})")
        target.append(item)
        profile = Profile.model_validate(data)
        self.save(profile)
        return profile

    def remove(self, section: str, index: int) -> Profile:
        data = self.load().model_dump(mode="json")
        target = data.get(section)
        if not isinstance(target, list) or not 0 <= index < len(target):
            raise KeyError(f"{section}[{index}] does not exist")
        del target[index]
        profile = Profile.model_validate(data)
        self.save(profile)
        return profile

    def import_any(self, path: Path) -> Profile:
        """A JobKiller user_info .json, or a CV .html made by JobKiller."""
        if path.suffix.lower() == ".json":
            return self.import_jobkiller(path)
        if path.suffix.lower() in (".html", ".htm"):
            return self.import_jobkiller_html(path)
        raise ValueError(f"Cannot import {path.name}: expected a JobKiller .json profile or a CV .html, got {path.suffix or 'no extension'}")

    def import_jobkiller_html(self, html_path: Path) -> Profile:
        """Import a CV made by the JobKiller MCP (its fixed class names: name, job, education-item, skills-content...).
        Keeps languages, search and preferences from the current profile; leaves verified=false."""
        doc = html_path.read_text()
        current = self.load() if self.exists() else None

        def text(fragment: str) -> str:
            fragment = re.sub(r"<br\s*/?>", " ", fragment)
            return " ".join(unescape(re.sub(r"<[^>]+>", "", fragment)).split())

        def first(cls: str, scope: str = doc) -> str:
            m = re.search(rf'class="{cls}"[^>]*>(.*?)</(?:div|span|td)>', scope, re.S)
            return text(m.group(1)) if m else ""

        def blocks(cls: str) -> list[str]:
            starts = [m.start() for m in re.finditer(rf'<div class="{cls}">', doc)]
            ends = starts[1:] + [len(doc)]
            out = []
            for a, b in zip(starts, ends):
                chunk = doc[a:b]
                cut = chunk.find('class="section-title"')
                out.append(chunk[:cut] if cut > 0 else chunk)
            return out

        def split2(value: str) -> tuple[str, str]:
            left, sep, right = value.partition(" | ")
            return (left.strip(), right.strip()) if sep else ("", value.strip())

        contact_lines = [text(d) for td in re.findall(r'<td class="[^"]*contact-info[^"]*">(.*?)</td>', doc, re.S) for d in re.findall(r"<div>(.*?)</div>", td, re.S)]
        personal = Personal(name=first("name"), headline=first("professional-title"))
        for line in contact_lines:
            if line.lower().startswith("location:"):
                personal.location = line.split(":", 1)[1].strip()
            elif line.lower().startswith("date of birth:"):
                personal.birth_date = line.split(":", 1)[1].strip()
            elif line.lower().startswith(("number:", "phone:")):
                personal.phone = line.split(":", 1)[1].strip()
            elif "@" in line and " " not in line:
                personal.email = line
        for href in re.findall(r'href="([^"]+)"', doc[: doc.find('class="objective"') if 'class="objective"' in doc else len(doc)]):
            if "linkedin.com" in href:
                personal.linkedin = href
            elif "github.com" in href:
                personal.github = href

        experience: list[Experience] = []
        for b in blocks("job"):
            company, title = split2(first("job-title", b))
            location, period = split2(first("job-date", b))
            bullets = [text(li) for li in re.findall(r"<li>(.*?)</li>", b, re.S)]
            experience.append(Experience(company=company, title=title, location=location, period=period, bullets=bullets))

        education: list[Education] = []
        for b in blocks("education-item"):
            header = re.search(r'class="degree-header">\s*<div>(.*?)</div>', b, re.S)
            institution, degree = split2(text(header.group(1)) if header else "")
            location, period = split2(first("degree-date", b))
            details = first("degree-details", b)
            gpa = ""
            gm = re.match(r"GPA:\s*([^,]+),?\s*(.*)", details)
            if gm:
                gpa, details = gm.group(1).strip(), gm.group(2).strip()
            education.append(Education(institution=institution, degree=degree, location=location, period=period, gpa=gpa, details=details))

        skills_html = re.search(r'class="skills-content">(.*?)</div>', doc, re.S)
        skills: list[Skill] = []
        skills_note = ""
        if skills_html:
            raw = skills_html.group(1)
            note = re.search(r'class="skills-highlight">(.*?)</span>', raw, re.S)
            skills_note = text(note.group(1)) if note else ""
            for part in re.split(r"\s*•\s*|\s{2,}", unescape(re.sub(r"<[^>]+>", "", raw.split("|")[0]))):
                name = part.strip()
                if name and not any(s.name == name for s in skills):
                    skills.append(Skill(name=name))

        projects: list[Project] = []
        plist = re.search(r'class="projects-list">(.*?)</ul>', doc, re.S)
        for li in re.findall(r"<li>(.*?)</li>", plist.group(1) if plist else "", re.S):
            link = re.search(r'href="([^"]+)"', li)
            title_html = re.search(r'class="project-title">(.*?)</span>', li, re.S)
            name = text(title_html.group(1)) if title_html else ""
            rest = text(li[title_html.end():]) if title_html else text(li)
            projects.append(Project(name=name, description=rest.lstrip(":").strip(), link=link.group(1) if link else ""))

        year = date.today().year + 1
        profile = Profile(
            verified=False,
            personal=personal,
            summary=first("objective"),
            skills_note=skills_note,
            experience=experience,
            education=education,
            skills=skills,
            projects=projects,
            languages=current.languages if current else [],
            preferences=current.preferences if current else Preferences(),
            search=current.search if current else SearchProfile(start_from=date(year, 2, 1), start_to=date(year, 4, 1)),
        )
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
        for w in info.get("work_experience", []):
            for tool in _as_list(w.get("technologies")):
                if not any(sk.name == str(tool) for sk in skills):
                    skills.append(Skill(name=str(tool), evidence=str(w.get("position") or w.get("title", ""))))
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
            experience=[_experience(w) for w in info.get("work_experience", [])],
            projects=[
                Project(
                    name=str(p.get("name") or p.get("title", "")),
                    description=str(p.get("description", "")),
                    tech=[str(t) for t in p.get("technologies") or p.get("tech") or []],
                    link=str(p.get("link") or p.get("url", "")),
                )
                for p in info.get("projects", [])
            ],
            skills=skills,
            languages=[_language(l) for l in info.get("languages", [])],
            search=SearchProfile(start_from=date(year, 2, 1), start_to=date(year, 4, 1)),
        )
        objectives = info.get("career_objectives") or {}
        roles = [str(r) for r in objectives.get("desired_roles") or []]
        if roles:
            profile.search.keywords = roles + [k for k in profile.search.keywords if k not in roles]
        self.save(profile)
        notes: list[str] = []
        if objectives.get("goal"):
            notes.append(f"Career goal (imported): {objectives['goal']}")
        for item in info.get("soft_skills") or []:
            notes.append(f"Soft skill (imported): {item}")
        if notes:
            self.notes_append("\n".join(notes))
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

    def version(self) -> str:
        """Changes whenever profile.yaml or voice.md changes, by any writer (web, MCP, CLI, hand edit)."""
        stamps = [str(f.stat().st_mtime_ns) for f in (self.profile_path, self.voice_path) if f.is_file()]
        return "-".join(stamps) or "0"

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


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _language(value: object) -> Language:
    """Either {"language": "English", "level": "C1"} or a string like "English (C1)"."""
    if isinstance(value, dict):
        return Language(name=str(value.get("language") or value.get("name", "")), level=str(value.get("level", "")))
    text = str(value).strip()
    for d in (": ", " – ", " - "):
        if d in text:
            name, _, level = text.partition(d)
            return Language(name=name.strip(), level=level.strip())
    name, sep, rest = text.partition("(")
    if sep:
        return Language(name=name.strip(), level=rest.strip().removesuffix(")").strip())
    return Language(name=text)


def _experience(w: dict[str, object]) -> Experience:
    """JobKiller stored jobs as title/period/description/achievements/technologies, sometimes 'Title at Company'."""
    title = str(w.get("position") or w.get("title", ""))
    company = str(w.get("company", ""))
    if not company and " at " in title:
        title, _, company = title.partition(" at ")
    bullets = [str(b) for b in _as_list(w.get("responsibilities") or w.get("bullets"))]
    if w.get("description"):
        bullets.insert(0, str(w["description"]))
    bullets += [str(a) for a in _as_list(w.get("achievements"))]
    tech = [str(t) for t in _as_list(w.get("technologies"))]
    if tech:
        bullets.append("Tools: " + ", ".join(tech))
    return Experience(company=company, title=title.strip(), period=str(w.get("period", "")), bullets=bullets)


def _child(node: object, token: str | int, path: str) -> object:
    if isinstance(node, dict) and isinstance(token, str) and token in node:
        return node[token]
    if isinstance(node, list) and isinstance(token, int) and token < len(node):
        return node[token]
    raise KeyError(path)


class ChecklistItem(BaseModel):
    label: str
    done: bool
    hint: str


def completeness(p: Profile) -> list[ChecklistItem]:
    """What the generated CVs and letters depend on. Every page shows this until it is all green."""
    return [
        ChecklistItem(label="Headline", done=bool(p.personal.headline), hint="One line under your name, e.g. 'Applied Mathematics & Data Science student'."),
        ChecklistItem(label="Summary", done=len(p.summary) >= 60, hint="Two or three sentences about what you do and want."),
        ChecklistItem(label="Contact details", done=bool(p.personal.email and p.personal.location), hint="Email and city, at least."),
        ChecklistItem(label="Education with dates", done=bool(p.education) and all(e.period for e in p.education), hint="Each entry needs a period."),
        ChecklistItem(label="At least one project or job", done=bool(p.projects or p.experience), hint="This is what the CV is built from."),
        ChecklistItem(label="Skills with evidence", done=len([s for s in p.skills if s.evidence]) >= 5, hint="Five or more skills, each with where you used it: the no-invention check relies on this."),
        ChecklistItem(label="Languages", done=bool(p.languages), hint="English level, plus anything else."),
        ChecklistItem(label="Search settings", done=bool(p.search.keywords and p.search.locations), hint="Keywords and locations drive the feed."),
        ChecklistItem(label="Profile verified", done=p.verified, hint="Read it through once, then mark it verified. Packs refuse to run before that."),
    ]


def outline(profile: Profile) -> str:
    """Every editable fact as `path: value`, the paths profile_update accepts."""
    lines: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, list) and node and all(not isinstance(x, (dict, list)) for x in node) and path.endswith(("keywords", "locations", "languages", "internship_types", "tech")):
            lines.append(f"{path}: [{', '.join(str(x) for x in node)}]")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        else:
            lines.append(f"{path}: {node}")

    walk(profile.model_dump(mode="json"), "")
    return "\n".join(lines)
