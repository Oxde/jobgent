from fastapi.testclient import TestClient

from jobgent.config import load_settings
from jobgent.demo import build_demo
from jobgent.service import build_services
from jobgent.web.app import create_app


def test_demo_home_is_complete_and_never_touches_the_real_profile(tmp_path):
    home = tmp_path / "demo"
    build_demo(home)
    services = build_services(load_settings(env={"JOBGENT_HOME": str(home), "JOBGENT_LINKEDIN": "off"}, secrets_file=tmp_path / "none"))
    profile = services.store.load()
    assert profile.verified and profile.personal.name == "Sam Jansen" and "example" in profile.personal.email
    c = TestClient(create_app(services))
    jobs = c.get("/api/jobs").json()
    assert len(jobs) >= 8
    home_data = c.get("/api/home").json()
    kinds = {a["kind"] for a in home_data["actions"]}
    assert {"send", "make_pack", "follow_up", "interview_soon"} <= kinds and home_data["funnel"]["sent"] >= 3
    packed = next(a["job"]["id"] for a in home_data["actions"] if a["kind"] == "send")
    page = c.get(f"/api/jobs/{packed}").json()
    assert page["evaluation"]["verdict"] in ("apply", "consider") and page["pack"] is not None
    assert c.get(f"/api/jobs/{packed}/documents").json()["cv"]["units"]
    assert c.get("/api/agent").json()["queue"]


def test_demo_refuses_to_overwrite_a_non_demo_home(tmp_path):
    import pytest

    from jobgent.errors import JobgentError
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "profile.yaml").write_text("personal: {name: Real}\n")
    with pytest.raises(JobgentError, match="not a demo"):
        build_demo(tmp_path)
