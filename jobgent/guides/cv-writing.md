# Writing and tailoring a CV (Jobgent guide for agents)

Read this before you write, rewrite or tailor any CV, summary, bullet or cover letter for the user.
The user's profile (`profile.yaml`, via `cv_outline` / `profile_get`) is the only source of facts.

## The one hard rule

Never write a skill, tool, job, title, date, number, result or certificate that is not in the profile.
You may select, reorder, merge and rephrase. If a posting asks for something the user does not have,
leave it out and tell the user it is a gap. If you think the user has it but it is not in the profile,
ask them and add it to the profile first (with evidence), then use it.

## What recruiters and ATS read

An applicant tracking system turns the PDF into plain text, then a recruiter skims it for 6–10 seconds.
Write for both.

- One column for the body. Contact details may sit side by side, but never in a table or a text box
  (several ATS drop table cells or read them out of order).
- Standard section names: Summary (or no heading), Work experience, Education, Skills, Projects, Languages.
  Creative names ("My journey") make the parser miss the section.
- Real text only: no text in images, icons for contact details, skill bars or star ratings.
- Show URLs as text (`linkedin.com/in/name`, `github.com/name`), not just the word "LinkedIn":
  a printed or parsed CV loses the link.
- One date format everywhere: `Sep 2023 – Present`, `2024 – 2025`. Month + year where you know it.
- Standard fonts (Times, Georgia, Calibri, Arial, Helvetica), 10.5–12 pt body, headings slightly larger.
- A4 for Europe, one page for students and graduates. 300–400 words fills one page well; under 250
  looks thin, over 450 will not fit.
- Plain PDF export with selectable text. File name `Firstname_Lastname_CV_Company.pdf`.
- Leave out: photo, date of birth, nationality, marital status, full address. (Dutch employers do not
  need them and the EU discourages them; the city is enough.) Keep them only if the user insists.

## Keywords (ATS match)

- Take the hard skills and tools named in the posting (Jobgent stores them per job as `keywords`).
- Use the posting's exact wording when the user really has the skill: "machine learning" not "ML stuff",
  "Python" not "Py". Write the acronym and the long form once each if both are common
  ("Large Language Models (LLMs)").
- Put each matched keyword where it is proven: in a bullet or project, not only in the skills list.
- Aim for 60–80% of the posting's keywords. 100% means you stuffed words in; that reads badly to humans.
- Never add a keyword the profile cannot back. A missing keyword is a gap to mention, not to hide.

## Structure (student / internship CV)

1. **Header**: name, a short title line (e.g. "Applied Mathematics & Data Science student" or the target
   role if the user has done it), city, email, phone, LinkedIn, GitHub.
2. **Summary**: 2–3 sentences. Who you are, the 2–3 strongest proofs for *this* role, what you want
   (role + start date). No "passionate", "hard-working", "team player".
3. **Work experience**: most recent first. `Company | Role` and `City | Period`. 2–4 bullets each.
4. **Education**: degree, school, period, GPA if ≥ 7.5/10, one line of relevant courses/thesis.
   For students with little experience, education may go before work experience.
5. **Skills**: grouped by category, most relevant group first ("AI & LLMs: …", "Programming: …",
   "Data: …", "Tools: …"). 12–25 items. No proficiency bars.
6. **Projects**: 2–4, each one line: name (linked) + what it does + stack + a result if there is one.
7. **Languages**: name + level (CEFR: B2, C1 …).

## Bullets

Formula: **action verb + what you did + how (tools) + result (number)**.
- "Built automated trading bots in Python (asyncio) that processed over $1M in volume for 150+ users."
- Start with a verb in the past tense (present for the current job): built, shipped, integrated,
  automated, reduced, led, designed, analysed, trained.
- One line, at most two. 3–4 bullets for the main job, 2 for older ones.
- Numbers only if the profile has them. Never invent a percentage.
- Remove filler: "responsible for", "helped with", "various", "etc.".

## Tailoring to one posting (the user's own pattern, from 36 CVs in 2025)

Change, in this order of frequency:
1. **Summary**: always. Rewrite for the role; name the company or team if it fits naturally.
2. **Skills**: always. Regroup and reorder so the posting's areas come first; drop irrelevant groups.
3. **Title line**: usually (two thirds of the time). Match the role family ("Data Analyst",
   "AI Developer") only if the user's experience supports it; otherwise use the student title.
4. **Bullets**: when a bullet can lead with what the posting cares about. Reword, do not invent.
5. **Projects**: swap in the most relevant 2–3.
6. **Education**: rarely; only to surface a relevant course or thesis.

Keep the page full (300–400 words) and on one page. List what you changed (the "change summary")
so the user can check it in under a minute.

## Cover letter

Under 250 words, three short paragraphs: why this company/team (one specific thing from the posting),
what you bring (two concrete facts from the profile with numbers), the ask (start date, availability,
"happy to talk"). Follow the user's `voice.md`. No "I am writing to express my interest".

## Before you hand it over

- Every claim traceable to the profile? (Jobgent's verifier checks this; do it yourself too.)
- One page, A4, 300–400 words?
- Dates consistent, no typos in company names, links correct?
- Top third of the page answers "why this person for this role" on its own?
