# HireTitan: clarified requirements baseline

Status: **APPROVED by Ravi 2026-11-03** · Date: 2026-11-03 · Source: Q&A session 2026-11-03 (answers to `docs/archive/specs-v0/06-analysis-and-questions.md` themes)

This replaces the assumptions in `docs/archive/specs-v0/01`–`05` wherever they differ. It is the input for `/speckit.constitution` and the per-feature `/speckit.specify` runs. Items marked *(Claude's call)* were chosen by Claude and are open to correction. Everything else is Ravi's answer.

## 1. Product

- **Name:** HireTitan (repo `github.com/RaviprasanthR/HireTitan`). **Private now, public at first release, MIT licence** *(Claude's call; Ravi: "doesn't matter")*.
- **Who uses it: anyone.** Each person clones it and runs their own copy: **self-hosted, one user per install**. No accounts or login. Each user's resume, data and API key stay on their own machine.
- **Nothing about any specific person is built in.** Target roles, locations, pay floor, stack, company preferences and blocked cities are all **user settings** set during onboarding. (Ravi's own rules from career-ops become just *their* settings.)
- **Region:** global (any country, currency, city), with **India-friendly defaults** (INR/LPA pay format, Indian cities, Indian sources supported out of the box).
- **Priority:** **showcase first**: production-grade (tests, evals, clean architecture, good docs), even if it takes longer.
- **Never** sends messages, emails or applications. The user sends everything themselves.

## 2. Install and first run

- **One command:** `docker compose up` (only Docker needed). Native `uv`/`npm` run documented for contributors.
- **First-run setup wizard** in the web app: pick the LLM provider → paste the API key (verified with a test call) → set the monthly budget → upload a resume → confirm the extracted profile → set job preferences → review the proposed search queries. Keys are stored locally; `.env` also works for advanced users.
- Works on Windows, macOS and Linux.
- The repo ships **synthetic demo data** (a fake resume and jobs) and never contains anyone's real data.

## 3. Core flow

1. **Profile.** Upload a resume (PDF/DOCX). AI extracts the details (experience, skills, years, education). The user also fills in a **job profile** (preferences). Everything is **editable by hand**. Optional import from an existing career-ops setup (`cv.md`, `profile.yml`, `voice-dna.md`) for users who have one.
   - The **confirmed, edited profile is the source of truth** for all AI work. The AI may only use facts in it, never invent.
   - Uploading a newer resume: AI extracts it, the app **shows a diff against the current profile**, and the user accepts changes. The old file is kept as a version.
2. **Preferences** captured: roles, seniority, stack, locations and work mode, pay and availability (currency-aware), company preferences. **Roles, stack and location weigh most.** They are *weighted* in scoring; nothing is hard-filtered by them.
3. **Search.** AI **proposes search queries** per source from the profile. The user **approves or edits** them, and they're saved. Runs happen **only on manual trigger** ("search now"), never scheduled.
   - **Rules first, AI optional** (Ravi, 2026-11-03). A search run uses **no AI by default**: fetch → dedup → **rule filter** → sort. Rules come from the user's preferences: title keywords (include/exclude), location and work mode, posting age, seniority words, years of experience parsed from the description, and stack keywords matched against the description (match score). Each job lands in **match / maybe / hidden**, always with the rule that decided it ("hidden: location Pune is in your blocked list"). Hidden jobs are kept and can be restored. Only the user's explicit exclusions (blocked cities, excluded title words) hide jobs; weighted preferences only rank them.
   - **Optional "Check with AI"**: on the "maybe" jobs or jobs the user picks, the AI gives relevant / not relevant with a visible reason, after showing the cost. Undoable.
   - Structured sources need no AI. Careers pages are read from embedded schema.org `JobPosting` data or generic parsing first; AI page extraction is only a fallback, and so is AI parsing of job-alert emails (per-sender parsers first).
   - Results are one **deduplicated list, newest first**.
   - When the profile changes, the app **proposes** updated queries and offers to re-score open jobs. Nothing changes until the user approves.
4. **Scoring is optional** because it costs money: an explicit action on jobs the user picks. Output: score, matched skills, gaps, verdict.
5. **Act on a job** (first release): **application tracking**, **outreach drafts**, **tailored resume**.

## 4. Sources

- **career-ops is a required dependency**: its portal scanner is a core job source.
  - *(Claude's interpretation)* HireTitan **bundles career-ops at a pinned version in its Docker image** and **manages its own career-ops data folder** inside HireTitan's data volume. It writes the scanner config from the user's approved queries and preferences, so users never configure career-ops by hand. **Before relying on this, check that career-ops' licence allows redistribution.**
  - Users with an existing career-ops setup can import from it (read-only).
- **Manual paste** (URL + JD text) is always available.
- **Built-in curated company list** (Ravi's answer: "hardcoded, our internal source, updated later"): HireTitan ships a versioned data file of companies + careers URLs, seeded from Ravi's Google Sheet (names + careers URLs) and updated through project releases. The app resolves each careers URL to its ATS (Greenhouse, Lever, Ashby, …) and scans it through the bundled career-ops scanner using **public job-board APIs**. Users can add their own companies and hide built-in ones locally *(Claude's call)*. No Google Sheets integration in the app.
  - **One global list** (not per region), currently 62 Chennai companies from Ravi's sheet. Only **name, city, website, careers URL and the resolved board** are shipped; the sheet's HR contacts and notes are **dropped** (third-party personal data).
  - Recon 2026-11-03 (career-ops `discover-ats.mjs`, preview only): **14/62 resolved** to a public board with live jobs (Greenhouse, SmartRecruiters, Recruitee, Rippling, BambooHR, Workday); 2 of these are doubtful matches; ~27 boards were found with 0 jobs (wrong or empty); ~20 had no supported ATS.
  - So: the project **resolves each built-in company once and ships the result** (vendor + board id) in the list file, **verified by a maintainer**; user-added companies get auto-discovery plus a **user confirmation** of the match *(Claude's call)*.
  - **Stored in a PostgreSQL `companies` table** (Ravi, 2026-11-03: "store the list of companies … in a psql table so that i can update it later"). The repo's seed file (Ravi's sheet, company columns only) is loaded into the table on install, and the table is what the app uses from then on. Companies can be **added, edited, hidden and deleted in the app**. Shipped list updates in later releases are merged in **without overwriting the user's edits**; each row records its origin (`built_in` / `user`) and whether the user changed it. **CSV import/export** on the companies screen, so the list can be maintained in a spreadsheet and loaded back *(Claude's call)*.
  - **Companies without a supported board:** HireTitan **fetches the company's own public careers page** (honours robots.txt, slow rate, caching) and **AI-extracts the job list**; if that fails (JS-only page, blocked), the company goes to a **"check manually" list** with its careers link and a "last checked" date.
- **career-ops' free boards** (RemoteOK, Remotive, Himalayas, We Work Remotely, Arbeitnow, HN "Who's hiring") are **optional sources** the user can enable.
- **Job-alert emails** in the user's own Gmail (**read-only**): Naukri, LinkedIn, Indeed, Cutshort, Instahyre, foundit. This is the only route to those platforms: none offers a public job-search API to job seekers (checked 2026-11-03). Full JDs from those sites are pasted by the user, never fetched.
- **Aggregator APIs with the user's own free key**, each optional: Adzuna, Jooble, Careerjet. Each must be checked in the plan phase for India coverage, rate limits, attribution and storage terms.
- **Rejected:** scraping or internal endpoints of Naukri/LinkedIn/Indeed/Cutshort (JobSpy, Apify actors, "free Naukri API" repos), paid scraped-data APIs (SerpApi/Google Jobs, JSearch), and a browser "save this job" button. **Only free, official or clearly permitted sources.**
- An application can exist **without a posting** (recruiter inbound: company + role + recruiter + channel; JD added later).

## 5. Application tracking

- Statuses as in the old design, plus **`no_response`**: **auto-marked after N days** with no update (default N = 21 *(Claude's call)*, user-configurable); the user can reopen it.
- Fields: **channel** (company site, job board, LinkedIn, referral, recruiter inbound, email, other), **referral details** (who, asked when, referred when), **recruiter/contacts** (name, phone/email, call notes), **offer details** (base/fixed, variable, total, currency, joining date, deadline).
- **Follow-up reminders:** default +7 and +14 days after applying, and +3 business days after each interview round with no update (all configurable).
- Records which resume version was sent (base or tailored).

## 6. Outreach drafts

- Types (all in the first release): **referral request**, **LinkedIn connection note** (character limit set by the user's account type: 200 free / 300 Premium), **HR/recruiter email**, **follow-up message**.
- **Writing style:** a user style guide built from writing samples the user provides, or imported from career-ops `voice-dna.md`; plain professional by default *(Claude's call, generalized from Ravi's answer)*.
- Grounded in the profile. The user approves or edits, then copies and sends it themselves.

## 7. Tailored resume per job

- **Generated by the app.** The AI may **reorder/select bullets, rephrase bullets (same facts and numbers), rewrite the summary, reorder/select skills.** It never adds facts.
- Review: a **full-document preview with free editing** before saving.
- Output: **ATS-friendly PDF + DOCX**, stored as a resume version and linked to the job/application.
- **One template only** (Ravi, 2026-11-03: "we dont have to support different resume templates"). No template picker.
- **Optional content suggestions** (Ravi: "in the same template we have to suggest better content so that it gets shortlisted … optional"). On a button press, the AI reviews the content (the base profile, or a tailored resume for a specific job) and suggests improvements to raise shortlisting chances: stronger wording, clearer impact, missing keywords from the JD that the user actually has, weak or vague bullets, ordering. Each suggestion is shown with its reason and can be **accepted, edited or rejected** individually. Suggestions never invent facts. Where an improvement needs a fact the profile doesn't have (e.g. "add a number for this result"), it is a **question to the user**. Only the user's answer, once confirmed, becomes a profile fact. Not run automatically; the cost estimate is shown first *(Claude's call)*.

## 8. Interviews (release 2)

- Capture: **paste notes; AI splits them into Q&A**; the user confirms and edits.
- Coach: **AI review of each answer** (scores, what was missing, improved outline), **on button press**, and **weak-topic analysis** across rounds (topics, trend, recurring questions).
- Not now: prep plans, mock practice.

## 9. AI and cost

- AI is required for profile extraction, query proposal, drafts, tailored resumes, transcript split and answer review. **Optional for job finding** (the AI relevance check, AI careers-page extraction fallback, AI alert-parsing fallback), **scoring** and **resume content suggestions**.
- **Bring your own key, any provider where possible.** Guaranteed: **OpenAI, Anthropic, Google Gemini**. Plus **any OpenAI-compatible endpoint** (Ollama/local, OpenRouter, Groq, LM Studio…) *(Claude's call for how "any" is met)*. The user picks the provider and model per task (with sensible defaults per provider).
- **Build order (Ravi, 2026-11-03): OpenAI first.** The OpenAI adapter is built in feature 001 and used for development with Ravi's key. Anthropic, Gemini and OpenAI-compatible adapters follow before the first public release. Own thin adapters behind one port, no LiteLLM.
- Features must degrade gracefully when the chosen model lacks a capability (e.g. no native structured output → JSON mode + validation + repair).
- Orchestration: **LangGraph + direct provider SDK calls** inside nodes (human approval steps, resumable state). *(Plan-phase research: a multi-provider library such as LiteLLM vs our own thin adapters.)*
- **Budget:** a user-set monthly cap (default **$25** *(Claude's call)*), a hard stop, and estimated cost shown before batch AI actions. Cost tables per provider/model must be updatable.
- Kept from the old design: versioned prompts, schema + rule validation of every output, fallbacks, untrusted-text (prompt-injection) defenses, LLM call logging. The eval gate applies from prompt v2 onward *(Claude's call)*. Evals must run against any configured provider.

## 10. UI

- **Web dashboard first** (React, localhost). **Local only:** no hosted version, no login; anyone who wants it clones the repo and runs it on their own machine (Ravi, 2026-11-03). An MCP server / Claude Code commands come later over the same backend.

## 11. Engineering process

- **GitHub Spec Kit** SDD: **fresh specs per feature**, with old docs used as input; `docs/specs/01–06` archived to `docs/archive/specs-v0/`.
- Constitution: **ports only at real boundaries** (LLM provider, job sources, file storage, clock). FastAPI and SQLAlchemy are used directly. TDD is non-negotiable. Real Postgres in tests, fakes only for LLM/external CLIs *(Claude's call)*. **No personal data in the repo; all fixtures synthetic.**
- Development runtime (Ravi): Postgres in Docker, api/worker/web native (uv, npm). End users: `docker compose up`.
- Implementation: **task by task in the main session**, TDD, one commit per task.
- Tool roles *(Claude's call, from 06 §A.6)*: Spec Kit owns spec/plan/tasks; superpowers brainstorming for discovery and TDD discipline in implementation; ecc reviewers per user story.
- Open-source hygiene for the first public release: README with screenshots, setup guide, CONTRIBUTING, licence, dependency licence check.

## 12. Proposed Spec Kit features (Claude's call)

| # | Feature | Release |
|---|---|---|
| 001 | `setup-and-profile`: install, first-run wizard (provider + key + budget), resume upload + AI extraction, job profile, manual edit, resume diff on re-upload, career-ops import | R1 |
| 002 | `job-search`: AI-proposed queries + approval, manual runs, built-in company list (Postgres table, editable, CSV import/export) → career-ops (bundled) + manual paste, dedup, rule filter (match / maybe / hidden with reasons), newest-first list, optional AI relevance check, optional scoring | R1 |
| 002b | `more-sources`: Gmail job-alert parsing, Adzuna/Jooble/Careerjet adapters | R1 or R1.1 |
| 003 | `applications`: tracking, channel/referral/recruiter/offer fields, no-response, follow-up reminders, inbound opportunities | R1 |
| 004 | `outreach`: four draft types, style guide, approval | R1 |
| 005 | `tailored-resume`: AI tailoring, preview/edit, one ATS-friendly template, PDF + DOCX, versions, optional content suggestions | R1 |
| 006 | `interviews`: paste-and-split, answer review, weak-topic analysis | R2 |
| 007 | `mcp-access`: Claude Code / MCP over the backend | later |

## 13. Still open

1. ~~Which sources~~ decided (§4). Sheet received 2026-11-03 (62 companies, seeds the built-in list). Remaining: fill in the 10 missing careers URLs; dedup across sources (same job via a board API and a Naukri alert) needs a fuzzy company + title + city match with user confirmation; verify Adzuna/Jooble/Careerjet terms and India coverage in the plan phase; Gmail access for self-hosters needs each user to create their own Google OAuth client (setup-guide step).
2. ~~career-ops licence~~ **Checked: MIT** (v1.38.0), so bundling is allowed with its copyright notice kept. Its `package.json` references Playwright; in the plan phase, check whether the scanner needs a browser (affects image size).
3. Default models per provider (decide in the plan phase, after measuring cost and quality).
4. Offer comparison view: just the fields, or a comparison screen?
5. Default N = 21 days for `no_response`.
6. Pay handling when a posting doesn't state pay, and fixed vs total comp in preferences.
7. ✅ Resolved 2026-11-03: Spec Kit 1.2.6 pinned; `master` is the main branch, one branch per feature, merged by GitHub PR; commit format `[<branch> - <feature>] - If applied this commit will <change>` (constitution v1.1.0).
