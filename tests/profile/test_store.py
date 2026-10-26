from datetime import date
from pathlib import Path

import pytest

from jobgent.profile.models import Education, Personal, Profile, SearchProfile
from jobgent.profile.store import ProfileStore

FIXTURE = Path(__file__).parent.parent / "fixtures" / "jobkiller_profile.json"


def make_profile() -> Profile:
    return Profile(
        personal=Personal(name="A B", location="Amsterdam", email="a@b.nl"),
        education=[Education(institution="X", degree="Y", period="2023 – Present")],
        search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)),
    )


def test_round_trip(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.exists() is False
    store.save(make_profile())
    assert store.exists() is True
    loaded = store.load()
    assert loaded.personal.name == "A B"
    assert loaded.verified is False
    assert loaded.preferences.weekly_goal == 10
    assert "data science intern" in loaded.search.keywords


def test_update_dotted_path_persists(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(make_profile())
    updated = store.update("preferences.weekly_goal", 15)
    assert updated.preferences.weekly_goal == 15
    assert store.load().preferences.weekly_goal == 15


def test_update_list_index(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(make_profile())
    updated = store.update("education[0].degree", "Z")
    assert updated.education[0].degree == "Z"


def test_update_unknown_path_raises(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(make_profile())
    with pytest.raises(KeyError, match="nope.x"):
        store.update("nope.x", 1)


def test_import_jobkiller(tmp_path):
    store = ProfileStore(tmp_path)
    p = store.import_jobkiller(FIXTURE)
    assert p.verified is False
    assert p.personal.name == "Test Student"
    assert p.education[0].institution == "Example University"
    assert p.experience[0].title == "Automation Engineer" and p.experience[0].company == ""
    assert p.experience[0].bullets == ["Built trading bots for a small fund", "Processed >$1M volume", "150+ users", "Tools: Python (asyncio), Docker"]
    assert p.experience[1].company == "Example Corp" and p.experience[1].title == "Full-Stack Engineer"
    assert p.projects[0].name == "Trading bot"
    assert "Leadership" in (tmp_path / "notes.md").read_text() and "Secure an AI internship" in (tmp_path / "notes.md").read_text()
    assert p.search.keywords[:2] == ["AI Automation Intern", "Data Science Intern"]
    assert any(s.name == "Python (asyncio)" for s in p.skills)
    assert any(s.name == "React" for s in p.skills)
    assert [(l.name, l.level) for l in p.languages] == [("English", "B2–C1 (written and spoken)"), ("Russian", "Native")]
    assert store.exists()


def test_voice_default_and_set(tmp_path):
    store = ProfileStore(tmp_path)
    assert "first person" in store.voice()
    store.set_voice("Short. Dry.")
    assert store.voice() == "Short. Dry."


def test_notes_append(tmp_path):
    store = ProfileStore(tmp_path)
    store.notes_append("I like robots")
    store.notes_append("and data")
    text = (tmp_path / "notes.md").read_text()
    assert "I like robots" in text and "and data" in text


def test_master_cv(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.master_cv_path() is None
    store.set_master_cv("<html>x</html>")
    assert store.master_cv_path() == tmp_path / "master_cv.html"


def test_append_and_remove_list_items(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(make_profile())
    p = store.append("skills", {"name": "SQL", "evidence": "course"})
    assert [s.name for s in p.skills] == ["SQL"]
    p = store.append("skills", {"name": "Python"})
    assert len(p.skills) == 2
    p = store.remove("skills", 0)
    assert [s.name for s in p.skills] == ["Python"]
    with pytest.raises(KeyError):
        store.remove("skills", 5)
    with pytest.raises(KeyError):
        store.append("personal", {"x": 1})


def test_completeness_checklist(tmp_path):
    from jobgent.profile.store import completeness

    p = make_profile()
    items = completeness(p)
    assert any(i.label.startswith("Summary") and not i.done for i in items)
    p.summary = "A data science student who builds trading bots and data tools for small teams."
    p.verified = True
    assert any(i.label.startswith("Summary") and i.done for i in completeness(p))
    assert 0 <= sum(i.done for i in items) <= len(items)


def test_import_jobkiller_html_reads_every_field(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(make_profile())  # existing languages/search are kept
    store.update("languages", [{"name": "English", "level": "C1"}])
    p = store.import_jobkiller_html(Path(__file__).parent.parent / "fixtures" / "jobkiller_cv.html")
    assert p.verified is False
    assert p.personal.name == "Test Student" and p.personal.headline == "Data Engineer"
    assert p.personal.location == "Netherlands" and p.personal.birth_date == "01-01-2003"
    assert p.personal.phone == "+31600000000" and p.personal.email == "test@example.com"
    assert p.personal.linkedin.endswith("/in/test-student") and p.personal.github == "https://github.com/teststudent"
    assert p.summary.startswith("AI-focused student")
    assert [(e.company, e.title, e.location, e.period) for e in p.experience] == [
        ("Freelance", "Crypto Automation Engineer", "Netherlands", "2024 - Present"),
        ("Freelance", "Full-Stack Web Developer", "Netherlands", "2023 - 2024"),
    ]
    assert p.experience[0].bullets[0].startswith("Developed automated trading bots") and len(p.experience[0].bullets) == 3
    assert [(e.institution, e.degree, e.location, e.period, e.gpa) for e in p.education][1] == (
        "MSHP Programming School", "Advanced Programming", "Moscow, Russia", "2020 - 2022", "10/10")
    assert p.education[0].details.startswith("ongoing studies")
    names = [s.name for s in p.skills]
    assert names[:3] == ["Python", "Java", "React"] and "n8n workflows" in names and "TypeScript" in names and "C++" in names
    assert p.skills_note == "All professional proficiency or above"
    assert [(pr.name, pr.link) for pr in p.projects][0] == ("MCP for CV editing and generation", "https://github.com/teststudent/CV-MCP")
    assert p.projects[1].description.startswith("Built AI chatbot")
    assert p.languages[0].name == "English"


def test_import_any_dispatches_by_extension(tmp_path):
    store = ProfileStore(tmp_path)
    fixtures = Path(__file__).parent.parent / "fixtures"
    assert store.import_any(fixtures / "jobkiller_cv.html").personal.headline == "Data Engineer"
    assert store.import_any(fixtures / "jobkiller_profile.json").personal.name == "Test Student"
    with pytest.raises(ValueError, match=".txt"):
        store.import_any(tmp_path / "x.txt")


def test_language_strings_in_all_shapes():
    from jobgent.profile.store import _language

    assert (_language("English: B2–C1 (written and spoken)").name, _language("English: B2–C1 (written and spoken)").level) == ("English", "B2–C1 (written and spoken)")
    assert (_language("Dutch (Beginner)").name, _language("Dutch (Beginner)").level) == ("Dutch", "Beginner")
    assert (_language("Russian - Native").name, _language("Russian - Native").level) == ("Russian", "Native")
    assert _language("German").name == "German"
