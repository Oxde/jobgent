from datetime import datetime

from fastapi.testclient import TestClient

from jobgent.documents import save_document
from jobgent.llm import FakeLLM
from jobgent.pack.rewrite import Rewrite
from jobgent.pack.tailor import TailoredCV
from jobgent.profile.models import Experience
from jobgent.web.app import create_app


def seed(services):
    cv = TailoredCV(summary="S", experience=[Experience(company="Acme", title="Intern", bullets=["built a bot"])], skills=["Python"])
    with services.sessionmaker() as s:
        save_document(s, 1, "cv", cv.model_dump(mode="json"), cause="written")
        save_document(s, 1, "letter", {"paragraphs": ["Dear Acme,", "I build tools."]}, cause="written")
        save_document(s, 1, "email", {"subject": "Application", "body": "Hi"}, cause="written")


def test_documents_listing(services):
    seed(services)
    d = TestClient(create_app(services)).get("/api/jobs/1/documents").json()
    assert [u["id"] for u in d["cv"]["units"]] == ["summary", "experience[0].bullets[0]", "skills"]
    assert d["letter"]["units"][1]["text"] == "I build tools." and d["email"]["units"][0]["id"] == "subject"
    assert d["cv"]["versions"][0]["cause"] == "written"


def test_hand_edit_then_ai_rewrite_then_undo(services):
    seed(services)
    c = TestClient(create_app(services))
    r = c.patch("/api/jobs/1/documents/cv", params={"unit": "summary"}, json={"text": "Maths student"})
    assert r.status_code == 200
    services.llm_factory = lambda: FakeLLM([Rewrite(text="Maths student who builds Python bots", declined=False, reason="")])
    r = c.post("/api/jobs/1/documents/cv/ai", params={"unit": "summary"}, json={"instruction": "mention Python"})
    assert r.status_code == 200 and r.json()["declined"] is False
    assert c.get("/api/jobs/1/documents").json()["cv"]["units"][0]["text"] == "Maths student who builds Python bots"
    assert c.post("/api/jobs/1/documents/cv/undo").status_code == 200
    assert c.get("/api/jobs/1/documents").json()["cv"]["units"][0]["text"] == "Maths student"


def test_ai_declines_or_is_stopped_by_the_fact_guard(services):
    seed(services)
    c = TestClient(create_app(services))
    services.llm_factory = lambda: FakeLLM([Rewrite(text="", declined=True, reason="Your profile has no Kubernetes; add it first.")])
    r = c.post("/api/jobs/1/documents/cv/ai", params={"unit": "summary"}, json={"instruction": "add Kubernetes"})
    assert r.json()["declined"] is True and "Kubernetes" in r.json()["reason"]
    services.llm_factory = lambda: FakeLLM([Rewrite(text="Grew revenue 45%", declined=False, reason="")])
    r = c.post("/api/jobs/1/documents/cv/ai", params={"unit": "summary"}, json={"instruction": "add impact"})
    assert r.status_code == 400 and "45%" in r.json()["detail"]
    assert c.get("/api/jobs/1/documents").json()["cv"]["units"][0]["text"] == "S"


def test_leave_out_put_back_and_restore(services):
    seed(services)
    c = TestClient(create_app(services))
    assert c.post("/api/jobs/1/documents/cv/leave-out", params={"unit": "experience[0].bullets[0]"}).status_code == 200
    d = c.get("/api/jobs/1/documents").json()["cv"]
    assert d["trimmed"][0]["label"].startswith("Bullet") and len(d["units"]) == 2
    assert c.post("/api/jobs/1/documents/cv/put-back/0").status_code == 200
    first = c.get("/api/jobs/1/documents").json()["cv"]["versions"][0]["id"]
    assert c.post(f"/api/jobs/1/documents/cv/restore/{first}").status_code == 200
    assert c.patch("/api/jobs/1/documents/cv", params={"unit": "nope"}, json={"text": "x"}).status_code == 400


def test_edits_rerender_the_cv_html(services):
    seed(services)
    c = TestClient(create_app(services))
    c.patch("/api/jobs/1/documents/cv", params={"unit": "summary"}, json={"text": "Rendered summary"})
    assert "Rendered summary" in c.get("/api/jobs/1/cv").text
