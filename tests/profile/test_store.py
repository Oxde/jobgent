from datetime import date
from pathlib import Path

import pytest

from stageone.profile.models import Education, Personal, Profile, SearchProfile
from stageone.profile.store import ProfileStore

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
    assert p.experience[0].company == "Example Corp"
    assert p.experience[0].bullets == ["Built a bot", "Shipped a dashboard"]
    assert any(s.name == "React" for s in p.skills)
    assert p.languages[0].name == "English"
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
