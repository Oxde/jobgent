from fastapi.testclient import TestClient

from jobgent.web.app import create_app


def test_feed_lists_jobs(services):
    c = TestClient(create_app(services))
    r = c.get("/")
    assert r.status_code == 200
    assert "Data Intern" in r.text and r.text.index("Data Intern") < r.text.index("AI Intern")


def test_status_post_moves_to_tracker(services):
    c = TestClient(create_app(services))
    r = c.post("/jobs/1/status", data={"status": "applied"}, follow_redirects=False)
    assert r.status_code in (200, 303)
    t = c.get("/tracker").text
    assert "AI Intern" in t and "1 / 10" in t


def test_unknown_job_404(services):
    c = TestClient(create_app(services))
    r = c.get("/jobs/999")
    assert r.status_code == 404 and "999" in r.text


def test_job_detail_shows_reasons_and_gaps(services):
    c = TestClient(create_app(services))
    r = c.get("/jobs/2")
    assert r.status_code == 200 and "Data Intern" in r.text


def test_status_post_with_next_redirects_there(services):
    c = TestClient(create_app(services))
    r = c.post("/jobs/1/status", data={"status": "skipped", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "AI Intern" not in c.get("/").text


def test_feed_has_keep_and_skip_controls(services):
    html = TestClient(create_app(services)).get("/").text
    assert 'value="liked"' in html and 'value="skipped"' in html
