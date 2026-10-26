from datetime import datetime, timedelta

from jobgent.db import Job, Status, open_db
from jobgent.tracker import set_status, weekly_stats


def add_job(s, i: int) -> Job:
    j = Job(source="s", external_id=str(i), url="u", title=f"t{i}", company="c", location=None, description="d",
            posted_at=None, fetched_at=datetime.now(), dedupe_key=str(i))
    s.add(j)
    s.commit()
    return j


def test_applied_sets_applied_at(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        j = add_job(s, 1)
        app = set_status(s, j.id, Status.applied, notes="via email")
        assert app.applied_at is not None and app.notes == "via email"
        app = set_status(s, j.id, Status.interview, notes=None)
        assert app.status == Status.interview and app.applied_at is not None


def test_weekly_stats_counts_only_this_week(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        a, b, c = add_job(s, 1), add_job(s, 2), add_job(s, 3)
        set_status(s, a.id, Status.applied, None)
        old = set_status(s, b.id, Status.applied, None)
        old.applied_at = datetime.now() - timedelta(days=14)
        set_status(s, c.id, Status.liked, None)
        s.commit()
        stats = weekly_stats(s, goal=10)
    assert stats.applied_this_week == 1 and stats.goal == 10
    assert stats.by_status["applied"] == 2 and stats.by_status["liked"] == 1
