from datetime import datetime, timedelta

from jobgent.dashboard import applications_board, home_data, needs_action
from jobgent.db import Application, Job, Status


def test_needs_action_buckets(services):
    with services.sessionmaker() as s:
        # job 1 liked without pack; job 2 applied 20 days ago with no answer
        s.add(Application(job_id=1, status=Status.liked))
        s.add(Application(job_id=2, status=Status.applied, applied_at=datetime.now() - timedelta(days=20)))
        s.commit()
        items = needs_action(s)
    kinds = {i.kind: i.job.title for i in items}
    assert kinds == {"make_pack": "AI Intern", "follow_up": "Data Intern"}


def test_home_data_has_matches_goal_and_checklist(services):
    with services.sessionmaker() as s:
        h = home_data(s, services.store.load())
    assert [j.title for j in h.top_matches] == ["Data Intern", "AI Intern"]
    assert h.weeks_left > 0 and h.stats.goal == 10
    assert any(not c.done for c in h.checklist)


def test_applications_board_groups_and_flags_no_answer(services):
    with services.sessionmaker() as s:
        s.add(Application(job_id=1, status=Status.applied, applied_at=datetime.now() - timedelta(days=20)))
        s.add(Application(job_id=2, status=Status.liked))
        s.commit()
        board = applications_board(s)
    cols = {c.key: [card.job.title for card in c.cards] for c in board}
    assert cols["liked"] == ["Data Intern"] and cols["no_answer"] == ["AI Intern"] and cols["applied"] == []
    card = next(c for col in board for c in col.cards if c.job.title == "AI Intern")
    assert card.days_since == 20
