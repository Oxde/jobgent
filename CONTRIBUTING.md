# Contributing to Jobgent

Thanks for helping. Jobgent is a small codebase on purpose. Small, focused pull requests are the easiest to review.

## The easiest contribution: add a company

`data/companies.yaml` lists companies whose jobs come from a public ATS feed. To add one:

1. Open the company's careers page and find which system hosts it. The URL usually tells you: `boards.greenhouse.io/<board>`, `jobs.lever.co/<board>`, `<board>.recruitee.com`, `jobs.ashbyhq.com/<board>`, `apply.workable.com/<board>`, `<board>.homerun.co`.
2. Add one line: `- { name: Company, ats: greenhouse, board: <board> }`.
3. Run `uv run jobgent companies` to check the board answers.

## Development setup

```bash
uv sync
uv run playwright install chromium
(cd frontend && npm ci --ignore-scripts)
uv run jobgent demo                                # made-up data, safe to break
JOBGENT_HOME=~/.jobgent-demo uv run jobgent web     # backend on 8781
(cd frontend && npm run dev)                       # frontend with hot reload, proxies /api to 8781
```

Before you open a pull request:

```bash
uv run pytest -q              # no network, no API keys
uv run mypy --strict jobgent
(cd frontend && npm run build)
```

## Rules the code follows

- **The model judges, code decides.** Models extract and draft into typed pydantic schemas. Verdicts, coverage, evidence checks and "is this safe to send" are plain, tested code. Don't move a decision into a prompt.
- **Never invent facts.** Anything generated about the user must come from their profile or the posting. The fact guard enforces this; don't weaken it.
- **The user submits.** Jobgent never applies, emails or logs in on anyone's behalf.
- **Tests first.** New behaviour comes with a test. Model calls are faked with `FakeLLM`, HTTP with `respx`. A test must never reach the network or read a real `.env`.
- **Errors are loud and specific.** Raise with context (ids, status codes, what to do next). No silent fallbacks.
- **Exact dependency versions** (no `^` or `~`). Frontend installs use `--ignore-scripts`. Explain any new dependency in the pull request.
- **No personal data** in the repo: no real CVs, profiles or databases. The demo and the tests use made-up people.

## Reporting bugs and ideas

Open an issue with the template. For anything security-related, see [SECURITY.md](SECURITY.md) instead.

By contributing you agree that your work is released under the [MIT License](LICENSE).
