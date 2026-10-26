"""HTML for the CV: the default A4 template or the user's own master_cv.html (same Jinja variables)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jobgent.pack.tailor import TailoredCV
from jobgent.profile.models import Profile

DEFAULT_TEMPLATE = Path(__file__).parent / "default_cv.html"


def render_cv_html(profile: Profile, cv: TailoredCV, template_path: Path | None) -> str:
    path = template_path or DEFAULT_TEMPLATE
    env = Environment(loader=FileSystemLoader(str(path.parent)), autoescape=select_autoescape(["html"]))
    template = env.get_template(path.name)
    return template.render(personal=profile.personal, cv=cv, languages=profile.languages)
