from datetime import date, datetime, timedelta

from jobgent.dashboard import funnel, parse_deadline, weekly_sent, worth_a_look
from jobgent.db import Application, ApplicationEvent, Job, Status, open_db


def session(tmp_path, n=6):
    s = open_db(tmp_path / "t.db")()
    for i in range(1, n + 1):
        s.add(Job(id=i, source="s", external_id=str(i), url=f"https://x/{i}", title=f"Job {i}", company=f"Co {i}", location=None,
                  description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key=str(i)))
    s.commit()
    return s


def test_parse_deadline():
    assert parse_deadline("15 Nov 2026") == date(2026, 11, 15)
    assert parse_deadline("November 15, 2026") == date(2026, 11, 15)
    assert parse_deadline("2026-11-15") == date(2026, 11, 15)
    assert parse_deadline("asap") is None and parse_deadline(None) is None


def test_worth_a_look_order_and_texts(tmp_path):
    s = session(tmp_path)
    now = datetime.now()
    s.get(Job, 3).deadline = (date.today() + timedelta(days=3)).strftime("%d %b %Y")
    s.add_all([
        Application(job_id=1, status=Status.offer),
        Application(job_id=2, status=Status.interview, interview_at=now + timedelta(days=1)),
        Application(job_id=3, status=Status.pack_ready),
        Application(job_id=4, status=Status.liked),
        Application(job_id=5, status=Status.applied, applied_at=now - timedelta(days=9)),
        Application(job_id=6, status=Status.applied, applied_at=now - timedelta(days=30)),
    ])
    # job 6 already got two follow-ups: no more nagging
    s.add_all([ApplicationEvent(job_id=6, kind="followup", text="f1"), ApplicationEvent(job_id=6, kind="followup", text="f2")])
    s.commit()
    items = worth_a_look(s)
    assert [i.kind for i in items] == ["offer", "interview_soon", "send", "make_pack", "follow_up"]
    send = next(i for i in items if i.kind == "send")
    assert "closes in 3 days" in send.text
    fu = next(i for i in items if i.kind == "follow_up")
    assert fu.job.id == 5 and "9 days" in fu.text and "1 of 2" in fu.text


def test_funnel_uses_furthest_stage(tmp_path):
    s = session(tmp_path)
    s.add_all([
        Application(job_id=1, status=Status.applied, furthest_stage="applied", applied_at=datetime.now()),
        Application(job_id=2, status=Status.rejected, furthest_stage="interview", applied_at=datetime.now()),
        Application(job_id=3, status=Status.offer, furthest_stage="offer", applied_at=datetime.now()),
        Application(job_id=4, status=Status.rejected, furthest_stage="applied", applied_at=datetime.now()),
        Application(job_id=5, status=Status.liked, furthest_stage="liked"),
    ])
    s.commit()
    f = funnel(s)
    assert (f.sent, f.heard_back, f.interview, f.offer) == (4, 3, 2, 1)
    assert f.response_rate == 75


def test_weekly_sent_has_eight_weeks(tmp_path):
    s = session(tmp_path)
    s.add(Application(job_id=1, status=Status.applied, applied_at=datetime.now()))
    s.add(Application(job_id=2, status=Status.applied, applied_at=datetime.now() - timedelta(days=7)))
    s.commit()
    weeks = weekly_sent(s, weeks=8)
    assert len(weeks) == 8 and weeks[-1].sent == 1 and weeks[-2].sent == 1
