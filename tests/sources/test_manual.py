from datetime import datetime

import httpx
import pytest
import respx

from stageone.errors import SourceError
from stageone.db import open_db
from stageone.llm import FakeLLM
from stageone.sources.manual import ExtractedJob, add_job_from_text, add_job_from_url

_HOSTS = {"acme.example": "93.184.216.34", "localhost": "127.0.0.1"}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """No live DNS in tests: literal IPs pass through, known names map to fixed addresses."""
    import ipaddress
    import socket

    def getaddrinfo(host, port, *args, **kwargs):
        try:
            ip = str(ipaddress.ip_address(host))
        except ValueError:
            if host not in _HOSTS:
                raise socket.gaierror(f"fake dns: unknown host {host}")
            ip = _HOSTS[host]
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr("stageone.sources.manual.socket.getaddrinfo", getaddrinfo)


def extracted() -> ExtractedJob:
    return ExtractedJob(title="AI Intern", company="Acme", location="Amsterdam", description="Build AI.", posted_at=None)


def test_add_from_text(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        job = add_job_from_text(s, FakeLLM([extracted()]), "m", text="AI Intern at Acme...", url=None)
        assert job.id is not None and job.source == "manual" and job.company == "Acme"
        assert job.url == "" and job.description == "Build AI."


def test_add_from_url(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with respx.mock as m:
        m.get("https://acme.example/jobs/1").mock(return_value=httpx.Response(200, text="<html><body><h1>AI Intern</h1></body></html>"))
        with Session() as s, httpx.Client() as client:
            job = add_job_from_url(s, FakeLLM([extracted()]), "m", client, "https://acme.example/jobs/1")
            assert job.url == "https://acme.example/jobs/1" and job.title == "AI Intern"


def test_add_from_url_http_error(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with respx.mock as m:
        m.get("https://acme.example/jobs/2").mock(return_value=httpx.Response(403, text="forbidden"))
        with Session() as s, httpx.Client() as client, pytest.raises(SourceError, match="403"):
            add_job_from_url(s, FakeLLM([]), "m", client, "https://acme.example/jobs/2")


def test_same_text_twice_returns_same_job(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with Session() as s:
        a = add_job_from_text(s, FakeLLM([extracted()]), "m", text="same", url=None)
        b = add_job_from_text(s, FakeLLM([extracted()]), "m", text="same", url=None)
        assert a.id == b.id


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8781/",
    "http://localhost/jobs",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
    "http://[::1]/",
    "file:///etc/passwd",
    "ftp://example.com/x",
])
def test_add_from_url_rejects_non_public_targets(tmp_path, url):
    Session = open_db(tmp_path / "t.db")
    with Session() as s, httpx.Client() as client, pytest.raises(SourceError, match="public http"):
        add_job_from_url(s, FakeLLM([]), "m", client, url)


def test_add_from_url_revalidates_redirects(tmp_path):
    Session = open_db(tmp_path / "t.db")
    with respx.mock as m:
        m.get("https://acme.example/jobs/3").mock(return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"}))
        with Session() as s, httpx.Client() as client, pytest.raises(SourceError, match="public http"):
            add_job_from_url(s, FakeLLM([]), "m", client, "https://acme.example/jobs/3")
