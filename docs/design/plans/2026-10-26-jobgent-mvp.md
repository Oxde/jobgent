# Jobgent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local internship copilot: profile → automatic job fetch from NL sources → classified, scored feed → per-job CV + cover letter pack → tracker, all driven through an MCP server (and a CLI), with a small web UI last.

**Architecture:** One Python package `jobgent` with pure functions per stage (sources → ingest → classify → score → pack → track) over a SQLite DB and a file-based profile in `$JOBGENT_HOME` (default `~/.jobgent`). Three thin interfaces call the same service functions: FastMCP server (stdio), Typer CLI, FastAPI + htmx web UI. All LLM calls go through one `llm.py` wrapper that returns validated pydantic models.

**Tech Stack:** Python 3.12, `uv`, pydantic 2, SQLAlchemy 2 (typed, sync), httpx, anthropic SDK, fastmcp, typer, PyYAML, Playwright (chromium), FastAPI + Jinja2 + htmx, pytest + respx. Exact pinned versions.

**Spec:** `docs/superpowers/specs/2026-10-26-jobgent-design.md`

## Global Constraints

- Strict typing: pydantic models and dataclasses; no `Any`, no untyped returns. `mypy --strict` clean on `jobgent/`.
- Errors explicit, with context (source name, job id, HTTP status + body excerpt). No silent fallbacks.
- Dependencies pinned to exact versions in `pyproject.toml`.
- Secrets only from env; `Settings` also reads `~/.config/secrets/env` (KEY=VALUE lines) if it exists. A missing key raises `MissingSecretError("ANTHROPIC_API_KEY")` only when first needed.
- No personal data in the repo. All user data under `JOBGENT_HOME`. `.gitignore` excludes `.env`, `*.db`, `.jobgent/`.
- Models: `claude-haiku-4-5-20251001` for classify/score; `claude-sonnet-4-5` for CV/letter. Both named in `Settings`, overridable by env.
- Tests never touch the network: `respx` mocks httpx; LLM calls mocked via an injectable `LLM` protocol.
- PDF: A4, one page, selectable text.
- Hard rule everywhere: generated CV/letter content may only contain facts from `profile.yaml`.
- Git: ask Mark before every commit; account Oxde; ask before creating the GitHub repo / first push.

## Review Focus

1. A posting that says "Dutch is a plus" must stay in the feed (penalty, not excluded); "fluent Dutch required" must be excluded. Test in Task 7.
2. The same job from LinkedIn and from the company's Greenhouse board must appear once. Test in Task 6.
3. `pack_create` on an unverified profile must refuse with a clear message, not generate. Test in Task 11.
4. A CV draft that mentions a tool absent from the profile must fail the no-invention check with the offending claim named. Test in Task 10.
5. `jobs_fetch` with no `APIFY_TOKEN` must still fetch company boards and report LinkedIn as skipped with the missing variable named. Test in Task 12.

---

### Task 1: Project skeleton, settings, secrets

**Files:**
- Create: `pyproject.toml`, `README.md`, `LICENSE` (MIT), `.gitignore`, `.env.example`, `jobgent/__init__.py`, `jobgent/config.py`, `jobgent/errors.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (pydantic `BaseSettings`-free, plain pydantic model) with fields `home: Path`, `anthropic_api_key: str | None`, `apify_token: str | None`, `fast_model: str`, `smart_model: str`, `db_path: Path` (= home/jobgent.db), `profile_dir: Path`, `applications_dir: Path`; `load_settings(env: Mapping[str,str] | None = None, secrets_file: Path | None = None) -> Settings`; `Settings.require(name: Literal["ANTHROPIC_API_KEY","APIFY_TOKEN"]) -> str` raising `MissingSecretError`.
- `errors.py`: `JobgentError(Exception)`, `MissingSecretError(JobgentError)`, `SourceError(JobgentError)` with `source: str`, `ProfileNotVerifiedError`, `InventedClaimError` with `claims: list[str]`.

- [ ] **Step 1: Write failing tests**

```python
def test_settings_reads_secrets_file(tmp_path):
    f = tmp_path / "env"; f.write_text("ANTHROPIC_API_KEY=sk-test\nexport APIFY_TOKEN=ap-test\n")
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path / "home")}, secrets_file=f)
    assert s.anthropic_api_key == "sk-test" and s.apify_token == "ap-test"
    assert s.db_path == tmp_path / "home" / "jobgent.db"

def test_require_missing_names_variable(tmp_path):
    s = load_settings(env={"JOBGENT_HOME": str(tmp_path)}, secrets_file=tmp_path / "nope")
    with pytest.raises(MissingSecretError, match="APIFY_TOKEN"):
        s.require("APIFY_TOKEN")
```

- [ ] **Step 2: Run, expect ImportError**
- [ ] **Step 3: `uv init --package`, pin deps (anthropic, fastmcp, typer, pydantic, sqlalchemy, httpx, pyyaml, playwright, fastapi, uvicorn, jinja2, python-multipart; dev: pytest, respx, mypy, types-PyYAML), implement config + errors.** Env var precedence: explicit `env` > process env > secrets file. Default `secrets_file` = `~/.config/secrets/env`.
- [ ] **Step 4: `uv run pytest -q` passes; `uv run mypy --strict jobgent` clean**
- [ ] **Step 5: Ask Mark, then commit `chore: scaffold jobgent`**

### Task 2: Profile models and store

**Files:**
- Create: `jobgent/profile/__init__.py`, `jobgent/profile/models.py`, `jobgent/profile/store.py`, `jobgent/profile/default_voice.md`
- Test: `tests/profile/test_store.py`, fixture `tests/fixtures/jobkiller_profile.json` (synthetic, NOT Mark's real data)

**Interfaces:**
- `models.py`: `Profile` with `verified: bool = False`, `personal: Personal(name, location, email, phone, linkedin, github)`, `education: list[Education(institution, degree, period, status, gpa, details)]`, `experience: list[Experience(company, title, period, bullets)]`, `projects: list[Project(name, description, tech, link)]`, `skills: list[Skill(name, evidence: str)]`, `languages: list[Language(name, level)]`, `preferences: Preferences(weekly_goal: int = 10, remote_ok: bool = True, eu_citizen: bool | None = None)`, `search: SearchProfile(keywords: list[str], locations: list[str] = ["Netherlands"], internship_types: list[Literal["graduation","work_placement","any"]] = ["any"], months_min: int = 4, months_max: int = 6, paid_required: bool = False, start_from: date, start_to: date, languages: list[str] = ["en"])`. Default keywords per spec resolutions.
- `store.py`: `ProfileStore(profile_dir: Path)` with `exists() -> bool`, `load() -> Profile`, `save(p: Profile) -> None` (profile.yaml), `update(path: str, value: object) -> Profile` (dotted path like `preferences.weekly_goal` or `skills[2].evidence`; re-validates; raises `KeyError` with the path), `import_jobkiller(json_path: Path) -> Profile` (maps `user_info` keys; `verified=False`), `voice() -> str` / `set_voice(text)` (voice.md, default from `default_voice.md`), `notes_append(text)` (notes.md), `master_cv_path() -> Path` and `set_master_cv(html: str)`.

- [ ] **Step 1: Tests:** round-trip save/load; `update("preferences.weekly_goal", 15)` persists; `update("nope.x", 1)` raises KeyError mentioning `nope.x`; `import_jobkiller(fixture)` yields `verified is False`, name and education mapped; `voice()` returns default text when no file.
- [ ] **Step 2: Run, expect fail**
- [ ] **Step 3: Implement.** YAML via `yaml.safe_dump(model.model_dump(mode="json"))`. Dotted-path update: parse with a small tokenizer (`name`, `[int]`), apply on `model_dump()` dict, re-validate with `Profile.model_validate`.
- [ ] **Step 4: Tests + mypy pass**
- [ ] **Step 5: Commit `feat: profile models and store`**

### Task 3: Database

**Files:**
- Create: `jobgent/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- SQLAlchemy 2 `DeclarativeBase` models: `Job(id int pk, source str, external_id str, url str, title str, company str, location str | None, description str, posted_at datetime | None, fetched_at datetime, dedupe_key str indexed, is_internship bool | None, language str | None, dutch_required bool | None, start_hint str | None, classified_at datetime | None)` unique on `(source, external_id)`; `Match(id, job_id fk unique, total int, skills int, role int, lang_loc int, timing int, reasons json list[str], gaps json list[str], model str, created_at)`; `Application(id, job_id fk unique, status Enum[new, liked, pack_ready, applied, interview, offer, rejected, skipped], pack_dir str | None, applied_at datetime | None, notes str, updated_at)`.
- `open_db(db_path: Path) -> sessionmaker[Session]` (creates tables; `sqlite:///` with `check_same_thread=False`).

- [ ] **Step 1: Test:** `open_db(tmp)`, insert Job, duplicate `(source, external_id)` raises `IntegrityError`; Application default status `new`.
- [ ] **Step 2–4: fail → implement → pass**
- [ ] **Step 5: Commit `feat: sqlite schema`**

### Task 4: Source contract and ATS adapters

**Files:**
- Create: `jobgent/sources/__init__.py`, `jobgent/sources/base.py`, `jobgent/sources/ats.py`, `jobgent/sources/companies.py`, `data/companies.yaml`
- Test: `tests/sources/test_ats.py`, fixtures `tests/fixtures/ats/{greenhouse,lever,recruitee,homerun,ashby,workable}.json`

**Interfaces:**
- `base.py`: `RawJob(source: str, external_id: str, url: str, title: str, company: str, location: str | None, description: str, posted_at: datetime | None)` (pydantic); `SourceResult(source: str, jobs: list[RawJob], error: str | None)`; `class Source(Protocol): name: str; def fetch(self, client: httpx.Client) -> list[RawJob]`.
- `companies.py`: `Company(name: str, ats: Literal["greenhouse","lever","recruitee","homerun","ashby","workable","careers_page"], board: str, careers_url: str | None)`; `load_companies(path: Path) -> list[Company]`.
- `ats.py`: `ATSSource(company: Company)` implementing `Source`, `name = f"ats:{company.ats}:{company.board}"`. Endpoints: Greenhouse `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`; Lever `https://api.lever.co/v0/postings/{board}?mode=json`; Recruitee `https://{board}.recruitee.com/api/offers/`; Homerun `https://{board}.homerun.co/api/v1/jobs` (builder verifies; if no public JSON, parse the embedded JSON of the careers page); Ashby `https://api.ashbyhq.com/posting-api/job-board/{board}`; Workable `https://apply.workable.com/api/v1/widget/accounts/{board}`. HTML descriptions → text via a small `html_to_text(html: str) -> str` helper in `base.py` (stdlib `html.parser`). Non-2xx → `SourceError(source, f"HTTP {status}: {body[:200]}")`.
- `data/companies.yaml`: ~40 NL companies; builder verifies each board id by fetching once (manual, not in tests) and keeps only the ones that respond.

- [ ] **Step 1: Tests:** one per ATS using respx + fixture: returns ≥1 `RawJob` with title, url, description text (no tags); 500 → `SourceError` whose message contains the status.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: ATS job sources`**

### Task 5: Apify (LinkedIn) source

**Files:**
- Create: `jobgent/sources/apify.py`
- Test: `tests/sources/test_apify.py`, fixture `tests/fixtures/apify_linkedin.json`

**Interfaces:**
- `ApifyLinkedInSource(token: str, keywords: list[str], locations: list[str], max_per_query: int = 100, actor: str = ACTOR_ID)` implementing `Source`, `name = "linkedin"`. Builder picks a maintained no-login actor (candidates: `meka.im/linkedin-jobs-scraper`, `crawlworks/linkedin-job-scraper`, `truefetch/linkedin-job-search`); the actor id is a `Settings` field `linkedin_actor` so Mark can swap it. Uses `POST https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?token=...` with `timeout=300`. Maps dataset items to `RawJob(source="linkedin", external_id=<job id from url>)`.

- [ ] **Step 1: Test:** respx mocks the run-sync endpoint with the fixture → N `RawJob`s; 401 → `SourceError` mentioning "APIFY".
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: linkedin via apify`**

### Task 6: Ingest and dedupe

**Files:**
- Create: `jobgent/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- `dedupe_key(company: str, title: str) -> str`: lowercase, strip punctuation and the words `intern, internship, stage, stagiair, m/f/d, (m/w/d), 2027, 2026`, collapse spaces → `f"{company}|{title}"`.
- `upsert_jobs(session: Session, jobs: Iterable[RawJob]) -> IngestReport(inserted: int, updated: int, duplicates: int)`: existing `(source, external_id)` → update description/posted_at; existing `dedupe_key` from another source → count as duplicate, keep the ATS version if either is ATS (prefer `source.startswith("ats:")`), else keep the first.
- `run_fetch(session: Session, sources: list[Source], client: httpx.Client) -> FetchReport(results: list[SourceResult], ingest: IngestReport)`: each source isolated; exceptions become `SourceResult.error = f"{type(e).__name__}: {e}"`; never raises for a single source.

- [ ] **Step 1: Tests:** same company+title from `linkedin` and `ats:greenhouse:x` → one row, source is the ATS one; a source that raises leaves others ingested and its error in the report; `dedupe_key("Picnic", "Data Science Intern (m/f/d) 2027")=="picnic|data science"`.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: ingest with cross-source dedupe`**

### Task 7: LLM wrapper and classifier

**Files:**
- Create: `jobgent/llm.py`, `jobgent/classify.py`, `jobgent/prompts/classify.md`
- Test: `tests/test_llm.py`, `tests/test_classify.py`

**Interfaces:**
- `llm.py`: `class LLM(Protocol): def complete_json[T: BaseModel](self, *, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2048) -> T`. `AnthropicLLM(api_key: str)` implements it with the Messages API, forcing JSON via a tool definition built from `schema.model_json_schema()` (tool use with `tool_choice`), and raises `LLMError` with the raw text when validation fails. `FakeLLM(responses: list[BaseModel])` for tests.
- `classify.py`: `prefilter(title: str) -> bool` (true if title contains any of: intern, internship, stage, stagiair, afstudeer, graduation, trainee, working student); `Classification(is_internship: bool, language: Literal["en","nl","other"], dutch_required: bool, dutch_plus: bool, start_hint: str | None, months: int | None, paid: bool | None)`; `classify_jobs(session, llm: LLM, model: str, batch: int = 10) -> int` classifies unclassified jobs that pass `prefilter` (others: `is_internship=False`, `classified_at=now`), writes to `Job`. `dutch_required` only when Dutch is demanded; "a plus/nice to have" → `dutch_plus=True, dutch_required=False` (prompt says this explicitly).
- `feed_filter(q: Select, profile: SearchProfile) -> Select`: `is_internship`, `language in profile.languages`, `dutch_required is False`.

- [ ] **Step 1: Tests:** `prefilter("Senior Engineer")` false; `prefilter("Stagiair Data")` true; `classify_jobs` with `FakeLLM` sets fields and skips prefiltered-out titles without calling the LLM; `feed_filter` keeps a `dutch_plus=True` job and drops `dutch_required=True`; `AnthropicLLM` test with respx on `api.anthropic.com` returning a tool_use block parses into the schema.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: classification`**

### Task 8: Scoring

**Files:**
- Create: `jobgent/score.py`, `jobgent/prompts/score.md`
- Test: `tests/test_score.py`

**Interfaces:**
- `ScoreOutput(skills: int, role: int, lang_loc: int, timing: int, reasons: list[str], gaps: list[str])` with ranges skills 0–50, role 0–20, lang_loc 0–15, timing 0–15 (pydantic `Field(ge, le)`); `total = sum - (10 if dutch_plus else 0)`, floored at 0.
- `score_jobs(session, llm, model, profile: Profile, limit: int | None = None) -> int`: scores feed jobs without a `Match`; writes `Match`. Prompt gets `profile` (yaml dump without personal contact fields) + job title/company/description (truncated to 6k chars).
- `profile_for_prompt(p: Profile) -> str` strips `personal`.

- [ ] **Step 1: Tests:** FakeLLM returns `ScoreOutput(skills=40, role=20, lang_loc=15, timing=10, ...)` → `Match.total == 85`; with `dutch_plus=True` → 75; already-matched jobs are not re-sent; `profile_for_prompt` output lacks the email.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: match scoring`**

### Task 9: Manual job add (URL or text)

**Files:**
- Create: `jobgent/sources/manual.py`, `jobgent/prompts/extract_job.md`
- Test: `tests/sources/test_manual.py`

**Interfaces:**
- `ExtractedJob(title, company, location: str | None, description, posted_at: datetime | None)`; `add_job_from_text(session, llm, model, text: str, url: str | None) -> Job` (source `manual`, external_id = sha1 of url or text); `add_job_from_url(session, llm, model, client: httpx.Client, url: str) -> Job` (GET, `html_to_text`, then same as text; non-2xx → `SourceError("manual", ...)`).

- [ ] **Step 1: Tests:** text → Job with fields from FakeLLM; URL via respx; 403 → SourceError with status.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: add job from url or text`**

### Task 10: Application pack: tailor, letter, verify, PDF

**Files:**
- Create: `jobgent/pack/__init__.py`, `jobgent/pack/tailor.py`, `jobgent/pack/letter.py`, `jobgent/pack/verify.py`, `jobgent/pack/pdf.py`, `jobgent/pack/render.py`, `jobgent/prompts/tailor.md`, `jobgent/prompts/letter.md`, `jobgent/prompts/verify.md`, `jobgent/pack/default_cv.html` (Jinja2 template, A4 CSS, `@page { size: A4; margin: 14mm }`)
- Test: `tests/pack/test_tailor.py`, `tests/pack/test_verify.py`, `tests/pack/test_pdf.py` (marked `slow`, skipped if chromium missing)

**Interfaces:**
- `tailor.py`: `TailoredCV(summary: str, experience: list[Experience], projects: list[Project], skills: list[str], education: list[Education], change_summary: list[str])`; `tailor_cv(llm, model, profile: Profile, job: Job) -> TailoredCV`. Prompt: select and rephrase only; order by relevance; no new facts; ≤ one A4 page (~450 words).
- `letter.py`: `CoverLetter(body: str)`; `write_letter(llm, model, profile, job, voice: str) -> CoverLetter` (≤ 250 words, 3 paragraphs: why them, what I bring (2 concrete facts), ask).
- `verify.py`: `VerifyOutput(unsupported_claims: list[str])`; `verify_against_profile(llm, model, profile, text: str) -> None` raising `InventedClaimError(claims)` when non-empty. Called on CV text and on the letter.
- `render.py`: `render_cv_html(profile: Profile, cv: TailoredCV, template_path: Path | None) -> str` (Jinja2; `template_path=None` → `default_cv.html`; `master_cv.html` support = template with the same Jinja variables, documented in README).
- `pdf.py`: `html_to_pdf(html: str, out: Path) -> int` returns page count (Playwright sync, `format="A4"`, `print_background=True`, `prefer_css_page_size=True`; page count via `pypdf`); `ensure_one_page(...)` lives in Task 11.

- [ ] **Step 1: Tests:** `tailor_cv` returns model from FakeLLM and `change_summary` non-empty; `verify_against_profile` with FakeLLM returning `["Kubernetes"]` raises `InventedClaimError` whose message contains "Kubernetes", with `[]` returns None; `render_cv_html` output contains the name and `size: A4`; slow test: `html_to_pdf("<p>hi</p>")` → 1.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: application pack generation`**

### Task 11: Pack orchestrator and tracker

**Files:**
- Create: `jobgent/pack/create.py`, `jobgent/tracker.py`, `jobgent/service.py`
- Test: `tests/pack/test_create.py`, `tests/test_tracker.py`

**Interfaces:**
- `create.py`: `PackResult(dir: Path, cv_html: Path, cv_pdf: Path, letter_md: Path, change_summary: list[str], apply_url: str, apply_email: str | None)`; `create_pack(settings, session, llm, store: ProfileStore, job_id: int, pdf: Callable[[str, Path], int] = html_to_pdf) -> PackResult`. Steps: profile `verified` check (`ProfileNotVerifiedError`) → tailor → render → verify CV text (strip tags) → letter → verify letter → pdf; if pages > 1: re-run tailor with `extra_instruction="shorten by 20%"` once; still > 1 → `JobgentError("CV is N pages after retry")`. `apply_email` = first email regex match in `job.description`. Writes `meta.json`. Sets `Application.status = pack_ready`, `pack_dir`. Dir name: `slugify(company)-slugify(title)-{job_id}` under `settings.applications_dir`.
- `tracker.py`: `set_status(session, job_id, status, notes: str | None) -> Application` (applied → sets `applied_at` now); `weekly_stats(session, goal: int) -> WeeklyStats(applied_this_week: int, goal: int, by_status: dict[str,int])` (week = Monday-based ISO week).
- `service.py`: a `Services` dataclass bundling `settings, sessionmaker, store, llm_factory: Callable[[], LLM], http_client_factory` and `build_services(settings) -> Services` so MCP/CLI/web share construction. `llm_factory` calls `settings.require("ANTHROPIC_API_KEY")` lazily.

- [ ] **Step 1: Tests:** unverified profile → `ProfileNotVerifiedError`, no files written; verified + FakeLLM + fake pdf returning 1 → files exist, status `pack_ready`, `apply_email` extracted from a description containing `jobs@acme.nl`; fake pdf returning 2 then 1 → success with tailor called twice; always 2 → `JobgentError` with "2 pages". Tracker: `set_status(applied)` sets `applied_at`; `weekly_stats` counts only this ISO week.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: pack orchestration and tracker`**

### Task 12: MCP server and CLI

**Files:**
- Create: `jobgent/mcp_server.py`, `jobgent/cli.py`, `jobgent/fetch.py`; add `[project.scripts] jobgent = "jobgent.cli:app"`
- Test: `tests/test_fetch.py`, `tests/test_mcp.py` (FastMCP in-process client), `tests/test_cli.py` (Typer `CliRunner`)

**Interfaces:**
- `fetch.py`: `build_sources(settings, profile: Profile, companies: list[Company]) -> tuple[list[Source], list[str]]` returns sources plus `skipped: list[str]` (e.g. `"linkedin: APIFY_TOKEN not set"`); `fetch_all(services, classify: bool = True, score: bool = True) -> FetchSummary(report: FetchReport, skipped: list[str], classified: int, scored: int)`. Classify/score raise `MissingSecretError` for the Anthropic key only after fetching has been saved.
- MCP tools (FastMCP, names exact, docstrings explain when to use each; all return pydantic models or lists thereof):
  `profile_get() -> Profile`, `profile_update(path: str, value: str) -> Profile` (value parsed as YAML scalar/list), `profile_set_verified(verified: bool) -> Profile`, `profile_import_jobkiller(json_path: str) -> Profile`, `profile_get_voice() -> str`, `profile_set_voice(text: str) -> str`, `profile_notes_append(text: str) -> str`, `profile_set_master_cv(html: str) -> str`,
  `jobs_fetch(classify: bool = True, score: bool = True) -> FetchSummary`,
  `jobs_list(min_score: int = 0, status: str | None = None, source: str | None = None, limit: int = 30) -> list[JobSummary(id, title, company, location, score, status, url, posted_at)]` sorted by score desc,
  `job_get(job_id: int) -> JobDetail(JobSummary + description, reasons, gaps, classification)`,
  `job_add(url: str | None = None, text: str | None = None) -> JobDetail` (scores it immediately),
  `job_score(job_id: int) -> JobDetail` (re-score),
  `pack_create(job_id: int) -> PackResult`, `pack_get(job_id: int) -> PackResult` (reads meta.json; error if none),
  `application_set_status(job_id: int, status: str, notes: str | None = None) -> JobSummary`,
  `applications_list(status: str | None = None) -> list[JobSummary]`,
  `stats() -> WeeklyStats`.
- CLI (Typer) commands mirroring: `init`, `profile show|set|verify|import|voice`, `fetch`, `jobs [--min-score] [--status]`, `job <id>`, `add --url|--text`, `pack <id>`, `status <id> <status>`, `stats`, `mcp` (runs the server, stdio), `web` (Task 13).

- [ ] **Step 1: Tests:** `build_sources` without APIFY token → linkedin in `skipped` with "APIFY_TOKEN" in the string and ATS sources present; MCP client lists all tool names above; `jobs_list` returns scored jobs sorted desc; `profile_update("preferences.weekly_goal","12")` → 12 (int); CLI `stats` exits 0.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: mcp server and cli`**
- [ ] **Step 6: Write README sections: install (`uv sync`, `uv run playwright install chromium`), secrets, `claude mcp add jobgent -- uv --directory /path run jobgent mcp`, the daily loop as agent prompts.**

### Task 13: Web UI

**Files:**
- Create: `jobgent/web/app.py`, `jobgent/web/templates/{base,feed,job,tracker}.html`, `jobgent/web/static/style.css`
- Test: `tests/web/test_app.py` (FastAPI `TestClient`)

**Interfaces:**
- `create_app(services: Services) -> FastAPI`. Routes: `GET /` feed (query `min_score`, `status`), `GET /jobs/{id}` detail with reasons/gaps, pack preview (letter text, link to PDF) and buttons; `POST /jobs/{id}/pack` (htmx, returns the pack fragment), `POST /jobs/{id}/status` (form `status`), `GET /tracker` board by status + weekly goal bar, `GET /packs/{id}/cv.pdf` static file. htmx from cdnjs pinned version; dark minimal CSS; single column ≤ 480px.

- [ ] **Step 1: Tests:** `GET /` 200 and contains a seeded job title; `POST /jobs/1/status` with `applied` → tracker shows it under Applied; `GET /jobs/999` → 404 with message.
- [ ] **Step 2–4**
- [ ] **Step 5: Commit `feat: web ui`**

### Task 14: Live smoke (manual, no tests)

- [ ] Verify `data/companies.yaml` boards against the real APIs; drop dead ones; note count in README.
- [ ] `uv run jobgent init && uv run jobgent fetch` with no keys → ATS jobs in DB, linkedin reported skipped.
- [ ] Once Mark adds keys: full `fetch`, `jobs`, `pack <id>`, open the PDF, check one page and A4.
