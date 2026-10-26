from datetime import date, datetime
from pathlib import Path

import pytest

from jobgent.config import load_settings
from jobgent.db import Application, Job, Status, open_db
from jobgent.errors import ProfileNotVerifiedError, JobgentError
from jobgent.llm import FakeLLM
from jobgent.pack.create import create_pack
from jobgent.pack.letter import CoverLetter
from jobgent.pack.tailor import TailoredCV
from jobgent.pack.verify import VerifyOutput
from jobgent.profile.models import Personal, Profile, SearchProfile
from jobgent.profile.store import ProfileStore


def setup(tmp_path: Path, verified: bool):
    settings = load_settings(env={"JOBGENT_HOME": str(tmp_path)}, secrets_file=tmp_path / "none")
    store = ProfileStore(settings.profile_dir)
    store.save(Profile(verified=verified, personal=Personal(name="T"),
                       search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1))))
    Session = open_db(settings.db_path)
    with Session() as s:
        s.add(Job(source="s", external_id="1", url="https://acme/1", title="AI Intern", company="Acme B.V.", location=None,
                  description="Contact jobs@acme.nl for questions.", posted_at=None, fetched_at=datetime.now(), dedupe_key="k",
                  is_internship=True, language="en", dutch_required=False, classified_at=datetime.now()))
        s.commit()
    return settings, store, Session


def responses(n_tailor: int = 1) -> list:
    out: list = []
    for _ in range(n_tailor):
        out += [TailoredCV(summary="S", skills=["Python"], change_summary=["x"]), VerifyOutput(unsupported_claims=[])]
    out += [CoverLetter(body="Dear Acme"), VerifyOutput(unsupported_claims=[])]
    return out


class FakePdf:
    def __init__(self, pages: list[int]) -> None:
        self.pages = pages
        self.calls = 0

    def __call__(self, html: str, out: Path) -> int:
        self.calls += 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-fake")
        return self.pages.pop(0)


def test_refuses_unverified_profile(tmp_path):
    settings, store, Session = setup(tmp_path, verified=False)
    with Session() as s, pytest.raises(ProfileNotVerifiedError):
        create_pack(settings, s, FakeLLM([]), store, job_id=1, pdf=FakePdf([1]))
    assert not settings.applications_dir.exists()


def test_creates_pack_files_and_status(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s:
        result = create_pack(settings, s, FakeLLM(responses()), store, job_id=1, pdf=FakePdf([1]))
        assert result.cv_pdf.is_file() and result.cv_html.is_file() and result.letter_md.read_text() == "Dear Acme"
        assert result.apply_email == "jobs@acme.nl" and result.apply_url == "https://acme/1"
        assert result.dir.name == "acme-bv-ai-intern-1"
        assert (result.dir / "meta.json").is_file()
        app = s.get(Application, 1)
        assert app is not None and app.status == Status.pack_ready and app.pack_dir == str(result.dir)


def test_retries_once_when_two_pages(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    llm = FakeLLM(responses(n_tailor=2))
    with Session() as s:
        result = create_pack(settings, s, llm, store, job_id=1, pdf=FakePdf([2, 1]))
    assert result.cv_pdf.is_file() and llm.calls == 6


def test_fails_when_still_two_pages(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(JobgentError, match="2 pages"):
        create_pack(settings, s, FakeLLM(responses(n_tailor=2)), store, job_id=1, pdf=FakePdf([2, 2]))


def test_unknown_job(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(JobgentError, match="999"):
        create_pack(settings, s, FakeLLM([]), store, job_id=999, pdf=FakePdf([1]))
