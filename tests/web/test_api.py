from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from jobgent.assistant import AssistantReply, ProfileEdit
from jobgent.db import Application, Status
from jobgent.llm import FakeLLM
from jobgent.web.app import create_app


def client(services) -> TestClient:
    return TestClient(create_app(services))


def test_home(services):
    with services.sessionmaker() as s:
        s.add(Application(job_id=1, status=Status.pack_ready))
        s.add(Application(job_id=2, status=Status.applied, applied_at=datetime.now() - timedelta(days=20)))
        s.commit()
    r = client(services).get("/api/home")
    assert r.status_code == 200
    d = r.json()
    assert d["stats"]["goal"] == 10 and d["weeks_left"] > 0
    assert [a["kind"] for a in d["actions"]] == ["send", "follow_up"]
    assert any(c["label"] == "Profile verified" for c in d["checklist"])


def test_jobs_list_filters_and_search(services):
    c = client(services)
    rows = c.get("/api/jobs").json()
    assert [j["title"] for j in rows] == ["Data Intern", "AI Intern"]
    assert [j["title"] for j in c.get("/api/jobs?q=data").json()] == ["Data Intern"]
    assert c.get("/api/jobs?min_score=80").json()[0]["title"] == "Data Intern" and len(c.get("/api/jobs?min_score=80").json()) == 1


def test_job_detail_has_dims_ats_and_pack_state(services):
    c = client(services)
    d = c.get("/api/jobs/2").json()
    assert d["job"]["title"] == "Data Intern"
    assert [x["name"] for x in d["dims"]] == ["Skills", "Role", "Language & location", "Timing"]
    assert d["ats"] is None and d["pack"] is None
    assert c.get("/api/jobs/999").status_code == 404


def test_status_update_and_board(services):
    c = client(services)
    r = c.post("/api/jobs/1/status", json={"status": "liked"})
    assert r.status_code == 200 and r.json()["status"] == "liked"
    assert c.post("/api/jobs/1/status", json={"status": "bogus"}).status_code == 400
    board = c.get("/api/applications").json()
    cols = {col["key"]: [card["job"]["title"] for card in col["cards"]] for col in board}
    assert cols["liked"] == ["AI Intern"]


def test_profile_get_patch_sections(services):
    c = client(services)
    p = c.get("/api/profile").json()
    assert p["profile"]["personal"]["name"] == "T" and "checklist" in p and "voice" in p and len(p["templates"]) >= 9
    r = c.patch("/api/profile", json={"path": "personal.headline", "value": "Data student"})
    assert r.status_code == 200 and r.json()["personal"]["headline"] == "Data student"
    assert c.patch("/api/profile", json={"path": "nope.x", "value": "1"}).status_code == 400
    r = c.post("/api/profile/skills", json={"name": "SQL", "evidence": "course"})
    assert r.status_code == 200 and r.json()["skills"][0]["name"] == "SQL"
    r = c.put("/api/profile/skills/0", json={"name": "SQL", "evidence": "two courses"})
    assert r.json()["skills"][0]["evidence"] == "two courses"
    r = c.post("/api/profile/experience", json={"company": "Acme", "title": "Dev", "period": "2024", "bullets": ["a", "b"]})
    assert r.json()["experience"][0]["bullets"] == ["a", "b"]
    assert c.delete("/api/profile/skills/0").json()["skills"] == []
    assert c.delete("/api/profile/skills/7").status_code == 404
    r = c.post("/api/profile/voice", json={"text": "Short."})
    assert r.status_code == 200 and services.store.voice() == "Short."


def test_cv_preview_and_template(services):
    c = client(services)
    r = c.get("/api/cv/preview?template=tech")
    assert r.status_code == 200 and "<html" in r.text.lower()
    assert c.get("/api/cv/preview?template=nope").status_code == 400
    assert c.get("/api/templates").json()[0]["id"] == "default"


def test_assistant_and_history(services):
    fake = FakeLLM([AssistantReply(reply="Goal is now 12.", edits=[ProfileEdit(path="preferences.weekly_goal", value="12")])])
    services.llm_factory = lambda: fake
    c = client(services)
    r = c.post("/api/assistant", json={"message": "set goal to 12"})
    assert r.status_code == 200
    d = r.json()
    assert d["reply"].startswith("Goal is now 12.") and d["applied"] == ["preferences.weekly_goal"]
    assert [m["role"] for m in c.get("/api/assistant").json()] == ["user", "assistant"]
    assert c.delete("/api/assistant").status_code == 200 and c.get("/api/assistant").json() == []


def test_assistant_without_key_returns_message_not_500(services):
    from jobgent.errors import MissingSecretError

    def boom():
        raise MissingSecretError("ANTHROPIC_API_KEY")

    services.llm_factory = boom
    r = client(services).post("/api/assistant", json={"message": "hi"})
    assert r.status_code == 200 and "ANTHROPIC_API_KEY" in r.json()["reply"]


def test_settings_never_leaks_values(services):
    from jobgent.config import load_settings

    services.settings = load_settings(env={"JOBGENT_HOME": str(services.settings.home), "ANTHROPIC_API_KEY": "sk-SECRET"}, secrets_file=services.settings.home / "none")
    d = client(services).get("/api/settings").json()
    assert "SECRET" not in str(d) and d["keys"][0]["name"] == "ANTHROPIC_API_KEY" and d["keys"][0]["present"] is True


def test_spa_fallback_serves_index_when_built(services, tmp_path, monkeypatch):
    import jobgent.web.app as webapp

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>app</body></html>")
    (dist / "assets" / "x.js").write_text("1")
    monkeypatch.setattr(webapp, "DIST", dist)
    c = client(services)
    assert c.get("/").text == "<html><body>app</body></html>"
    assert c.get("/jobs/42").text == "<html><body>app</body></html>"
    assert c.get("/assets/x.js").text == "1"
    assert c.get("/api/nope").status_code == 404


def test_editable_preview_and_profile_version(services):
    import time

    c = client(services)
    services.store.append("experience", {"company": "Acme", "title": "Dev", "period": "2024", "bullets": ["a"]})
    html = c.get("/api/cv/preview?template=default&edit=1").text
    assert 'data-path="experience[0].bullets[0]"' in html and "contenteditable" in html
    assert "contenteditable" not in c.get("/api/cv/preview?template=default").text
    v1 = c.get("/api/profile/version").json()["version"]
    time.sleep(0.01)
    assert c.patch("/api/profile", json={"path": "experience[0].bullets[0]", "value": "Built it"}).status_code == 200
    assert services.store.load().experience[0].bullets[0] == "Built it"
    assert c.get("/api/profile/version").json()["version"] != v1


def test_cv_pdf_download(services, monkeypatch):
    import jobgent.web.app as webapp

    calls = []

    def fake_pdf(html: str, out, fit: bool = False):
        calls.append(fit)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4 fake")
        return 1

    monkeypatch.setattr(webapp, "html_to_pdf", fake_pdf)
    r = client(services).get("/api/cv/pdf?template=times")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert client(services).get("/api/cv/pdf?template=nope").status_code == 400
    assert calls == [True]


def test_job_cv_preview_falls_back_to_general_cv(services):
    c = client(services)
    r = c.get("/api/jobs/1/cv")
    assert r.status_code == 200 and "<html" in r.text.lower() and "T" in r.text
    assert c.get("/api/jobs/999/cv").status_code == 404
    pack_dir = services.settings.applications_dir / "acme-ai-intern-1"
    pack_dir.mkdir(parents=True)
    (pack_dir / "cv.html").write_text("<html><body>tailored for acme</body></html>")
    assert "tailored for acme" in c.get("/api/jobs/1/cv").text


def test_section_specs_expose_hidden_as_a_checkbox(services):
    specs = {s["key"]: {f["name"]: f["kind"] for f in s["fields"]} for s in client(services).get("/api/profile").json()["sections"]}
    assert specs["experience"]["hidden"] == "bool" and specs["education"]["hidden"] == "bool" and specs["projects"]["hidden"] == "bool"
    assert specs["experience"]["bullets"] == "lines" and specs["skills"]["name"] == "text"
