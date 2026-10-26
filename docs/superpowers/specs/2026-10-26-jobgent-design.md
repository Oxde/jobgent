# Jobgent — design (26 Oct 2026)

Working name: **Jobgent** ("stage" = internship in Dutch; stage one of a career). Mark may rename it; nothing in the code should depend on the name beyond the package folder.

## Intent

The author (a data-science student in the Netherlands, not fluent in Dutch) needs an internship starting Feb 2027 and wants to start applying **this week**. In June 2025 he did the loop by hand: find a posting, paste it into Cursor, have an MCP tool tailor his CV from a saved profile, write a cover letter, apply via LinkedIn / company form / email. ~50 applications.

Jobgent automates that loop end to end **except the final submit**, which stays human. It is built for Mark first; later it becomes an open-source tool with paid hosting for international students in NL (the Piston pattern: ton-piston.com, France, €8.4k MRR after 2.5 months).

## Goals (day one)

1. **Knowledge base about the user.** Built once from an uploaded CV plus free-form answers (typed text or a voice-note transcript). Stored as readable files, editable by hand. This is the single source of truth: every CV and letter is derived from it.
2. **Automatic job search.** Runs daily, pulls internships in NL from several sources into one local database, de-duplicates, and filters: internship, posting in English, no "Dutch required", start date compatible.
3. **Match feed.** Each job gets a score 0–100 with reasons and gaps, computed from the knowledge base.
4. **Per-job application pack.** One command produces: tailored CV (A4 PDF, one page), cover letter, and the "how to apply" pointer (URL, or email address when the posting gives one). Hard rule: never add a skill, job, result, degree or certificate that is not in the knowledge base. The user reviews and submits.
5. **Tracker.** Status per job: new → liked → pack ready → applied → interview → offer / rejected, with dates.
6. **MCP server from day one.** Every capability above is an MCP tool, so Mark can drive the whole thing from Claude Code / Claude Desktop / Cursor by talking to an agent. The MCP is the primary interface on day one.
7. **Web UI** second: a small local site showing the feed, the pack and the tracker. Nice to have on day one; must exist before other users.

## Non-goals (day one)

- No accounts, auth, payments, hosting, Dutch translation.
- No automatic submission of applications anywhere (no LinkedIn Easy Apply bot, no form-filling bots). Competitors that do this (LazyApply, JobCopilot, AIApply) are what to avoid.
- No "hidden market" / open applications to companies without a posting (phase 2).
- No swipe UI / preference learning (phase 2).

## Anti-goals (failure even if it works)

- Invents experience. One hallucinated skill in a sent CV is a product-killing bug.
- Touches Mark's LinkedIn account in any automated way.
- Puts personal data in the repo. The repo will be open-sourced: user data lives in a separate data directory, git-ignored, default `~/.jobgent/`.
- Becomes a mess of "smart" features nobody uses before Mark has sent 10 real applications with it.

## Constraints

- Runs locally on Mark's Mac (macOS, Python 3.12 via `uv`). Must also be runnable in Docker later for hosting; no macOS-only dependencies.
- LLM: Anthropic Claude, model `claude-haiku-4-5-20251001` for bulk work (filtering, scoring); `claude-sonnet-4-5` level for writing the CV and letter is allowed if cost stays cents per application. Key from env `ANTHROPIC_API_KEY`.
- Follows `~/.claude/CLAUDE.md`: strict typing (pydantic models, no `Any`), explicit errors with context, exact pinned dependency versions, no silent fallbacks, ask before every commit, GitHub account Oxde (ask before creating the repo / first push).
- Open-source friendly: MIT licence, `.env.example`, README with a 5-minute setup.

## Decisions already made

### Job sources (all three; none is allowed to be the only one)

| Source | How | Notes |
|---|---|---|
| LinkedIn Jobs | Apify actor that scrapes LinkedIn's **public** job search (no login, Mark's account never involved). | Grey-zone; may break. Pay per result, cents per day. Env `APIFY_TOKEN`. Builder picks the actor (must be a maintained one that takes a search URL or keywords + location and returns title, company, location, description, posted date, apply URL). |
| Indeed NL | Apify actor, same way. | Same caveat. |
| Company career sites | A `companies.yaml` of NL companies that take interns, each with its ATS and board id. Adapters for the public JSON feeds of **Greenhouse, Lever, Recruitee, Homerun, Ashby, Workable**, and a generic "careers page URL + Claude extracts the postings" fallback for others. | Free, legal, reliable. Seed with ~40 companies (ASML, Philips, Booking, Adyen, ING, ABN AMRO, Heineken, Picnic, Vanderlande, NXP, Signify, Coolblue, bol, Mollie, TomTom, Catawiki, Bugaboo, Haskoning, Genmab, Metyis, Azerion, Spotler, Sportmonks, WEBB Traders, TrendWatching, Crystalloids, FreshPortal, Jaspers and others the builder verifies). Mark adds more by editing the file. |

Also: **manual add**: paste a URL or the posting text (reuse CV Craft's vacancy parser idea), for anything the search misses.

Searches are driven by a `search_profile` in the knowledge base: keywords (e.g. "data science intern", "AI intern", "software engineering intern"), locations ("Netherlands", plus cities), start window, languages. Builder picks the exact query strategy.

### Knowledge base format

Directory `~/.jobgent/profile/` (path configurable via env `JOBGENT_HOME`):
- `profile.yaml` — structured facts: personal info, education, experience, projects, skills with evidence, languages, availability, preferences (what roles, where, remote?), visa/EU status, start date. Pydantic-validated.
- `master_cv.html` — the design-preserving HTML replica of the user's own CV (reuse the earlier MCP tool's CV-to-HTML approach: screenshot + Claude vision, or import an existing HTML template directly).
- `notes.md` — free-form raw answers from onboarding (verbatim), kept so nothing is lost.
- `voice.md` — writing-style notes for cover letters (short, concrete, no corporate filler), extracted from past letters if any exist.

Bootstrap for the author: import the earlier tool's `user_info` JSON (already structured) and the saved CV template. **Read those files only; never copy them into the repo.**

### Data

SQLite at `~/.jobgent/jobgent.db` via SQLAlchemy 2 (typed). Tables: `jobs` (source, external id, url, title, company, location, description, posted_at, fetched_at, language, dutch_required, is_internship, start hints, dedupe hash), `matches` (job, score, reasons, gaps, model, created_at), `applications` (job, status, pack paths, applied_at, notes). Generated packs on disk under `~/.jobgent/applications/<company>-<title>/` (cv.html, cv.pdf, cover_letter.md, meta.json).

### Pipeline

1. `fetch` — run all sources, upsert jobs, dedupe (same company + normalised title + ~same description hash).
2. `classify` — Haiku, batched: is_internship, language, dutch_required (true only when the posting demands Dutch; "Dutch is a plus" = false), start hints. Hard pre-filters first (title keywords: intern, internship, stage, stagiair, graduate internship, afstudeer) to save tokens.
3. `score` — Haiku per job: 0–100, 3–5 reasons, gaps. Only for jobs that passed classify.
4. `pack <job>` — tailor: (a) pick which profile facts matter for this posting, (b) rewrite `master_cv.html` content (not layout) within the no-invention rule, (c) produce a diff summary of what changed, (d) write the cover letter in `voice.md` style, (e) export A4 PDF with Playwright (single page, selectable text). A post-check pass asks the model to list every claim in the output that is not supported by `profile.yaml`; if any, fail with the list.
5. `track` — set status, record applied_at.

Scheduling: a `jobgent fetch --all` CLI command; Mark runs it with a launchd/cron entry or asks the agent. No internal scheduler on day one.

### Interfaces

- **MCP server** (`jobgent mcp`, FastMCP, stdio): tools `profile_get`, `profile_update`, `profile_import_cv`, `jobs_fetch`, `jobs_list` (filters: min score, status, source, since), `job_get`, `job_add` (url or text), `job_score`, `pack_create`, `pack_get`, `application_set_status`, `applications_list`, `stats` (weekly count vs goal). Tool docs must be good: the agent is the main user.
- **CLI** (Typer) mirroring the same functions, for cron and debugging.
- **Web UI** (after MCP works): FastAPI serving a small HTML app (htmx or plain React+Vite, builder's choice; keep it one page): feed sorted by score with filters, job detail with pack preview and "mark applied", tracker board, weekly goal. Dark, minimal. Must work on a phone-width screen.

### Not decided (builder decides)

- Exact Apify actors; HTTP client; how aggressively to batch Claude calls; prompt wording; diff format for the CV changes; htmx vs React for the UI; test strategy (at minimum: unit tests for dedupe, classify pre-filters, the no-invention post-check, and the ATS adapters against saved fixture JSON; no live network in tests).

## Success, day one

Mark runs onboarding from his existing profile, runs `fetch`, sees a scored feed of real NL internships, picks one, gets a CV PDF + cover letter he would actually send, marks it applied. Then does that for 5 more jobs the same evening, from Claude Code via MCP.

## Later (not now)

Hosting + accounts (Phase 1), Stripe (Phase 2), Dutch UI, hidden market via KVK/UWV open data, swipe feed, follow-up reminders, interview prep.

## Resolutions after the builder check (26 Oct, Mark + Claude)

- **Profile facts are deferred.** Mark will fix his profile later, through Claude. Onboarding imports `default_profile.json` as a starting point and marks it `verified: false`; `profile_update` (MCP) edits any field; `pack_create` refuses to run while `verified` is false. Everything in `profile.yaml` and `search_profile` must be editable through MCP tools, no file editing required.
- **No past cover letters exist on disk.** `voice.md` starts from a short default style guide (short paragraphs, concrete, first person, no corporate filler, no "I am writing to express my interest") and is editable via `profile_update`. Later: learn from letters Mark approves.
- **Internship type, duration, paid, region, keywords** are fields of `search_profile` with placeholder defaults (type: any internship; months: 4–6; paid: not required; region: Netherlands; keywords: data science intern, AI intern, machine learning intern, software engineering intern, AI automation intern). Postings without a start date are kept and flagged `start_unknown`.
- **Scoring rubric (Claude's call):** skills & experience fit 50, role type fit 20, language & location 15, start/duration fit 15. "Dutch required" is a hard filter (excluded, kept in DB with the flag); "Dutch is a plus" costs up to 10 points. Store the four sub-scores plus total.
- **CV tailoring architecture (Claude's call):** content comes from `profile.yaml` (slots), the look comes from `master_cv.html`. Tailoring may include any profile fact and drop any section. One page enforced: model asked for one page; PDF page count checked; one retry with "shorten"; then fail with an explicit error.
- **Weekly goal:** `profile.yaml: preferences.weekly_goal`, default 10; "applied" = status set to applied.
- **Fetch failure semantics:** each source runs independently; a failing source is reported in the result with its error and the command exits non-zero, but results from the sources that worked are saved. Per-run caps: 100 results per keyword per Apify actor; configurable.
- **Secrets:** read from the environment (`ANTHROPIC_API_KEY`, `APIFY_TOKEN`); also loads `~/.config/secrets/env` if present. Missing key → explicit error naming the variable, at the moment it is needed, so fetching company feeds works with no keys at all.
