"""A complete demo with a made-up student, so anyone can try Jobgent without personal data or an API key.
Everything here is fictional; companies are generic. Run `jobgent demo` then `JOBGENT_HOME=~/.jobgent-demo jobgent web`."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from jobgent.config import load_settings
from jobgent.db import AgentRun, Application, ApplicationEvent, Evaluation, Job, Match, Status, open_db
from jobgent.documents import save_document
from jobgent.errors import JobgentError
from jobgent.ingest import dedupe_key
from jobgent.pack.create import PackResult, pack_dir_for
from jobgent.pack.render_pack import rerender
from jobgent.pack.tailor import general_cv
from jobgent.profile.models import (Education, Experience, Language, Personal, Preferences, Profile, Project,
                                    SearchProfile, Skill)
from jobgent.profile.store import ProfileStore

MARKER = ".jobgent-demo"

PROFILE = Profile(
    verified=True,
    personal=Personal(name="Sam Jansen", headline="Data Science student", location="Amsterdam", email="sam.jansen@example.com",
                      phone="+31600000000", linkedin="https://www.linkedin.com/in/example", github="https://github.com/example"),
    summary="Data Science student who builds small AI tools: a course-planning chatbot used by 300 students and a Python pipeline that cleans public transport data. Looking for an AI or data internship from February 2027.",
    experience=[
        Experience(company="Campus IT Helpdesk", title="Student Developer (part-time)", location="Amsterdam", period="Sep 2024 - Present",
                   bullets=["Built a course-planning chatbot in Python and LangChain used by 300 students", "Automated weekly reports with pandas, saving the team 4 hours a week"]),
        Experience(company="Fietsenwinkel De Spaak", title="Web Developer (freelance)", location="Utrecht", period="Jan 2023 - Jun 2024",
                   bullets=["Built the shop's website with Flask and PostgreSQL", "Added online booking for repairs"]),
    ],
    education=[Education(institution="University of Amsterdam", degree="BSc Data Science", location="Amsterdam", period="Sep 2023 - 2027", gpa="7.8/10",
                         details="machine learning, statistics, databases")],
    projects=[
        Project(name="TransitClean", description="Python pipeline that cleans and joins public transport open data", tech=["Python", "pandas", "Docker"], link="https://github.com/example/transitclean"),
        Project(name="StudyBuddy", description="Course-planning chatbot with retrieval over the study guide", tech=["Python", "LangChain", "FastAPI"], link="https://github.com/example/studybuddy"),
    ],
    skills=[Skill(name=n, category=c) for c, names in {
        "AI & Data": ["Python", "pandas", "LangChain", "Prompt engineering", "scikit-learn"],
        "Engineering": ["FastAPI", "Flask", "SQL", "PostgreSQL", "Docker", "Git"],
    }.items() for n in names],
    languages=[Language(name="English", level="C1"), Language(name="Dutch", level="Native")],
    facts=["Available from 1 February 2027, 5 days a week", "EU citizen"],
    preferences=Preferences(weekly_goal=8, template="times", eu_citizen=True),
    search=SearchProfile(keywords=["AI intern", "data science intern", "machine learning intern"], locations=["Amsterdam"],
                         start_from=date(2027, 2, 1), start_to=date(2027, 3, 31)),
)

# title, company, location, score, verdict, reason, status, days_ago_applied, extra
JOBS: list[tuple[str, str, str, int, str, str, Status | None, int | None]] = [
    ("AI Engineering Intern", "Northwind Analytics", "Amsterdam", 91, "apply", "Strong fit (91): you cover Python, LangChain.", Status.pack_ready, None),
    ("Data Science Intern", "Tulip Mobility", "Amsterdam", 84, "apply", "Strong fit (84): you cover pandas, SQL.", Status.liked, None),
    ("Machine Learning Intern", "Canal Health", "Amsterdam", 79, "apply", "Strong fit (79): you cover Python, scikit-learn.", Status.applied, 9),
    ("GenAI Product Intern", "Harbor Retail", "Amsterdam", 72, "consider", "Possible (72), missing a must-have: product analytics.", Status.interview, 14),
    ("Data Engineering Intern", "Polder Energy", "Amsterdam", 68, "consider", "Possible (68), a partial fit.", Status.rejected, 20),
    ("Software Engineering Intern", "Bicycle Cloud", "Amsterdam", 75, "apply", "Strong fit (75): you cover FastAPI, Docker.", None, None),
    ("AI Research Intern", "Tram Labs", "Remote (Netherlands)", 81, "apply", "Strong fit (81): you cover Python, LangChain.", None, None),
    ("Analytics Intern", "Dyke Finance", "Amsterdam", 58, "consider", "Possible (58), a partial fit.", None, None),
    ("Stagiair Data", "Molen Logistiek", "Amsterdam", 40, "skip", "The posting requires Dutch.", None, None),
    ("Business Analyst Intern", "Gracht Consulting", "Amsterdam", 52, "consider", "Possible (52), a partial fit.", None, None),
]


def build_demo(home: Path) -> Path:
    if (home / "profile" / "profile.yaml").is_file() and not (home / MARKER).is_file():
        raise JobgentError(f"{home} has a profile and is not a demo folder; refusing to overwrite it.")
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    (home / MARKER).write_text("Made-up demo data. Safe to delete.\n")
    settings = load_settings(env={"JOBGENT_HOME": str(home)}, secrets_file=home / "no-secrets")
    store = ProfileStore(settings.profile_dir)
    store.save(PROFILE)
    store.set_voice("Short, concrete, friendly. First person. No buzzwords.")
    Session = open_db(settings.db_path)
    now = datetime.now()
    with Session() as s:
        s.add(AgentRun(status="done", fetched=212, evaluated=10, queued=6, finished_at=now - timedelta(hours=2), note="Demo run."))
        for i, (title, company, location, score, verdict, reason, status, applied_days) in enumerate(JOBS, start=1):
            description = (f"{company} is looking for a {title.lower()} to join our team in {location}. You will work with Python and data to build "
                           f"internal tools. Requirements: currently enrolled student, Python, SQL; experience with LLMs is a plus. "
                           f"Start: February 2027, 5-6 months. {'Fluent Dutch required.' if 'Stagiair' in title else 'English is our working language.'}")
            job = Job(id=i, source="demo", external_id=str(i), url=f"https://example.com/jobs/{i}", title=title, company=company, location=location,
                      description=description, posted_at=now - timedelta(days=3 + i * 4), fetched_at=now, dedupe_key=dedupe_key(company, title, location),
                      in_region=True, is_internship=True, language="en", dutch_required="Stagiair" in title, dutch_plus=False,
                      classified_at=now, start_hint="February 2027", months=6, live_status="open",
                      deadline=(date.today() + timedelta(days=5 if i == 1 else 20 + i)).strftime("%d %b %Y"))
            s.add(job)
            s.flush()
            s.add(Match(job_id=i, total=score, skills=min(50, score // 2), role=18, lang_loc=14, timing=12,
                        reasons=["Your StudyBuddy chatbot matches their LLM work", "Python and SQL are in your profile"],
                        gaps=["Product analytics"] if verdict == "consider" else [], keywords=["Python", "SQL", "LLM", "pandas", "Docker", "Tableau"], model="demo"))
            s.add(Evaluation(job_id=i, verdict=verdict, verdict_reason=reason, summary=title, deadline=job.deadline, coverage=score - 10, model="demo",
                             gates=[{"name": "language", "status": "fail" if "Stagiair" in title else "pass", "reason": "The posting requires Dutch." if "Stagiair" in title else "Works in English."},
                                    {"name": "location", "status": "pass", "reason": location}],
                             requirements=[
                                 {"text": "Python", "kind": "skill", "importance": "critical", "basis": "stated", "status": "covered", "evidence": "StudyBuddy chatbot"},
                                 {"text": "SQL", "kind": "skill", "importance": "high", "basis": "stated", "status": "partial", "evidence": "SQL in skills"},
                                 {"text": "Experience with LLMs", "kind": "experience", "importance": "nice", "basis": "stated", "status": "covered", "evidence": "LangChain chatbot"},
                                 {"text": "Tableau", "kind": "skill", "importance": "nice", "basis": "stated", "status": "gap", "evidence": ""},
                             ]))
            if status is not None:
                applied_at = now - timedelta(days=applied_days) if applied_days is not None else None
                furthest = {"pack_ready": "pack_ready", "liked": "liked", "applied": "applied", "interview": "interview", "rejected": "applied"}[status.value]
                s.add(Application(job_id=i, status=status, applied_at=applied_at, furthest_stage=furthest,
                                  interview_at=now + timedelta(days=1, hours=1) if status == Status.interview else None))
                s.add(ApplicationEvent(job_id=i, kind="status", from_status="new", to_status=status.value, text=f"Moved to {status.value.replace('_', ' ')}"))
        s.commit()

        first = s.get(Job, 1)
        assert first is not None
        job = first
        cv = general_cv(PROFILE)
        cv.change_summary = ["Led with the StudyBuddy chatbot (LLM work in the posting)", "Moved SQL into the first skills group"]
        save_document(s, 1, "cv", cv.model_dump(mode="json"), cause="written")
        save_document(s, 1, "letter", {"paragraphs": [
            "Dear Northwind Analytics team,",
            "You are building internal AI tools on top of your data, and that is exactly the kind of work I enjoy: I built StudyBuddy, a course-planning chatbot in Python and LangChain that 300 students use.",
            "At the campus helpdesk I also automated weekly reports with pandas, which saved the team 4 hours a week. I have not used Tableau yet; I learn tools like that quickly by building with them.",
            "I am available from 1 February 2027, five days a week, and would be glad to talk.",
            "Warm regards,\nSam Jansen"]}, cause="written")
        save_document(s, 1, "email", {"subject": "Application: AI Engineering Intern - Sam Jansen",
                                      "body": "Dear hiring team,\n\nPlease find attached my CV and cover letter for the AI Engineering Intern position at Northwind Analytics.\n\nKind regards,\nSam Jansen"}, cause="written")
        out = rerender(settings, s, store, job)
        result = PackResult(job_id=1, dir=out, cv_html=out / "cv.html", cv_pdf=out / "cv.pdf", letter_md=out / "cover_letter.md",
                            change_summary=cv.change_summary, apply_url=job.url, apply_email="jobs@example.com", created_at=now,
                            review_applied=["summary"], review_notes={"missed_keywords": "Docker is in your profile but not in the CV", "company_angle": "good: internal AI tools", "passive_phrasing": "none", "tone": "warm, fine"},
                            check_this=[], ats_ok=True, ats_problems=[], keywords={"covered": ["Python", "SQL", "LLM", "pandas"], "missing_but_in_profile": ["Docker"], "gap": ["Tableau"]})
        (out / "meta.json").write_text(json.dumps(result.model_dump(mode="json"), indent=2))
        app = job.application
        assert app is not None
        app.pack_dir = str(pack_dir_for(settings, job))
        s.commit()
    return home
