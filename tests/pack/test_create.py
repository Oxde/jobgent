from datetime import date, datetime
from pathlib import Path

import pytest

from jobgent.config import load_settings
from jobgent.db import Application, Job, Status, open_db
from jobgent.errors import ProfileNotVerifiedError, JobgentError
from jobgent.llm import FakeLLM
from jobgent.pack.create import create_pack
from jobgent.pack.letter import CoverLetter
from jobgent.pack.review import Review, ReviewEdit
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


def no_edits() -> Review:
    return Review(edits=[], missed_keywords="none", company_angle="fine", passive_phrasing="none", tone="fine")


def responses(n_tailor: int = 1) -> list:
    """Order: tailor, letter, review, verify CV, verify letter; each retry adds tailor + verify CV."""
    out: list = [TailoredCV(summary="S", skills=["Python"], change_summary=["x"]), CoverLetter(body="Dear Acme"), no_edits(),
                 VerifyOutput(unsupported_claims=[]), VerifyOutput(unsupported_claims=[])]
    for _ in range(n_tailor - 1):
        out += [TailoredCV(summary="S", skills=["Python"], change_summary=["x"]), VerifyOutput(unsupported_claims=[])]
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
    assert result.cv_pdf.is_file() and llm.calls == 7


def test_fails_when_still_two_pages(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(JobgentError, match="2 pages"):
        create_pack(settings, s, FakeLLM(responses(n_tailor=2)), store, job_id=1, pdf=FakePdf([2, 2]))


def test_unknown_job(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    with Session() as s, pytest.raises(JobgentError, match="999"):
        create_pack(settings, s, FakeLLM([]), store, job_id=999, pdf=FakePdf([1]))


def test_reviewer_edits_are_applied_and_recorded(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    review = Review(edits=[ReviewEdit(unit="summary", old="S", new="Student who builds Python tools", reason="specific"),
                           ReviewEdit(unit="letter", old="Dear Acme", new="Dear Acme team", reason="warmer"),
                           ReviewEdit(unit="experience[5].bullets[0]", old="x", new="y", reason="no such unit")],
                    missed_keywords="Python not in summary", company_angle="mention internal tools", passive_phrasing="none", tone="ok")
    llm = FakeLLM([TailoredCV(summary="S", skills=["Python"], change_summary=["x"]), CoverLetter(body="Dear Acme"), review,
                   VerifyOutput(), VerifyOutput()])
    with Session() as s:
        r = create_pack(settings, s, llm, store, job_id=1, pdf=FakePdf([1]))
    assert r.letter_md.read_text() == "Dear Acme team"
    assert "Student who builds Python tools" in r.cv_html.read_text()
    assert r.review_applied == ["summary", "letter"] and r.review_skipped == ["experience[5].bullets[0]"]
    assert r.review_notes["company_angle"] == "mention internal tools"


def test_banned_phrases_trigger_one_rewrite(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    llm = FakeLLM([TailoredCV(summary="S", skills=["Python"]), CoverLetter(body="I am passionate about AI — truly."), no_edits(),
                   CoverLetter(body="I build AI tools."), VerifyOutput(), VerifyOutput()])
    with Session() as s:
        r = create_pack(settings, s, llm, store, job_id=1, pdf=FakePdf([1]))
    assert r.letter_md.read_text() == "I build AI tools."
    assert "passionate" in llm.prompts[3][1]


def test_invented_number_stops_the_pack_before_any_pdf(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    pdf = FakePdf([1])
    llm = FakeLLM([TailoredCV(summary="Raised revenue by 37%", skills=["Python"]), CoverLetter(body="Dear Acme"), no_edits()])
    with Session() as s, pytest.raises(JobgentError, match="37%"):
        create_pack(settings, s, llm, store, job_id=1, pdf=pdf)
    assert pdf.calls == 0


def test_unknown_names_are_marked_for_checking(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    llm = FakeLLM([TailoredCV(summary="Built tools with Terraform", skills=["Python"]), CoverLetter(body="Dear Acme"), no_edits(),
                   VerifyOutput(), VerifyOutput()])
    with Session() as s:
        r = create_pack(settings, s, llm, store, job_id=1, pdf=FakePdf([1]))
    assert "Terraform" in r.check_this  # "Python" too: the test profile has no Python skill


def test_note_tone_and_facts_reach_the_letter(tmp_path):
    settings, store, Session = setup(tmp_path, verified=True)
    store.update("facts", ["Available from 1 February 2027, 40 hours a week"])
    with Session() as s:
        s.add(Application(job_id=1, status=Status.liked, ai_note="I met their CTO at a meetup", tone="direct"))
        s.commit()
        llm = FakeLLM(responses())
        create_pack(settings, s, llm, store, job_id=1, pdf=FakePdf([1]))
    system, user = llm.prompts[1]
    assert "I met their CTO" in user and "Available from 1 February 2027" in user and "Direct" in system
