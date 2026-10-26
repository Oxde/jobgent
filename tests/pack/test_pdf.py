import pytest

from jobgent.pack.pdf import html_to_pdf

pytestmark = pytest.mark.slow


def test_html_to_pdf_one_page(tmp_path):
    pytest.importorskip("playwright")
    out = tmp_path / "x.pdf"
    try:
        pages = html_to_pdf("<html><body><p>hi</p></body></html>", out)
    except RuntimeError as e:  # chromium not installed on this machine
        pytest.skip(str(e))
    assert pages == 1 and out.stat().st_size > 500


def test_html_to_pdf_counts_pages(tmp_path):
    pytest.importorskip("playwright")
    html = "<html><body>" + "<p style='page-break-after: always'>a</p>" * 2 + "<p>b</p></body></html>"
    try:
        pages = html_to_pdf(html, tmp_path / "y.pdf")
    except RuntimeError as e:
        pytest.skip(str(e))
    assert pages == 3


def test_full_times_cv_fits_one_a4_page(tmp_path):
    """A CV the size of the author's real one (3 jobs, 2 schools, 4 skill groups, 3 projects) must fit one A4 page."""
    pytest.importorskip("playwright")
    from datetime import date

    from jobgent.pack.render import render_cv_html
    from jobgent.pack.tailor import general_cv
    from jobgent.profile.models import Education, Experience, Language, Personal, Profile, Project, SearchProfile, Skill

    long = "Developed automated trading bots processing over $1M in trading volume with 150+ active users and dashboards"
    p = Profile(
        personal=Personal(name="Firstname Lastname", headline="Software Engineer", location="Netherlands", phone="+31600000000",
                          email="name@example.com", linkedin="https://www.linkedin.com/in/firstname-lastname-123456789", github="https://github.com/name"),
        summary=" ".join(["AI-focused student with hands-on experience building GenAI solutions, multi-agent systems and chatbots."] * 4),
        experience=[Experience(company="Company", title="GenAI Intern, Chatbot team", period="Sep 2025 - Feb 2026", bullets=[long]),
                    Experience(company="Freelance", title="Automation Engineer", location="Netherlands", period="2024 - 2025", bullets=[long] * 3),
                    Experience(company="Freelance", title="Full-Stack Web Developer", location="Netherlands", period="2023 - 2024", bullets=[long] * 2)],
        education=[Education(institution="University of Applied Sciences", degree="Applied Mathematics & Data Science", location="Netherlands", period="Sep 2023 - Present", gpa="8.2/10", details="ongoing studies in mathematical modeling, statistical analysis, and machine learning")] * 2,
        skills=[Skill(name=f"Skill {i}", category=f"Group {i // 6}") for i in range(24)],
        skills_note="Excellent communication, collaboration, and team leadership skills with proven track record in multinational environments",
        projects=[Project(name="Project", description=long, link="https://github.com/name/project")] * 3,
        languages=[Language(name="English", level="C1")],
        search=SearchProfile(start_from=date(2027, 2, 1), start_to=date(2027, 4, 1)),
    )
    try:
        pages = html_to_pdf(render_cv_html(p, general_cv(p), None, "times"), tmp_path / "cv.pdf")
    except RuntimeError as e:
        pytest.skip(str(e))
    assert pages == 1


def test_fit_shrinks_a_slight_overflow_to_one_page(tmp_path):
    pytest.importorskip("playwright")
    html = "<html><head><style>@page{size:A4;margin:0}body{margin:0;padding:12mm;font-size:12pt}</style></head><body>" + "<p>line</p>" * 32 + "</body></html>"
    try:
        plain = html_to_pdf(html, tmp_path / "a.pdf")
        fitted = html_to_pdf(html, tmp_path / "b.pdf", fit=True)
    except RuntimeError as e:
        pytest.skip(str(e))
    assert plain == 2 and fitted == 1


def test_fit_gives_up_on_real_two_page_content(tmp_path):
    pytest.importorskip("playwright")
    html = "<html><body>" + "<p style='page-break-after: always'>a</p><p>b</p></body></html>"
    try:
        assert html_to_pdf(html, tmp_path / "c.pdf", fit=True) == 2
    except RuntimeError as e:
        pytest.skip(str(e))
