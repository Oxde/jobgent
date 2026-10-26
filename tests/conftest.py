from datetime import date, datetime
from pathlib import Path

import pytest

from stageone.config import load_settings
from stageone.db import Job, Match, open_db
from stageone.llm import FakeLLM
from stageone.profile.models import Personal, Profile, SearchProfile
from stageone.profile.store import ProfileStore
from stageone.service import Services


@pytest.fixture
def services(tmp_path: Path) -> Services:
    """A Services bundle on a temp home with a verified profile and two scored jobs."""
    settings = load_settings(env={"STAGEONE_HOME": str(tmp_path), "APIFY_TOKEN": "", "ANTHROPIC_API_KEY": ""},
                             secrets_file=tmp_path / "none")
    store = ProfileStore(settings.profile_dir)
    store.save(Profile(verified=True, personal=Personal(name="T"),
                       search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))))
    Session = open_db(settings.db_path)
    with Session() as s:
        for i, (title, total) in enumerate([("AI Intern", 70), ("Data Intern", 90)], start=1):
            j = Job(source="ats:lever:acme", external_id=str(i), url=f"https://acme/{i}", title=title, company="Acme",
                    location="Amsterdam", description="d", posted_at=None, fetched_at=datetime.now(), dedupe_key=title,
                    is_internship=True, language="en", dutch_required=False, dutch_plus=False, classified_at=datetime.now())
            s.add(j)
            s.flush()
            s.add(Match(job_id=j.id, total=total, skills=40, role=15, lang_loc=10, timing=5, reasons=["r"], gaps=["g"], model="m"))
        s.commit()
    fake = FakeLLM([])
    return Services(settings=settings, sessionmaker=Session, store=store, llm_factory=lambda: fake,
                    http_client_factory=lambda: __import__("httpx").Client())
