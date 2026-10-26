import asyncio
import json

from fastmcp import Client

from jobgent.mcp_server import build_mcp

EXPECTED = {
    "profile_get", "profile_update", "profile_set_verified", "profile_import_jobkiller", "profile_get_voice",
    "profile_set_voice", "profile_notes_append", "profile_set_master_cv", "jobs_fetch", "jobs_list", "job_get",
    "job_add", "job_score", "pack_create", "pack_get", "application_set_status", "applications_list", "stats",
    "jobs_search", "job_evaluate", "cv_writing_guide", "agent_run", "agent_queue", "learning_gaps", "interview_prep",
}


def run(coro):
    return asyncio.run(coro)


def parse(content):
    return json.loads(content.text)


def test_mcp_exposes_all_tools(services):
    mcp = build_mcp(services)

    async def go():
        async with Client(mcp) as c:
            return {t.name for t in await c.list_tools()}

    assert EXPECTED <= run(go())


def test_jobs_list_sorted_by_score_and_profile_update(services):
    mcp = build_mcp(services)

    async def go():
        async with Client(mcp) as c:
            jobs = await c.call_tool("jobs_list", {"min_score": 0})
            prof = await c.call_tool("profile_update", {"path": "preferences.weekly_goal", "value": "12"})
            stats = await c.call_tool("stats", {})
            return jobs, prof, stats

    jobs, prof, stats = run(go())
    listed = parse(jobs[0]) if len(jobs) == 1 else [parse(c) for c in jobs]
    assert [j["title"] for j in listed] == ["Data Intern", "AI Intern"]
    assert parse(prof[0])["preferences"]["weekly_goal"] == 12
    assert parse(stats[0])["goal"] == 12


def test_cv_editing_tools(services):
    mcp = build_mcp(services)

    async def go():
        async with Client(mcp) as c:
            names = {t.name for t in await c.list_tools()}
            added = await c.call_tool("profile_add_item", {"section": "skills", "item": {"name": "SQL", "evidence": "course"}})
            outline = await c.call_tool("cv_outline", {})
            removed = await c.call_tool("profile_remove_item", {"section": "skills", "index": 0})
            return names, added, outline, removed

    names, added, outline, removed = run(go())
    assert {"profile_add_item", "profile_remove_item", "cv_outline", "cv_export_pdf"} <= names
    assert parse(added[0])["skills"][0]["name"] == "SQL"
    assert "skills[0].name: SQL" in outline[0].text and "personal.name: T" in outline[0].text
    assert parse(removed[0])["skills"] == []


def test_cv_writing_guide_tool(services):
    mcp = build_mcp(services)

    async def go():
        async with Client(mcp) as c:
            return await c.call_tool("cv_writing_guide", {})

    text = run(go())[0].text
    assert "never write a skill" in text.lower() and "Tailoring to one posting" in text
