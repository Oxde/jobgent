# Jobgent


Internship copilot for students in the Netherlands. It finds internships, scores them against your profile, writes a tailored one-page A4 CV and a cover letter per job, and tracks your applications. **You review and submit every application yourself.** It never invents experience: every generated claim is checked against your profile.

MCP-first: run it inside Claude Code / Claude Desktop / Cursor and let the agent drive. There is also a CLI and a small local web UI.

## Setup (5 minutes)

```bash
git clone <this repo> && cd jobgent
uv sync
uv run playwright install chromium
```

Secrets go in the environment or in `~/.config/secrets/env`:

```
ANTHROPIC_API_KEY=sk-ant-...   # required for matching, CVs, letters
APIFY_TOKEN=apify_api_...      # optional: enables LinkedIn job search
```

Without `APIFY_TOKEN` the company job boards still work; LinkedIn is reported as skipped.
All your data lives in `~/.jobgent/` (override with `JOBGENT_HOME`). Nothing personal is in this repo.

## Connect to Claude

```bash
claude mcp add jobgent -- uv --directory /ABSOLUTE/PATH/jobgent run jobgent mcp
```

Then talk to it:

1. "Import my profile from `~/path/to/user_info.json`, show it to me, and fix the dates I give you." → `profile_import_jobkiller`, `profile_get`, `profile_update`
2. "Mark my profile verified." → `profile_set_verified`
3. "Fetch jobs and show me the top 10." → `jobs_fetch`, `jobs_list`
4. "Make the application pack for job 42." → `pack_create` (CV PDF + cover letter in `~/.jobgent/applications/…`)
5. "I applied to 42 by email." → `application_set_status`
6. "How am I doing this week?" → `stats`

Found a posting the search missed (e.g. on LinkedIn)? "Add this job: <url or pasted text>" → `job_add`.

## CLI

```bash
uv run jobgent init
uv run jobgent profile import ~/path/user_info.json
uv run jobgent profile set preferences.weekly_goal 12
uv run jobgent profile verify
uv run jobgent fetch            # all sources → classify → score
uv run jobgent jobs --min-score 60
uv run jobgent pack 42
uv run jobgent status 42 applied
uv run jobgent stats
uv run jobgent companies        # check every job board in data/companies.yaml
uv run jobgent web              # http://127.0.0.1:8781
```

Daily fetch with cron/launchd: `uv --directory /path/jobgent run jobgent fetch`.

## Job sources

- **Company job boards** (`data/companies.yaml`): public JSON feeds of Greenhouse, Lever, Recruitee, Homerun, Ashby and Workable. Free and reliable. Add a company: find which ATS hosts its careers page and add `{ name, ats, board }`.
- **LinkedIn** via an [Apify](https://apify.com) actor that reads LinkedIn's public job search (no login, your account is never used). Pay per result, cents per day. Actor id is `JOBGENT_LINKEDIN_ACTOR`.
- **Manual**: any URL or pasted text.

Jobs are de-duplicated across sources (the company's own posting wins). Then a model pass keeps internships in English with no Dutch requirement ("Dutch is a plus" stays in, with a small score penalty).

## How the CV is made

Your profile (`~/.jobgent/profile/profile.yaml`) is the only source of truth. For each job the model selects, orders and rephrases profile facts; a second pass lists any claim not backed by the profile and the pack fails if there is one. The CV must fit one A4 page (one automatic retry, then an error). Put your own Jinja2 template at `~/.jobgent/profile/master_cv.html` (variables: `personal`, `cv`, `languages`) to keep your own design.

## Not yet

- Indeed and a generic careers-page fallback (companies not on the six ATSs are reachable via LinkedIn or `job_add`).
- Importing a profile from a CV PDF (today: from a JobKiller `user_info` JSON, or build it with `profile_update`).
- Hidden-market open applications, swipe feed, follow-up reminders, hosting, Dutch UI.

## Development

```bash
uv run pytest -q           # no network, no API keys needed
uv run mypy --strict jobgent
```

Design: `docs/superpowers/specs/2026-10-26-jobgent-design.md`. Plan: `docs/superpowers/plans/2026-10-26-jobgent-mvp.md`.

MIT.
