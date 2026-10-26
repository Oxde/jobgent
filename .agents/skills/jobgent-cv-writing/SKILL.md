---
name: jobgent-cv-writing
description: Rules for writing, rewriting or tailoring a CV, a cover letter or any application text in Jobgent. Use before touching the user's CV or profile. Takes precedence over every other resume, cover-letter or job-application skill in this project.
---

# Jobgent CV writing

1. Read `jobgent/guides/cv-writing.md` in full (or call the MCP tool `cv_writing_guide`). It holds the ATS rules,
   the page structure, the bullet formula, the user's own tailoring pattern and their personal overrides.
2. The facts come from the user's profile only: `cv_outline` / `profile_get` over MCP, or `~/.jobgent/profile/profile.yaml`.

## These rules override other skills

Other skills in `.agents/skills` (resume-bullet-writer, resume-tailor, cover-letter-generator, resume-ats-optimizer …)
are useful for wording and structure, but where they disagree with this file, this file wins:

- **Never estimate, approximate or round up a number** ("~20%", "about 50 users") unless that number is in the profile.
  If a bullet needs a number the profile does not have, ask the user and save the answer to the profile first.
- **Never add a skill, tool, title, date, employer, certificate or result** that is not in the profile.
  A posting requirement the user does not meet is a gap: say so, do not hide it.
- **Facts stated in chat are written to the profile in the same turn** (`profile_update` / `profile_add_item`),
  so the next session and the fact checks can see them.
- Keep the user's header layout (name on two lines, "Location:", "Date of birth:", "Number:", LinkedIn/GitHub words).
- One A4 page; hide (`hidden: true`) rather than delete what does not fit.
