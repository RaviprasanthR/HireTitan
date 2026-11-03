# 01 — Requirements

Status: **DRAFT — awaiting review** · Date: 2026-11-03 · Owner: Ravi Prasanth R

Spec-driven workflow: **Requirements (this file) → Design (`02-design.md`) → Prompts (`03-prompts.md`) → Tasks (`04-tasks.md`)**. Nothing is implemented until all four are approved. Every requirement has an ID; design sections, tasks and tests reference these IDs so each line of code traces back to a requirement.

Notation: acceptance criteria use EARS (`WHEN <trigger> THE SYSTEM SHALL <response>`; `IF <condition> THEN …`; `WHILE <state> …`).

---

## 1. Goal

A single-user, self-hosted job-search agent that:

1. gathers openings from several sources into one deduplicated list,
2. filters and ranks them against my CV and targeting rules,
3. drafts LinkedIn referral notes, HR emails and follow-ups for the roles I pick,
4. tracks every application and its follow-ups in one dashboard,
5. records which resume version I sent with each application, and how each version performs,
6. tracks every interview round, the questions asked and my answers, reviews those answers, and turns the patterns into an analysis of where I lag and a preparation plan,

while **never taking an outward action without my approval**.

Secondary goal: a production-grade, well-tested project I can put on my resume.

## 2. Non-goals (v1)

- Submitting applications or sending messages/emails automatically.
- Scraping or automating LinkedIn, Naukri, Cutshort or any site whose terms forbid it.
- Multi-user accounts, teams, billing.
- Generating or tailoring PDF CVs — career-ops already does this (`/career-ops pdf`); this system only registers and tracks the resulting files (R9).
- Recording or transcribing live interview calls (consent and legal issues). Interviews are captured from my own typed notes or a transcript I paste.
- Re-building features career-ops or other well-maintained tools already provide (see design §17, reuse map).
- Mobile app.

## 3. Actors

| Actor | Description |
|---|---|
| **User** | Me. Reviews jobs, approves drafts, sends messages and applies manually. |
| **Scheduler** | Time-based trigger inside the worker (ingestion, follow-up checks). |
| **Agent** | The LangGraph workflows that call Claude. |
| **External systems** | career-ops CLI, Google Sheets, Anthropic API, Gmail API (phase 4). |

## 4. Functional requirements

### R1 — Job ingestion

| ID | Requirement |
|---|---|
| R1.1 | WHEN the user triggers ingestion for the **career-ops** source, or the scheduler fires it, THE SYSTEM SHALL run the career-ops scanner against the user's career-ops data directory and import every posting it accepted. |
| R1.2 | WHEN the user triggers ingestion for the **Google Sheet** source, THE SYSTEM SHALL read the configured sheet and import rows that contain a job URL as jobs, and rows that contain only a company as tracked companies. |
| R1.3 | WHEN the user submits a job URL manually (with optional title, company, location and pasted JD text), THE SYSTEM SHALL create the job from it. This covers Naukri, Cutshort, LinkedIn and any other site. |
| R1.4 | THE SYSTEM SHALL deduplicate jobs across all sources by a normalized URL key, keep one job row per posting, and record every source that reported it. |
| R1.5 | IF a source fails (process error, HTTP error, malformed data), THEN THE SYSTEM SHALL record the run as failed or partial with the error, keep every job already imported from that run, and leave other sources unaffected. |
| R1.6 | WHILE an ingestion run for a source is in progress, THE SYSTEM SHALL reject a second run for the same source (no concurrent duplicate runs). |
| R1.7 | THE SYSTEM SHALL record for each run: source, start/end time, status, postings found, jobs created, jobs updated, error. |
| R1.8 | Sheet header names SHALL be matched case- and spacing-insensitively with common aliases (e.g. "Job Link" = "url", "Role" = "title"). |
| R1.9 | *(Phase 4)* WHEN a job-alert email from a supported sender (Naukri, Cutshort, LinkedIn, Instahyre) arrives in the user's Gmail, THE SYSTEM SHALL extract the job links and ingest them, using read-only Gmail access. |

### R2 — Filtering and scoring

| ID | Requirement |
|---|---|
| R2.1 | WHEN a new job is ingested, THE SYSTEM SHALL apply deterministic prefilter rules (title keywords, location policy, blocked companies) before any LLM call, and record the reason for every rejection. |
| R2.2 | WHEN a job passes the prefilter and has no JD text, THE SYSTEM SHALL try to fetch the public JD; IF that fails, THEN THE SYSTEM SHALL mark the job "JD needed" and let the user paste it. |
| R2.3 | WHEN a job has JD text, THE SYSTEM SHALL extract structured job facts (seniority, required years, skills, location, work mode, compensation if stated) with an LLM. |
| R2.4 | WHEN job facts exist, THE SYSTEM SHALL score fit against the candidate profile on a 1.0–5.0 scale with: overall score, per-dimension scores (role fit, skills, seniority, location, compensation, company type), matched skills, gaps, and a one-line verdict. |
| R2.5 | The scorer SHALL apply the user's targeting rules: backend roles are the primary target and are never penalized for not mentioning AI; unfamiliar tech stacks are a bridgeable gap (≤ −0.5), never a disqualifier; product startups score higher; location policy is the user's ranked city list (preferred > conditional > low-priority > blocked); comp floor from the user's settings. |
| R2.6 | WHEN scoring completes, THE SYSTEM SHALL place the job in the review queue and pause its workflow until the user shortlists or dismisses it. |
| R2.7 | THE SYSTEM SHALL keep every fit assessment (history), tagged with the prompt version and model that produced it, so scores can be compared across prompt versions. |
| R2.8 | WHEN the candidate profile (`cv.md` or targeting rules) changes, THE SYSTEM SHALL let the user re-score selected jobs. |

### R3 — Contacts

| ID | Requirement |
|---|---|
| R3.1 | WHEN the user shortlists a job, THE SYSTEM SHALL search the public web for likely recruiter, hiring-manager or team contacts at that company and store them as **unverified suggestions** with their source URLs. |
| R3.2 | THE SYSTEM SHALL NOT log into, scrape or automate LinkedIn or any other site to obtain contacts. Only public search results are used. |
| R3.3 | The user SHALL be able to add, edit, verify and delete contacts manually. |
| R3.4 | Drafts addressed to a contact SHALL show whether the contact is verified. |

### R4 — Drafts and approvals

| ID | Requirement |
|---|---|
| R4.1 | WHEN the user shortlists a job, THE SYSTEM SHALL draft a LinkedIn referral/connection note and an HR email for it (per contact when contacts exist, otherwise a generic version). |
| R4.2 | LinkedIn connection notes SHALL respect the user's character limit (configurable; default 300). |
| R4.3 | Every factual claim about the candidate in a draft SHALL be traceable to a fact in `cv.md`; IF a draft contains a claim or number not in `cv.md`, THEN THE SYSTEM SHALL reject the draft before showing it. |
| R4.4 | Drafts SHALL be streamed to the UI while generated. |
| R4.5 | THE SYSTEM SHALL hold every draft in `pending_approval` until the user approves, edits-and-approves, regenerates or rejects it. |
| R4.6 | THE SYSTEM SHALL NOT send any draft. The user copies it and sends it; the user then marks it "sent". |
| R4.7 | Regenerating a draft SHALL keep the previous version (revision history). |

### R5 — Application tracking

| ID | Requirement |
|---|---|
| R5.1 | The user SHALL be able to create an application for a job and move it through the states `preparing → applied → responded → assessment → interview → offer`, plus terminal states `rejected`, `withdrawn`, `accepted`. Only transitions in the allowed transition table are accepted. WHEN the first interview round is added to an application (R10.1), THE SYSTEM SHALL move it to `interview` if the transition is allowed. |
| R5.2 | THE SYSTEM SHALL record every status change (from, to, time, actor, note) as an audit event. |
| R5.3 | WHEN an application moves to `applied`, THE SYSTEM SHALL schedule follow-ups at +7 and +14 days (configurable). |
| R5.4 | WHEN a follow-up is due and the application is still `applied`, THE SYSTEM SHALL draft a follow-up and put it in the approval queue. |
| R5.5 | WHEN an application leaves `applied`, THE SYSTEM SHALL cancel its pending follow-ups. |
| R5.6 | Concurrent updates to the same application SHALL NOT overwrite each other silently (optimistic locking). |

### R6 — Dashboard (UI)

| ID | Requirement |
|---|---|
| R6.1 | **Jobs**: list all jobs with filters (status, source, location, score range, company, posted date) and text search. |
| R6.2 | **Review queue**: scored jobs awaiting a decision, showing score, verdict, matched skills, gaps and a link to the posting; actions shortlist / dismiss / re-score. |
| R6.3 | **Applications board**: Kanban by status with drag-to-move (valid transitions only), applied date and next follow-up. |
| R6.4 | **Drafts**: pending approvals with live streaming, edit, approve, regenerate, reject, copy, mark sent. |
| R6.5 | **Follow-ups**: due today and overdue. |
| R6.6 | **Sources**: trigger ingestion per source, see last runs and errors. |
| R6.7 | **Insights**: counts per stage (found → shortlisted → applied → interview → offer), response rate, LLM cost this week. |
| R6.8 | **Application detail**: job, resume version used, drafts sent, status history, follow-ups, and an interview-rounds timeline with each round's questions, answers and reviews. |
| R6.9 | **Resume library**: all resume versions, which applications used each, and each version's outcomes (R9.5). |
| R6.10 | **Interview insights**: weak topics (topic × round type), trend over time, recurring questions, rounds lost and why, and the current preparation plan (R10.6–R10.8). |

### R7 — LLM governance

| ID | Requirement |
|---|---|
| R7.1 | Every prompt SHALL be a versioned file; THE SYSTEM SHALL record the prompt name, version and content hash with every LLM call and every artifact it produced. |
| R7.2 | Every LLM output SHALL be validated against a typed schema and then against business rules before it is used; invalid output SHALL be retried once with the validation errors, then fall back (R7.5). |
| R7.3 | All external text (JDs, web pages, search results, sheet cells, emails) SHALL be treated as untrusted data, never as instructions (see design §8). |
| R7.4 | THE SYSTEM SHALL log for every LLM call: node, model actually served, tokens (input, output, cache read/write), latency, cost, stop reason, outcome. |
| R7.5 | Each LLM node SHALL have a defined fallback (retry → refusal fallback model → deterministic degraded output or "needs attention"), and a failed node SHALL never crash the workflow or lose the job. |
| R7.6 | THE SYSTEM SHALL enforce a configurable daily LLM spend cap; WHEN the cap is reached, THE SYSTEM SHALL pause LLM work and show this in the UI. |
| R7.7 | A changed prompt version SHALL NOT become active until it passes its evaluation set at or above the configured threshold. |

### R8 — Candidate profile

| ID | Requirement |
|---|---|
| R8.1 | THE SYSTEM SHALL read the candidate profile from the career-ops data directory (`cv.md`, `config/profile.yml`, `modes/_profile.md`) and never write to those files. The only career-ops location it may write to is `interview-prep/sessions/`, and only for new session files on an explicit user export (R10.9). |
| R8.2 | THE SYSTEM SHALL parse `cv.md` into a list of identified facts (experience bullets, skills, education) used for grounding drafts (R4.3) and answer reviews (R10.5). |

### R9 — Resume versions

| ID | Requirement |
|---|---|
| R9.1 | The user SHALL be able to register a resume version by uploading a file (PDF or DOCX) or by importing one from the career-ops `output/` folder (tailored CVs made by `/career-ops pdf`). Each version has a label, origin (`base`, `career_ops_tailored`, `manual`), optional target job, upload time and notes. |
| R9.2 | THE SYSTEM SHALL store an immutable copy of every registered file, addressed by its SHA-256 hash, and SHALL NOT create a second version for a byte-identical file (it returns the existing one). |
| R9.3 | THE SYSTEM SHALL extract and store the resume's text for search and keyword analysis. |
| R9.4 | WHEN an application moves to `applied`, THE SYSTEM SHALL require the resume version used, or an explicit "not recorded" choice for back-filled applications. The user SHALL be able to change it later; changes are audited. |
| R9.5 | THE SYSTEM SHALL report per resume version: applications sent, responses, interviews, offers, and response rate — so I can see which version works better. |
| R9.6 | WHEN a resume version is linked to an application, THE SYSTEM SHALL store the keyword coverage of that resume against the job's description (computed with career-ops `keyword-match.mjs`, diagnostic only). |
| R9.7 | A resume version used by any application SHALL NOT be deletable; it can only be archived (hidden from pickers). |

### R10 — Interview rounds and preparation analysis

| ID | Requirement |
|---|---|
| R10.1 | The user SHALL be able to add interview rounds to an application, each with: sequence number, type (`screen`, `hiring_manager`, `technical`, `coding`, `system_design`, `behavioral`, `take_home`, `onsite`, `final`, `other`), scheduled time, duration, mode (video, phone, in-person), interviewer names and roles, status (`scheduled`, `completed`, `cancelled`, `rescheduled`, `no_show`), outcome (`pending`, `passed`, `failed`, `unknown`), and feedback received. |
| R10.2 | For each completed round, the user SHALL be able to record the questions asked and their own answers, one entry per question, with: question text, answer text, self-rating 1–5, optional notes (interviewer reaction, what I'd change), and time spent. |
| R10.3 | WHEN the user pastes free-form notes or a transcript for a round, THE SYSTEM SHALL split it into question/answer entries for the user to confirm and edit before saving. |
| R10.4 | THE SYSTEM SHALL tag every question with one or more topics from a controlled, extensible taxonomy (e.g. `system-design/caching`, `dsa/graphs`, `python/concurrency`, `databases/indexing`, `behavioral/conflict`, `project-deep-dive`). The user SHALL be able to change tags. |
| R10.5 | WHEN a question/answer entry is saved, THE SYSTEM SHALL review the answer and store: scores (correctness, depth, structure, communication; 1–5), a status (strong / solid / gap — same scale as the career-ops question bank), strengths, what was missing, and an improved answer outline. Any experience the outline cites SHALL come from `cv.md` facts; the review SHALL NOT invent experience. The user SHALL be able to override the status. |
| R10.6 | THE SYSTEM SHALL compute a weakness analysis across all rounds: per topic and per round type — number of questions, average self-rating, average review score, share of `gap` answers, trend over time; plus rounds marked `failed` and the topics in them. |
| R10.7 | THE SYSTEM SHALL detect recurring questions (similar questions asked across different interviews) and show how my answers to them changed. |
| R10.8 | On request, THE SYSTEM SHALL generate a preparation plan: (a) a general plan ranked by weakness severity and how often each topic is asked, and (b) a next-round plan for a specific application, using that job's facts, its earlier rounds and my weak topics. Each item has the topic, why it is prioritized (with the numbers), and concrete practice steps. |
| R10.9 | THE SYSTEM SHALL export a round as a career-ops interview session file (`interview-prep/sessions/{company}-{role}-{round}-{date}.md`, career-ops schema) and import existing session files, so career-ops `interview/debrief`, `interview/plan`, `interview/practice` and `weekly-digest.mjs` work on the same data. |
| R10.10 | Interview data (interviewer names, questions, answers) SHALL be stored locally only and SHALL be deletable per round or per application. |

## 5. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| N1 | Safety | No code path may send a message, email or application. Enforced by architecture (no sending adapters exist) and by a test that scans for outbound mail/LinkedIn clients. |
| N2 | Reliability | Workflow state is persisted; a crash or restart resumes paused/in-flight workflows without losing data or duplicating LLM calls already completed. |
| N3 | Idempotency | Re-ingesting the same postings creates no duplicates; re-running a queued task with the same dedupe key is a no-op. |
| N4 | Performance | Jobs list API p95 < 300 ms for 10k jobs; UI first load < 2 s locally. |
| N5 | Cost | Average LLM cost per fully processed job (extract + score) ≤ $0.05; daily cap default $2. |
| N6 | Security | Secrets only from environment; API bound to localhost by default; single-user token auth if exposed; no secrets in logs or prompts. |
| N7 | Privacy | Contact data, interviewer names and interview Q&A are stored locally only and can be deleted completely; resume files live in a local volume, never in the repo. |
| N12 | Reuse | Before building a capability, check career-ops and well-maintained open-source tools; reuse when it fits the architecture and licence, and record the decision in the reuse map (design §17). |
| N8 | Observability | Structured JSON logs with trace IDs; OpenTelemetry traces across API → worker → LLM calls. |
| N9 | Quality | Backend: ruff + mypy `--strict` clean; ≥ 90% line coverage on domain and application layers, ≥ 80% overall. Frontend: typecheck + lint clean; component tests for every page. |
| N10 | Maintainability | Hexagonal architecture: the domain has no imports from FastAPI, SQLAlchemy, LangGraph or the Anthropic SDK. |
| N11 | Portability | Runs with `docker compose up` (Postgres, API, worker, web) on Windows, macOS and Linux. |

## 6. Constraints and assumptions

- Single user, local machine (Windows 11 + Docker Desktop). Cloud deployment is out of scope for v1 but must stay possible.
- career-ops is installed as a Claude Code plugin; its scripts are invoked as a CLI and treated as an external dependency with a pinned version (1.38.0).
- Claude API access through the official Anthropic Python SDK.
- Naukri and Cutshort have no official public API (checked 2026-11-03); they are covered by manual links (R1.3) and alert emails (R1.9).

## 7. Open questions (need answers before design sign-off)

**All open questions and architecture decisions are now tracked in `05-open-decisions.md` (D1–D30), with options and recommendations.** The table below is kept for history; the mapping is Q1→D11, Q2→D9, Q3→D7, Q4→D12, Q5→D13, Q6→D14, Q7→D2, Q8→D15, Q9→D16.

| # | Question | Affects |
|---|---|---|
| Q1 | Google Sheet layout: column names, and does it hold companies, openings, or both? Is it OK to share it as "anyone with the link can view", or must it stay private (needs Google service account)? | R1.2, design §6 |
| Q2 | Claude API key available? Monthly budget you're comfortable with? | R7.6, model choices |
| Q3 | Project location and name (`<repo path>`)? | repo |
| Q4 | Should applications also be written to the career-ops tracker so both stay in sync? | R5 |
| Q5 | LinkedIn account type (free = 200-char notes, Premium = 300)? | R4.2 |
| Q6 | Gmail ingestion of job-alert emails in phase 4 — yes/no? | R1.9 |
| Q7 | Where are your existing resume files (e.g. `<your existing resume PDFs>`)? Import them as the first versions? | R9.1 |
| Q8 | How will you usually capture interviews — typing Q&A per question, or pasting notes/transcripts after the call? | R10.2, R10.3 |
| Q9 | Any topics you already know you want tracked (e.g. DSA, system design, Go, Python, SQL, behavioral)? Seeds the taxonomy. | R10.4 |
