from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from stageone.db import Application, Job, Status, open_db


def make_job(**overrides: object) -> Job:
    base: dict[str, object] = dict(
        source="ats:greenhouse:acme",
        external_id="1",
        url="https://acme.example/jobs/1",
        title="Data Intern",
        company="Acme",
        location="Amsterdam",
        description="desc",
        posted_at=None,
        fetched_at=datetime(2026, 10, 26),
        dedupe_key="acme|data",
    )
    base.update(overrides)
    return Job(**base)


def test_open_db_creates_tables_and_inserts(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        s.add(make_job())
        s.commit()
        assert s.query(Job).count() == 1


def test_duplicate_source_external_id_rejected(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        s.add(make_job())
        s.commit()
        s.add(make_job())
        with pytest.raises(IntegrityError):
            s.commit()


def test_application_default_status_new(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        job = make_job()
        s.add(job)
        s.commit()
        app = Application(job_id=job.id)
        s.add(app)
        s.commit()
        assert app.status == Status.new
        assert app.notes == ""
