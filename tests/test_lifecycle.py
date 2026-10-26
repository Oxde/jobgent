from datetime import datetime, timedelta

import pytest

from jobgent.db import Job, Status, open_db
from jobgent.errors import JobgentError
from jobgent.lifecycle import add_note, set_interview, timeline, undo_status
from jobgent.tracker import set_status


def session(tmp_path):
    s = open_db(tmp_path / "t.db")()
    s.add(Job(source="s", external_id="1", url="u", title="AI Intern", company="Acme", location=None, description="d",
              posted_at=None, fetched_at=datetime.now(), dedupe_key="k"))
    s.commit()
    return s


def test_furthest_stage_never_goes_down(tmp_path):
    s = session(tmp_path)
    set_status(s, 1, Status.applied, None)
    app = set_status(s, 1, Status.interview, None)
    assert app.furthest_stage == "interview"
    app = set_status(s, 1, Status.rejected, None)
    assert app.status == Status.rejected and app.furthest_stage == "interview"


def test_undo_restores_status_furthest_stage_and_sent_date(tmp_path):
    s = session(tmp_path)
    set_status(s, 1, Status.liked, None)
    app = set_status(s, 1, Status.applied, None)
    assert app.applied_at is not None
    app = undo_status(s, 1)
    assert app.status == Status.liked and app.applied_at is None and app.furthest_stage == "liked"
    with pytest.raises(JobgentError, match="Nothing to undo"):
        undo_status(s, 1)
        undo_status(s, 1)


def test_timeline_mixes_notes_and_status_changes(tmp_path):
    s = session(tmp_path)
    set_status(s, 1, Status.applied, None)
    add_note(s, 1, "Sent via their careers page")
    set_interview(s, 1, datetime.now() + timedelta(days=2))
    items = timeline(s, 1)
    kinds = [i.kind for i in items]
    assert kinds == ["status", "note", "interview"]
    assert "applied" in items[0].text and items[1].text == "Sent via their careers page"
