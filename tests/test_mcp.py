import asyncio
import json

from fastmcp import Client

from jobgent.mcp_server import build_mcp

EXPECTED = {
    "profile_get", "profile_update", "profile_set_verified", "profile_import_jobkiller", "profile_get_voice",
    "profile_set_voice", "profile_notes_append", "profile_set_master_cv", "jobs_fetch", "jobs_list", "job_get",
    "job_add", "job_score", "pack_create", "pack_get", "application_set_status", "applications_list", "stats",
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
