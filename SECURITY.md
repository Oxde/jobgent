# Security

Jobgent runs on your own machine and handles your CV, your API keys and text from job postings written by strangers. Those three things shape its security.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private vulnerability reporting: **Security → Report a vulnerability** on this repository. Expect a first answer within a week.

## What Jobgent does to protect you

- **Posting text is data, not instructions.** Postings are cleaned of invisible and direction-changing characters, fenced before any prompt sees them, and checked for injection attempts. A posting that tries to instruct the model is flagged in its evaluation.
- **Link fetching is restricted.** Adding a job by URL and the liveness check only fetch public `http(s)` addresses, and every redirect is re-checked, so a link can't make Jobgent reach your local network.
- **Secrets stay local.** Keys are read from the environment, `.env` (git-ignored) or `~/.config/secrets/env`. They are never logged, never returned by the API or MCP tools, and never written to your data folder.
- **Local by default.** The web app and the HTTP MCP server bind to `127.0.0.1`. There is no authentication, so don't expose them to a network you don't trust.
- **Your data stays in `JOBGENT_HOME`** (`~/.jobgent` by default), never in the repository.
