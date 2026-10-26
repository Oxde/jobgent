from datetime import date, datetime

import pytest

from jobgent.db import Job, open_db
from jobgent.documents import (DocumentError, cv_units, leave_out, load_document, put_back, restore_version, save_document,
                               set_unit, undo_last, versions)
from jobgent.pack.tailor import TailoredCV
from jobgent.profile.models import Experience, Project


def cv() -> TailoredCV:
    return TailoredCV(summary="S", experience=[Experience(company="HEINEKEN", title="Intern", bullets=["a", "b"])],
                      projects=[Project(name="Bot", description="trading bot")], skills=["Python", "SQL"], change_summary=[])


def session(tmp_path):
    Session = open_db(tmp_path / "t.db")
    s = Session()
    s.add(Job(source="s", external_id="1", url="u", title="AI Intern", company="Acme", location=None, description="d",
              posted_at=None, fetched_at=datetime.now(), dedupe_key="k"))
    s.commit()
    return s


def test_units_cover_every_editable_piece():
    ids = [u.id for u in cv_units(cv())]
    assert ids == ["summary", "experience[0].bullets[0]", "experience[0].bullets[1]", "projects[0].description", "skills"]


def test_hand_edit_changes_content_without_a_version(tmp_path):
    s = session(tmp_path)
    save_document(s, 1, "cv", cv().model_dump(mode="json"), cause="written")
    set_unit(s, 1, "cv", "experience[0].bullets[1]", "built things", cause=None)
    doc = load_document(s, 1, "cv")
    assert doc.content["experience"][0]["bullets"][1] == "built things"
    assert [v.cause for v in versions(s, 1, "cv")] == ["written"]


def test_ai_change_is_undoable(tmp_path):
    s = session(tmp_path)
    save_document(s, 1, "cv", cv().model_dump(mode="json"), cause="written")
    set_unit(s, 1, "cv", "summary", "Sharper summary", cause="regenerated")
    assert load_document(s, 1, "cv").content["summary"] == "Sharper summary"
    undo_last(s, 1, "cv")
    assert load_document(s, 1, "cv").content["summary"] == "S"
    with pytest.raises(DocumentError, match="Nothing to undo"):
        undo_last(s, 1, "cv")


def test_leave_out_and_put_back(tmp_path):
    s = session(tmp_path)
    save_document(s, 1, "cv", cv().model_dump(mode="json"), cause="written")
    leave_out(s, 1, "cv", "projects[0].description")
    doc = load_document(s, 1, "cv")
    assert doc.content["projects"] == [] and doc.trimmed[0]["label"].startswith("Project")
    put_back(s, 1, "cv", 0)
    assert load_document(s, 1, "cv").content["projects"][0]["name"] == "Bot"


def test_restore_keeps_a_way_back(tmp_path):
    s = session(tmp_path)
    save_document(s, 1, "cv", cv().model_dump(mode="json"), cause="written")
    set_unit(s, 1, "cv", "summary", "v2", cause="refined")
    first = versions(s, 1, "cv")[0]
    restore_version(s, 1, "cv", first.id)
    assert load_document(s, 1, "cv").content["summary"] == "S"
    assert versions(s, 1, "cv")[-1].cause == "before restore"


def test_letter_units_are_paragraphs(tmp_path):
    s = session(tmp_path)
    save_document(s, 1, "letter", {"paragraphs": ["Dear Acme,", "I build tools.", "Best,\nT"]}, cause="written")
    set_unit(s, 1, "letter", "p1", "I build AI tools.", cause="regenerated")
    assert load_document(s, 1, "letter").content["paragraphs"][1] == "I build AI tools."
    with pytest.raises(DocumentError, match="p9"):
        set_unit(s, 1, "letter", "p9", "x", cause=None)
