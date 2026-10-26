from datetime import datetime

from jobgent.db import Application, Evaluation, Job, Match, Status, open_db
from jobgent.insights import calibration, learning_gaps
from jobgent.profile.models import Personal, Profile, SearchProfile, Skill
from datetime import date


def profile() -> Profile:
    return Profile(personal=Personal(name="T"), skills=[Skill(name="Python")],
                   search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)))


def seed(tmp_path):
    s = open_db(tmp_path / "t.db")()
    reqs = {
        1: [("SQL", "critical", "gap"), ("Python", "high", "covered"), ("Docker", "nice", "gap")],
        2: [("SQL", "high", "gap"), ("Kubernetes", "critical", "gap")],
        3: [("sql", "nice", "gap"), ("Python", "critical", "gap")],
    }
    verdicts = {1: "apply", 2: "skip", 3: "consider"}
    for i in (1, 2, 3):
        j = Job(id=i, source="s", external_id=str(i), url="u", title=f"Job {i}", company="C", location=None, description="d",
                posted_at=None, fetched_at=datetime.now(), dedupe_key=str(i))
        s.add(j)
        s.add(Evaluation(job_id=i, verdict=verdicts[i], verdict_reason="", gates=[], coverage=50,
                         requirements=[{"text": t, "kind": "skill", "importance": imp, "basis": "stated", "status": st, "evidence": ""} for t, imp, st in reqs[i]]))
    s.commit()
    return s


def test_learning_gaps_rank_by_weight_and_skip_what_you_have(tmp_path):
    s = seed(tmp_path)
    gaps = learning_gaps(s, profile())
    names = [g.skill for g in gaps]
    assert names[0] == "SQL" and gaps[0].jobs == 3
    assert "Python" not in names  # in the profile already: a CV wording problem, not a learning gap
    assert names.index("Kubernetes") < names.index("Docker")


def test_calibration_by_verdict(tmp_path):
    s = seed(tmp_path)
    s.add_all([
        Application(job_id=1, status=Status.interview, furthest_stage="interview", applied_at=datetime.now()),
        Application(job_id=3, status=Status.rejected, furthest_stage="applied", applied_at=datetime.now()),
    ])
    s.commit()
    rows = {r.group: r for r in calibration(s)}
    assert rows["apply"].sent == 1 and rows["apply"].heard_back == 1 and rows["apply"].interviews == 1
    assert rows["consider"].sent == 1 and rows["consider"].heard_back == 1 and rows["consider"].interviews == 0
