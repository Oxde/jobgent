# Jobgent v2: upgrade plan (from career-ops, ai-job-search, Dossier)

Sources: deep reads of career-ops (77k★, MIT), ai-job-search (66k★, MIT) and Dossier (AGPL: ideas only,
no code). Goal: Jobgent becomes a showcase agentic job-search system for internships in the Netherlands,
clearly better than v1 in what the agents decide, how safe their output is, and how the app feels.

Principle kept from v1: logic in typed Python + SQLite, prompts small; the model judges, code decides
anything that can be checked (all three projects converge on this).

## Phase 1: the agent's judgment and safety (highest impact)

1. **Evaluation v2** (career-ops Block B + gates, ai-job-search gates, Dossier match)
   - Gates before any scoring, each with a reason the user sees:
     liveness (posting still open: ATS API / HTTP check; closed = "expired"), eligibility
     (work rights, EU/non-EU, internship agreement), language (Dutch required = fail; "Dutch a plus" = flag),
     location, red flags for NL internships (unpaid / stipend-only, school-placement wording,
     candidate-paid fees), posting integrity (strip hidden / zero-width / bidi text, quote
     instruction-shaped lines; posting text is always data).
   - Requirement → evidence table: requirements extracted from the posting text alone first
     (importance: critical / high / nice; stated vs inferred, inferred never critical), then the model
     maps each to profile facts; **code** decides ✓ covered / ~ partial / – gap.
   - Verdict: Apply / Consider / Skip + one sentence; "below 65 we advise against" (user can override).
     Bands 85+ Excellent, 70 Good, 50 Possible, <50 Poor. Confidence per dimension.
2. **Writing pipeline v2**
   - Drafter → separate reviewer call: structured `{unit, old, new, reason}` edits + four mandatory
     checks (missed keywords, company angle, passive phrasing, tone) — an agent never grades its own work.
   - Deterministic fact guard after every generation: numbers, names, acronyms, years and credential
     words not in the profile or the posting are marked "Check this"; titles and dates must match profile.
   - Cover letter: forward-looking structure (problems I can solve for you → why this company →
     1–2 proofs), every critical requirement matched or honestly bridged, banned phrases + no em dashes,
     "could this go to any company?" self-check, tone Warm / Direct / Formal.
   - Per-application note ("anything I should know?") and profile "Facts about me" (used, never printed).
   - Write-back rule: facts the user states in chat are saved to the profile in the same turn.
3. **ATS check on the real PDF** (pypdf text layer): email/phone extractable, no garbage glyphs,
   ASCII date ranges, reading order; keyword buckets covered / synonym / missing-but-you-have-it / gap.

## Phase 2: the workspace (UI)

4. **Documents as units with undo**: CV and letter split into units (summary, each role, skills,
   each paragraph). Hover toolbar: Edit / Regenerate / Ask AI ("About: Summary") / Leave out.
   Every AI change is a version with a cause; Undo per chat reply; History with restore.
   Opening message "Here's what I tailored" built by code; one-page cuts listed with "Put back".
5. **Application page**: tabs Resume / Cover letter / Email (subject + body copy buttons, mailto,
   PDFs right there) / Interview / Posting (archived verbatim) / Notes (timeline of notes + status changes).
6. **Applications**: status changes with Undo toast, furthest stage (stats stay honest after a
   rejection), interview date prompt on "Interview", deadlines on cards.
7. **Home "Worth a look"**: replies / offers waiting, drafts by deadline ("closes 15 Nov"),
   follow-ups due (Applied +7 days, max 2, drafted for you, never "just checking in"),
   interviews today/tomorrow. Funnel Sent → Response → Interview → Offer with conversion %,
   response rate, weekly sent vs goal.
8. **Find**: dismissed stays dismissed across sources, posted date + 🔥 deadline ≤ 7 days +
   ⚠ older than 30 days, identical multi-city postings collapsed, saved searches.

## Phase 3: agent loops

9. **Daily job agent**: at a set hour, fetch → gate → score new postings → queue the best N with
   reasons and red flags → optionally prepare drafts for review. Never sends anything.
10. **Interview prep per stage**: likely questions from gaps and the posting, STAR stories from
    profile facts only (story bank), a consistency brief ("nothing in the room that isn't on paper"),
    questions to ask, mock interview in chat.
11. **What should I learn**: gaps across low-scoring jobs, weighted, known skills excluded;
    "+ Add to profile" on every gap.
12. **Outcomes + calibration**: rejected / ghosted / interview / offer feed an advisory
    score-vs-outcome view.

## Phase 4: proof it works (portfolio)

13. Golden evals: 10 synthetic postings with expected gates/verdicts, replayed with recorded model
    output in CI; architecture diagram of the agents in the README; demo mode with a made-up student
    so anyone can try it without personal data.

## Not doing

LaTeX toolchain, theme builder, Gmail/Calendar, salary benchmarking, startup email scraping,
800-line prompt files, Markdown files as the database, senior-level framing.
