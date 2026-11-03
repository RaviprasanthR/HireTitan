# 06 — Requirements analysis, Spec Kit migration and detailed questions

Status: **OPEN — Ravi to answer** · Created: 2026-11-03 · Reviewed: `CONTEXT.md`, `01`–`05` specs

How to use: answer inline on the **Answer:** lines (or write "accept rec"). Items tagged **[C]** are needed before writing the Spec Kit constitution, and **[F1]** before the first feature spec. Everything else can wait for its feature.

---

## Part A — Moving to GitHub Spec Kit: what changes

### A.1 What Spec Kit expects (checked 2026-11-03 against github/spec-kit)

- Install: `uv tool install specify-cli`, then `specify init . --integration <claude key>` in the repo. It creates `.specify/` (templates, scripts, `memory/constitution.md`) and the slash commands. Not installed on this machine yet.
- Flow: `constitution` → `specify` → `clarify` → `plan` → `tasks` → `analyze` → `implement` (newer versions add `converge`; `checklist` is optional). Command naming varies by version (`/speckit.specify` vs `/speckit-specify`). The version we pin decides it.
- **One folder per feature**, `specs/NNN-feature-name/`, each with `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `tasks.md` and `checklists/`. `specify` also creates a git branch per feature.
- **`spec.md` is tech-agnostic.** It covers what and why only: user stories with priorities (P1/P2/P3), Given/When/Then acceptance scenarios, edge cases, functional requirements `FR-001…`, key entities, measurable success criteria `SC-001…`, and `[NEEDS CLARIFICATION]` markers. All technology goes in `plan.md`.
- `tasks.md` is organized **by user story** (each story can be shipped and tested on its own), with `[P]` for tasks that can run in parallel.

### A.2 Gaps between our docs and Spec Kit

| # | Gap | Impact |
|---|---|---|
| G1 | Our specs are one monolith (`01`–`05`) covering 10 capability areas. Spec Kit wants one folder per feature. | We need to split into features (proposal in A.3). |
| G2 | `01-requirements.md` mixes in technology: career-ops script names, SHA-256, `keyword-match.mjs`, LangGraph-shaped "pause the workflow", SSE streaming. | Requirements move into `spec.md` without the tech. The tech moves into `plan.md` / `research.md`. |
| G3 | Requirement format is EARS with `R1.4`-style IDs. Spec Kit uses user stories + Given/When/Then + `FR-###`. Our tests are named after `R` IDs. | We need to decide the ID scheme (Q-SK3). |
| G4 | There are no measurable **success criteria**. N4/N5 are technical targets, not user outcomes. | We need your outcome goals (Q-G2). |
| G5 | `02-design.md` ≈ `plan.md` + `data-model.md` + `contracts/` + `research.md` (ADRs) for *all* features at once. | Cut it up per feature. Cross-cutting parts (architecture, LLM governance, queue) go in the constitution or the first feature that needs them. |
| G6 | `05-open-decisions.md` ≈ `[NEEDS CLARIFICATION]` + `/speckit.clarify` sessions. | Answered decisions become clarifications recorded in each `spec.md`. Tech decisions go to `research.md`. |
| G7 | `04-tasks.md` is ordered by technical layer (domain → persistence → adapters → LLM → API → UI). Spec Kit orders by user story (a vertical slice per story). | This is the biggest change, and a good one. It's the thin-slice approach I suggested earlier. |
| G8 | **The Spec Kit default constitution conflicts with our design** (see A.4). | You need to rule on each article. |

### A.3 Proposed feature breakdown (for `specs/NNN-*`)

| # | Feature | Covers (old IDs) | Priority (my guess) |
|---|---|---|---|
| 001 | `job-intake`: one deduplicated job list from career-ops, sheet and manual entry | R1.1–R1.8 | P1 |
| 002 | `fit-triage`: rules prefilter, AI extract + score, review queue | R2, R7 (first use), R8 | P1 |
| 003 | `application-tracker`: board, status history, follow-up schedule, resume versions | R5, R9, R6.3/6.5/6.8/6.9 | P1 |
| 004 | `outreach-drafts`: LinkedIn/HR/follow-up drafts, approval, streaming | R4, R5.4 | P2 |
| 005 | `interview-log`: rounds, Q&A capture, paste-and-split, career-ops export/import | R10.1–R10.4, R10.9–10 | P2 |
| 006 | `interview-coach`: answer review, weakness analysis, recurring questions, prep plan | R10.5–R10.8, R6.10 | P2 |
| 007 | `contact-discovery`: web-search contact suggestions | R3 | P3 |
| 008 | `email-alerts`: Gmail job-alert ingestion | R1.9 | P3 |
| 009 | `insights`: funnel, response rate, cost | R6.7 | P3 |

**Answer (order, merge or split anything):** ______

### A.4 Constitution: Spec Kit defaults vs our current design [C]

| Default article | Our design today | Conflict? | My recommendation |
|---|---|---|---|
| I. Library-first | Hexagonal app with domain/application/adapters | Partly | Replace it with "domain core is a pure library with no framework imports" (our N10). |
| II. CLI interface for every library | No CLI except `make eval` | Yes | Drop it, or keep it small: an admin CLI (`job-agent ingest`, `eval`, `activate-prompt`) helps testing and demos. |
| III. Test-first (non-negotiable) | TDD already | No | Keep, and add "tests named after requirement IDs". |
| VII. Simplicity (≤ 3 projects) | api, worker, web + postgres | Borderline | api+worker as one Python project, web as the second: OK. |
| VIII. Anti-abstraction (use framework features directly, no wrappers) | Ports for everything, decorators around the LLM, `LlmTask` template method, Repository + UoW, Specification pattern | **Yes, strongly** | Choose: (a) keep the patterns and amend VIII with written justifications, or (b) slim down: ports only at real boundaries (LLM, career-ops, file storage, clock), SQLAlchemy used directly, no Specification pattern. **I lean (b)**: less code, and still shows good design. |
| IX. Integration-first testing (real DB over mocks) | Heavy use of in-memory fakes + contract suite + testcontainers | Partly | Use real Postgres (testcontainers) for repositories and the queue, and fakes only for the LLM and external CLIs. |

Principles we'd add as project articles: **No outbound actions** (N1), **cv.md is the only source of candidate facts**, **untrusted text is data** (R7.3), **every LLM output is schema- and rule-validated with a fallback** (R7.2/R7.5), **prompts are versioned and eval-gated** (R7.1/R7.7), **career-ops is read-only except session exports** (R8.1), **privacy: personal data stays local** (N7).

**Answer (per article):** ______

### A.5 Spec Kit questions

- **Q-SK1 [C]** Should we migrate the existing `docs/specs/01–05` into Spec Kit's layout (I'd convert them, keep the old files in `docs/archive/` for history), or start fresh with `/speckit.specify` per feature and use the old docs only as input? Rec: convert, because a lot of good thinking is already in them. **Answer:** ______
- **Q-SK2 [C]** Spec Kit creates a **git branch per feature** (`001-job-intake`). Do you want that flow, with a PR per feature merged into `main`? Note: the repo is currently on `master` with no commits, while `main` is listed as the main branch. Should I rename to `main` before the first commit? **Answer:** ______
- **Q-SK3 [C]** Requirement IDs: use Spec Kit's per-feature `FR-001` (tests named `test_001_fr003_…`), or keep our global `R1.4` IDs inside the Spec Kit templates? Rec: Spec Kit's IDs with a feature prefix (`F001-FR-003`), and an old→new mapping table in each spec. **Answer:** ______
- **Q-SK4** Acceptance criteria format: Spec Kit's Given/When/Then, or keep EARS? Rec: Given/When/Then for user stories (they map 1:1 to tests), EARS allowed in FR lines. **Answer:** ______
- **Q-SK5** Which Spec Kit version should we pin? Rec: latest stable at install, recorded in `research.md`. Do you also want the community extensions (e.g. bug/assessment workflows)? **Answer:** ______
- **Q-SK6** Where do cross-cutting technical decisions (hexagonal layout, Postgres queue, LLM governance) live: the constitution, or a "000-foundation" plan? Rec: principles go in the constitution, concrete tech goes in feature 001's/002's `plan.md` and is referenced from later features. **Answer:** ______
- **Q-SK7** Should `tasks.md` keep our TDD rule explicitly (each story's tasks start with failing tests), and should we run `/speckit.analyze` as a hard gate before every `/speckit.implement`? Rec: yes to both. **Answer:** ______

### A.6 How ecc, superpowers and Spec Kit fit together (they overlap)

| Phase | Spec Kit | superpowers | ecc | Proposal |
|---|---|---|---|---|
| Discovery / intent | `specify`, `clarify` | `brainstorming` | `plan-prd`, `prp-prd`, `intent-driven-development` | **Spec Kit owns the artifact.** Use `superpowers:brainstorming` for the conversation before `specify` (like this one). Skip the ecc PRD commands, which would produce duplicate documents. |
| Planning | `plan`, `tasks`, `analyze` | `writing-plans` | `plan`, `prp-plan`, `architect`, `planner` agents | **Spec Kit owns it.** Use the ecc `architect` / `database-reviewer` agents to review `plan.md` and `data-model.md`. Don't use `superpowers:writing-plans` (it would write a second plan into `docs/superpowers/`). |
| Implementation | `implement` | `test-driven-development`, `executing-plans`, `subagent-driven-development`, `using-git-worktrees` | `tdd-guide`, `tdd-workflow`, `orch-add-feature` | `/speckit.implement` drives the task list; `superpowers:test-driven-development` enforces red→green→refactor per task. Do we want subagents per task (faster, costlier, less visible to you) or one task at a time in the main session? |
| Review | `analyze`, `converge`, `checklist` | `requesting-code-review`, `verification-before-completion` | `python-reviewer`, `fastapi-reviewer`, `react-reviewer`, `security-reviewer`, `database-reviewer`, `code-review` | After each user story: ecc reviewers plus `verification-before-completion` before marking it done. |
| Commit / PR | (branch per feature) | `finishing-a-development-branch` | `prp-commit`, `pr`, `commit-reviewer` | One commit per task (your rule), one PR per feature. |

- **Q-T1 [C]** Accept this division of tools? **Answer:** ______
- **Q-T2** Execution style: (a) I implement task by task in the main session and you watch, (b) subagents per task with review checkpoints, or (c) mixed: subagents for routine tasks, main session for LLM/agent parts. **Answer:** ______
- **Q-T3** How strict should the review gate be? Should every task pass an ecc reviewer, or only every user story / feature? **Answer:** ______
- **Q-T4** The ecc **GateGuard** hook blocks the first Bash call / file write per session until I state facts. Keep it as is, or exempt `docs/**` and routine read-only commands? **Answer:** ______

---

## Part B — Product and goals (the "why", feeds every `spec.md`)

- **Q-G1 [C]** What matters more if they conflict: **(a)** a tool that speeds up *this* job search soon, or **(b)** a showcase project for interviews? This drives scope, ordering and how much "production" ceremony we keep. **Answer:** ______
- **Q-G2 [F1]** What would success look like after 4–6 weeks of use? I need measurable outcomes for `SC-###`, for example: "triage all new jobs in ≤ 15 min/day", "no job I applied to lacks a record of the resume used", "every application gets a follow-up on time", "N applications/week". Your numbers? **Answer:** ______
- **Q-G3** Is job-agent the "in-progress AI project (LangChain, LangGraph, HITL, streaming)" that goes on your CV? If yes, which of those must be visibly showcased in the first release? **Answer:** ______
- **Q-G4** What would make this a failure even if it technically works? (For me: a draft with an invented claim, a score you can't trust, or more time spent maintaining the tool than it saves.) **Answer:** ______
- **Q-G5** Walk me through your current week of job searching: where do you find jobs, how many do you look at, how do you apply, what do you track today (sheet? nothing?), and where does it hurt most? **Answer:** ______
- **Q-G6** Target date for "I'm using it daily"? And hours per week you can spend on building versus searching? **Answer:** ______
- **Q-G7** Will anyone else use it (friends job hunting)? If yes, single-user assumptions (no auth, one cv.md) need revisiting. **Answer:** ______

## Part C — Detailed analysis per area: gaps, contradictions, questions

### C1. Job intake (R1)

Findings:
- **Dedup by URL only (R1.4).** The same opening often appears on Naukri, LinkedIn and the company site with different URLs. career-ops already has a `fingerprint` column (company + title + location). URL-only dedup will show duplicates.
- R1.1 filters with "first_seen ≥ last successful run date". That's date granularity, so two scans on one day can miss or repeat rows.
- "Closed" job status (design §3.2) has no detection mechanism: there's no liveness check and no Playwright.
- The Google Sheet (R1.2) is undefined. We don't know what's in it or whether it exists yet.
- Recruiter-initiated opportunities (a Naukri recruiter calls or messages) have no URL and no posting. There's no way to record them.

Questions:
- **Q1.1 [F1]** Dedup: URL only, or also a fuzzy "same company + similar title + same city" match that asks you to confirm a merge? **Answer:** ______
- **Q1.2 [F1]** Is the Google Sheet real today? What's in it (columns, rough row count), and is it a list of target companies, openings, or both? If it doesn't exist yet, drop R1.2 from v1? **Answer:** ______
- **Q1.3 [F1]** Recruiter inbound: should you be able to create an "opportunity" with just company + role + recruiter name + channel (no URL)? **Answer:** ______
- **Q1.4** When a posting disappears from career-ops scans or the URL 404s, should the job auto-close, be flagged, or be left alone? **Answer:** ______
- **Q1.5** Should jobs older than N days without action be auto-archived from the review queue? N = ? **Answer:** ______
- **Q1.6** Manual entry: is pasting a URL + JD the main path for Naukri/LinkedIn jobs? Would a browser bookmarklet ("save this job") be worth it later? **Answer:** ______
- **Q1.7** Is "tracked companies" (company without an opening) a real need? What would you do with them: watch their careers page, add them to the career-ops scanner? **Answer:** ______

### C2. Fit triage (R2, R8)

Findings:
- **Duplicate scoring with career-ops.** career-ops' `/career-ops` evaluation already scores job descriptions (with your `_profile.md` rules). Two scorers can disagree.
- **Comp is rarely stated in Indian JDs**, but the conditional-city rule depends on the pay floor (R2.5). What happens when comp is unknown is undefined (scoring sets `compensation: 3.0 when not stated`, but the location rule needs it too).
- "Good company" (conditional-city rule) and "too good to miss" (low-priority city) are subjective with no definition, so the model will guess.
- CTC vs fixed: the floor is on **fixed** pay, but postings usually quote CTC including variable pay and ESOPs.
- **CV fact IDs** (`exp.punch.1`) are positional. Editing `cv.md` shifts the IDs, and existing drafts/reviews then cite the wrong facts.
- **R7.7 bootstrapping contradiction:** a prompt can't become active until it passes an eval set, and the eval sets need labels you haven't made, so on day one nothing could run.
- The review queue "pauses the workflow" (R2.6) with no expiry. Paused threads can pile up.

Questions:
- **Q2.1 [F1]** Our scorer vs career-ops evaluation: (a) ours is primary and career-ops is only the scanner, (b) import career-ops evaluation reports and don't score ourselves, or (c) both, shown side by side? **Answer:** ______
- **Q2.2 [F1]** When comp isn't stated: should a conditional-city job pass as "unknown, check later", or be penalized? **Answer:** ______
- **Q2.3** What makes a company "good" for you (funding stage, brand, product vs services, size, engineering culture, AI work)? Can you name 5 examples you'd call good and 3 you wouldn't? **Answer:** ______
- **Q2.4** Is the pay floor on fixed pay or CTC? If a posting only gives CTC, what fixed share should we assume? **Answer:** ______
- **Q2.5** What score threshold means "show me" versus "hide"? Should low scorers (< 3.0) be hidden, or shown in a collapsed section? **Answer:** ______
- **Q2.6** Does an exceptional role in a blocked city ever deserve a look? Should blocked mean hidden, or ranked last? **Answer:** ______
- **Q2.7** Seniority: should "Senior" titles asking 5+ years be in range? Lead/staff titles out? (The spec says staff/8+ fits poorly.) **Answer:** ______
- **Q2.8 [F1]** Eval bootstrapping: v1 prompts start active without an eval gate, and the gate applies from v2 onward once labels exist? Rec: yes. **Answer:** ______
- **Q2.9** How many jobs per day/week do you expect to triage? (This drives cost, UI design and whether auto-scoring every job is worth it.) **Answer:** ______
- **Q2.10** Should the review queue show *why* a job was filtered out, with a "rescue" button for false rejections? **Answer:** ______

### C3. Applications and resume versions (R5, R9)

Findings:
- The state machine has **no `ghosted` / no-response state**. In practice most applications end silently.
- `applications.job_id` is `NOT NULL UNIQUE`: you can't re-apply to the same company role later, and you can't have an application without a job (recruiter inbound).
- Follow-ups are hard-coded to 2 in the DB (`seq IN (1,2)`) while `FOLLOWUP_DAYS` is configurable, which is a contradiction. They also only exist while the status is `applied`; there's nothing after an interview ("any update after round 2?").
- Similarly, the LinkedIn note limit is configurable (200/300), but the DB CHECK hard-codes 300.
- The relationship between **shortlisting a job and creating an application** is undefined. Is it automatic?
- Referral applications have extra steps (ask → referred → applied) that aren't modeled.
- Interview offers often come with notice, joining date and negotiation. `offer → accepted` is a single step.

Questions:
- **Q3.1 [F1]** Add `ghosted` (auto-suggested after N days with no response) or a `no_response` terminal state? N = ? **Answer:** ______
- **Q3.2** Does shortlisting create an application in `preparing` automatically, or do you create it when you actually apply? **Answer:** ______
- **Q3.3** Referrals: should we track "referral requested → referral given" as its own steps (who referred you)? **Answer:** ______
- **Q3.4** Follow-ups: how many, at which days, and also after interview rounds? Business days or calendar days? **Answer:** ______
- **Q3.5** Offers: track offer details (CTC, fixed, joining date, deadline) for comparing offers? **Answer:** ______
- **Q3.6** Should you be able to apply again to the same company later (new application, same company)? **Answer:** ______
- **Q3.7** Resume files: which existing local PDFs should be imported, which one is the current base, and do you edit resumes by hand or only via `/career-ops pdf`? (= D2) **Answer:** ______
- **Q3.8** For "which resume works better" (R9.5) to mean anything, you'd need ~10+ applications per version. Is that realistic, or is the main value just "what did I send to X"? **Answer:** ______
- **Q3.9** Should applications sync to the career-ops tracker (D12)? **Answer:** ______

### C4. Outreach drafts (R4)

Findings:
- R4.1 auto-drafts on every shortlist, for every contact. That's cost and noise if you shortlist many jobs but only reach out on a few.
- R4.3 promises that "every factual claim is traceable", but validation can only check numbers, skills and cited fact IDs. Free-text claims ("led a team") can't be fully verified.
- The tone/voice reference is unclear: there's a `voice-dna.md` in your career-ops data folder that the spec doesn't mention.

Questions:
- **Q4.1** Draft automatically on shortlist, or only when you click "draft outreach"? Rec: on click. **Answer:** ______
- **Q4.2** Which outreach do you actually send today: LinkedIn connection notes, InMail, cold emails to HR, WhatsApp to referrers? Which matters most? **Answer:** ______
- **Q4.3** Should drafts use `voice-dna.md` from career-ops as your writing style? **Answer:** ______
- **Q4.4** Accept rewording R4.3 to the verifiable rule (numbers, skills and cited facts checked; everything else via your approval)? **Answer:** ______
- **Q4.5** LinkedIn free or Premium (200 vs 300 chars)? (= D13) **Answer:** ______
- **Q4.6** Should we keep a library of your past sent messages to learn your style over time? **Answer:** ______

### C5. Interview log and coach (R10)

Findings:
- R10.5 reviews on **every save**, so editing an answer three times means three paid reviews. Needs debouncing or an explicit "review" button.
- Self-rating, review scores and the weakness formula (design §3.3) produce meaningful numbers only after many questions. Early on, the "analysis" is noise.
- Storing interviewer names is third-party personal data (India's DPDP Act). It's local-only, which is fine, but deletion matters (R10.10).
- career-ops already has `interview/debrief`, `plan` and `practice`. Is our coach a replacement or a dashboard on top of the same data?
- **Public repo vs real data:** tasks T1.8 and T11.3 use "the real `cv.md`" and "my real resume PDF" as test fixtures. That contradicts a public repo (N7, D7).

Questions:
- **Q5.1** Do you have interviews coming up now? (That decides whether interview features move up in priority.) **Answer:** ______
- **Q5.2** How do you capture interviews: notes during the call, notes from memory after, a recording transcript? (= D15) **Answer:** ______
- **Q5.3** AI review on save, or only when you press "review"? Rec: on button press, plus a "review all" per round. **Answer:** ______
- **Q5.4** Our coach vs career-ops interview modes: replace them, complement them (dashboard + analytics here, practice there), or just sync data? **Answer:** ______
- **Q5.5** Should coding rounds store code (your solution, the problem link), or just Q&A text? **Answer:** ______
- **Q5.6** Accept the seed topic taxonomy (D16), or edit it? **Answer:** ______
- **Q5.7 [C]** Test fixtures: use a **synthetic** CV and resume in the repo (with your real ones only in a gitignored local fixture folder for opt-in tests)? Rec: yes if the repo is public. **Answer:** ______

### C6. Contacts (R3)

- **Q6.1** Keep AI contact discovery in v1, or defer it (manual contacts only)? Rec: defer. It's the least accurate, most privacy-sensitive and most expensive feature. **Answer:** ______
- **Q6.2** How do you find referrers today: alumni, ex-colleagues, LinkedIn search? Would a "people I know at company X" list (manual) be more useful than web search? **Answer:** ______

### C7. LLM, cost and governance (R7)

Findings:
- The design's own estimate (~$0.051/job) is right at the N5 cap ($0.05) before thinking tokens, which are billed as output. Expect to exceed it with Opus everywhere.
- The daily budget cap blocks everything equally. A user-triggered answer review should probably outrank background scoring.
- Spec Kit `plan.md` will need the exact SDK features we rely on (structured output via `messages.parse`, refusal fallback beta, web search tool version). I'll verify these against the current Claude API docs at plan time, not from memory.

Questions:
- **Q7.1 [F1]** Do you have an Anthropic API key, and what monthly budget is OK? (= D9) **Answer:** ______
- **Q7.2** Model policy: Opus 5.5 everywhere at first and then measure, or cheaper models for extraction/splitting from day one (subject to evals)? (= D10) **Answer:** ______
- **Q7.3** When the daily cap is hit: pause background work but still allow actions you trigger (up to a hard ceiling)? **Answer:** ______
- **Q7.4** Is N5 (≤ $0.05 per job) a real constraint, or just a guess we can relax? **Answer:** ______
- **Q7.5** LLM tracing: is LangSmith (hosted) acceptable for your data, or must everything stay local? (= D27) **Answer:** ______

### C8. Platform, runtime and ops (N-requirements)

Findings:
- **career-ops in Docker is a practical problem.** N11 says `docker compose up` runs everything, but the worker must run `node scan.mjs` from a Windows path (plugin cache or clone) against the user's career-ops data folder. That needs Node in the worker image, bind mounts of Windows paths, and possibly Playwright if career-ops needs it. Or the worker runs on the host.
- The scheduler lives in the worker. If the laptop is off at 09:00, catch-up behavior is undefined.
- N4 (10k jobs, p95 < 300 ms) and full OpenTelemetry are heavy for a single user. Are they there for the showcase?
- Numbering: N12 sits between N7 and N8; phases run 0–9, 11, 12, 10.

Questions:
- **Q8.1 [C]** Runtime: (a) everything in Docker, including the worker with Node + mounted career-ops, (b) Postgres in Docker and api/worker/web run natively on Windows via `uv`/`npm` during development, Docker only for the demo, or (c) the worker on the host, the rest in Docker. Rec: (b) for development speed on Windows, keeping (a) working for the public demo. **Answer:** ______
- **Q8.2** Missed schedules (laptop was off): catch up on next start, or skip? **Answer:** ______
- **Q8.3** Keep N4 (perf at 10k jobs) and full OpenTelemetry as showcase items, or defer them? **Answer:** ______
- **Q8.4** Is Docker Desktop running reliably on this machine (testcontainers needs it for every integration test run)? **Answer:** ______
- **Q8.5** Data location and backup target (= D6). **Answer:** ______
- **Q8.6** Repo name, public or private, licence (= D7). **Answer:** ______
- **Q8.7** career-ops: a pinned separate clone, or the plugin path (= D17)? **Answer:** ______
- **Q8.8** Notifications (= D20): none, Windows toast, Telegram, or email-to-self? **Answer:** ______

### C9. UI

- **Q9.1** Is a web dashboard the right primary surface, or would you rather drive most things from Claude Code (slash commands / an MCP server over the same backend) with the dashboard for boards and charts? This changes what feature 001 delivers. **Answer:** ______
- **Q9.2** Any tracker or dashboard you've liked (Huntr, Teal, Notion templates, a spreadsheet)? What did you like or hate? **Answer:** ______
- **Q9.3** Desktop only, or should it work on your phone too (for example, logging an interview right after a call)? **Answer:** ______

---

## Part D — Quick-accept list (existing decisions I'd simply take as recommended)

D1 (local content-addressed storage), D3 (hash + label + sequence), D4 (PDF + DOCX), D5 (cv.md = facts), D8 (Postgres), D18 (export on request), D21 (localhost only), D23 (own approval UI), D24 (Resume-Matcher later), D25 (no scraping), D26 (label as you go), D28 (uv, npm, Python 3.12, Node 22, GitHub Actions).

**Answer:** accept all / except: ______

---

## Suggested order to answer

1. Part B (Q-G1–Q-G6): the why shapes everything.
2. [C] items: Q-SK1–Q-SK3, A.4 constitution, Q-T1, Q5.7, Q8.1.
3. [F1] items for `001-job-intake` / `002-fit-triage`: Q1.1–Q1.3, Q2.1, Q2.2, Q2.8, Q3.1, Q7.1.
4. The rest whenever the feature that needs it comes up. `/speckit.clarify` will ask about it again then.
