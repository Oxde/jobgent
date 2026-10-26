from datetime import date, datetime

from jobgent.db import Job
from jobgent.llm import FakeLLM
from jobgent.pack.letter import CoverLetter, write_letter
from jobgent.pack.render import render_cv_html
from jobgent.pack.tailor import TailoredCV, tailor_cv
from jobgent.profile.models import Education, Experience, Personal, Profile, SearchProfile


def profile() -> Profile:
    return Profile(personal=Personal(name="Test Student", email="t@x.nl", location="Amsterdam"),
                   education=[Education(institution="Uni", degree="Math", period="2023–now")],
                   experience=[Experience(company="Acme", title="Dev", bullets=["Built a bot"])],
                   search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def job() -> Job:
    return Job(id=1, source="s", external_id="1", url="https://acme/1", title="AI Intern", company="Acme", location="Amsterdam",
               description="We want Python.", posted_at=None, fetched_at=datetime.now(), dedupe_key="k")


def tailored() -> TailoredCV:
    return TailoredCV(summary="Math student who builds bots.", experience=profile().experience, projects=[],
                      skills=["Python"], education=profile().education, change_summary=["Moved Python first"])


def test_tailor_cv_passes_profile_and_job_and_extra_instruction():
    llm = FakeLLM([tailored()])
    cv = tailor_cv(llm, "m", profile(), job(), extra_instruction="shorten by 20%")
    assert cv.change_summary == ["Moved Python first"]
    system, user = llm.prompts[0]
    assert "AI Intern" in user and "Built a bot" in user and "shorten by 20%" in user
    assert "never" in system.lower()


def test_write_letter_uses_voice():
    llm = FakeLLM([CoverLetter(body="Dear Acme, ...")])
    letter = write_letter(llm, "m", profile(), job(), voice="Short. Dry.")
    assert letter.body.startswith("Dear Acme")
    assert "Short. Dry." in llm.prompts[0][0]


def test_render_cv_html_default_template():
    html = render_cv_html(profile(), tailored(), template_path=None)
    assert "Test Student" in html and "size: A4" in html and "Built a bot" in html and "Python" in html


def test_render_cv_html_custom_template(tmp_path):
    t = tmp_path / "cv.html"
    t.write_text("<html><body>{{ personal.name }} / {{ cv.summary }}</body></html>")
    html = render_cv_html(profile(), tailored(), template_path=t)
    assert html == "<html><body>Test Student / Math student who builds bots.</body></html>"


def test_general_cv_builds_from_profile_without_llm():
    from jobgent.pack.tailor import general_cv

    p = profile()
    p.summary = "Math student who builds bots."
    p.skills = [__import__("jobgent.profile.models", fromlist=["Skill"]).Skill(name="Python", evidence="bots")]
    cv = general_cv(p)
    assert cv.summary == "Math student who builds bots." and cv.skills == ["Python"]
    assert cv.experience == p.experience and cv.education == p.education and cv.change_summary == []
    html = render_cv_html(p, cv, template_path=None)
    assert "Python" in html and "Test Student" in html


def test_all_templates_render_profile():
    import pytest as _pt

    from jobgent.pack.render import list_templates, render_cv_html

    ids = [t.id for t in list_templates()]
    assert set(ids) >= {"modern", "classic", "minimal", "creative", "tech", "executive", "compact", "two-column"}
    for tid in ids:
        html = render_cv_html(profile(), tailored(), template_path=None, template_id=tid)
        assert "Test Student" in html and "Built a bot" in html and "size: A4" in html, tid
    with _pt.raises(KeyError, match="nope"):
        render_cv_html(profile(), tailored(), template_path=None, template_id="nope")


def test_editable_render_marks_profile_paths():
    from jobgent.pack.render import render_cv_html

    for tid in ("default", "times"):
        html = render_cv_html(profile(), tailored(), template_path=None, template_id=tid, editable=True)
        assert 'data-path="personal.name"' in html, tid
        assert 'data-path="summary"' in html, tid
        assert 'data-path="experience[0].bullets[0]"' in html, tid
        assert 'data-path="education[0].degree"' in html, tid
        plain = render_cv_html(profile(), tailored(), template_path=None, template_id=tid)
        assert "data-path" not in plain, tid


def test_times_template_groups_skills_by_category():
    from jobgent.pack.render import render_cv_html
    from jobgent.pack.tailor import general_cv
    from jobgent.profile.models import Skill

    p = profile()
    p.skills = [Skill(name="Python", category="Programming"), Skill(name="SQL", category="Programming"), Skill(name="LangChain", category="AI")]
    html = render_cv_html(p, general_cv(p), None, "times", editable=True)
    assert "Programming</b>: " in html and "AI</b>: " in html
    assert html.index("Python") < html.index("SQL") < html.index("LangChain")
    assert 'data-path="skills[2].name"' in html and 'data-path="skills[2].category"' in html


def test_tailor_prompt_includes_the_guide():
    llm = FakeLLM([tailored()])
    tailor_cv(llm, "m", profile(), job())
    assert "Tailoring to one posting" in llm.prompts[0][0]


def test_times_header_is_ats_safe():
    from jobgent.pack.render import render_cv_html
    from jobgent.pack.tailor import general_cv

    p = profile()
    p.personal.linkedin = "https://www.linkedin.com/in/test-student"
    p.personal.github = "https://github.com/teststudent"
    p.personal.birth_date = "01-01-2003"
    html = render_cv_html(p, general_cv(p), None, "times")
    head = html[html.index('<div class="header">'):html.index("</div>\n    </div>") if "</div>\n    </div>" in html else len(html)]
    assert "<table" not in html
    assert "linkedin.com/in/test-student" in html and "github.com/teststudent" in html
    assert "01-01-2003" not in html
