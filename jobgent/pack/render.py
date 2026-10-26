"""HTML for the CV: a built-in template by id, or the user's own master_cv.html (same Jinja variables)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from jobgent.pack.tailor import TailoredCV
from jobgent.profile.models import Profile

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_TEMPLATE = Path(__file__).parent / "default_cv.html"
DEFAULT_TEMPLATE_ID = "default"
_DATE_DASH = re.compile(r"(\d{4})\s*[\u2013\u2014]\s*")


class TemplateInfo(BaseModel):
    id: str
    name: str
    description: str
    color: str


def list_templates() -> list[TemplateInfo]:
    built_in = [TemplateInfo(id=DEFAULT_TEMPLATE_ID, name="Jobgent", description="Plain, one page, ATS-safe.", color="#15192b")]
    extra = json.loads((TEMPLATES_DIR / "templates.json").read_text())
    return built_in + [TemplateInfo.model_validate(t) for t in extra]


def template_file(template_id: str) -> Path:
    if template_id == DEFAULT_TEMPLATE_ID:
        return DEFAULT_TEMPLATE
    path = TEMPLATES_DIR / f"{template_id}.html"
    if not path.is_file():
        raise KeyError(f"No CV template {template_id!r}. Known: {', '.join(t.id for t in list_templates())}")
    return path


EDITABLE_TEMPLATES = {DEFAULT_TEMPLATE_ID, "times"}


def render_cv_html(
    profile: Profile,
    cv: TailoredCV,
    template_path: Path | None,
    template_id: str = DEFAULT_TEMPLATE_ID,
    editable: bool = False,
) -> str:
    """`editable` marks every field with its profile path (data-path) so the preview can be edited in place.
    Only meaningful for the untailored CV, where list positions equal profile positions."""
    by_name = {sk.name: (i, sk.category) for i, sk in enumerate(profile.skills)}
    groups: list[tuple[str, list[tuple[str, int]]]] = []  # (category, [(name, profile index or -1)])
    for name in cv.skills:
        index, category = by_name.get(name, (-1, ""))
        if groups and groups[-1][0] == category:
            groups[-1][1].append((name, index))
        else:
            existing = next((g for g in groups if g[0] == category), None)
            if existing:
                existing[1].append((name, index))
            else:
                groups.append((category, [(name, index)]))
    path = template_path or template_file(template_id)
    env = Environment(loader=FileSystemLoader(str(path.parent)), autoescape=select_autoescape(["html"]))

    def pidx(section: str, item: object) -> int:
        """Position of a CV item in the profile (for edit paths); -1 if the item is not from the profile."""
        items: list[object] = list(getattr(profile, section))
        for i, candidate in enumerate(items):
            if candidate is item:
                return i
        for i, candidate in enumerate(items):
            if candidate == item:
                return i
        return -1

    env.globals["pidx"] = pidx
    template = env.get_template(path.name)
    html = template.render(
        personal=profile.personal,
        headline=profile.personal.headline,
        skills_note=profile.skills_note,
        skill_groups=groups,
        cv=cv,
        languages=profile.languages,
        certifications=[],
        editable=editable,
    )
    # ATS: some systems (e.g. Workday) drop en/em dashes in date ranges; print plain hyphens.
    return _DATE_DASH.sub(r"\1 - ", html)
