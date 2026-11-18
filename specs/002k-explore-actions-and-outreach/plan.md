# Implementation Plan: Explore row actions and outreach drafts

**Branch**: `002k-explore-actions-and-outreach` | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002k-explore-actions-and-outreach/spec.md`

## Summary

The Explore row keeps only **I applied** and **I inquired**. The resume choice and a renamed **Pick a date** move into the expanded row (front end only, using a `compact` form of the existing `PipelineControl`). Each job gains three actions that produce drafts the person edits and copies or downloads: a LinkedIn **connection request** (at most 200 characters), a **referral message** (polite, not pushy) and an **ATS-friendly tailored resume** (PDF and DOCX). HireTitan never sends anything.

Approach: a new feature module `hiretitan.drafts` with three tables (migration `0021_drafts`). Each request starts a one-node workflow run (`outreach_draft` or `tailor_resume`) on the existing workflow runner, like 002's `recheck`, which reads the job's description once into bounded keywords, writes with the model chosen for that case (**fast** for keyword extraction and both messages, **strong** for the tailored resume, set in each prompt's `meta.yaml`; the eval compares both tiers for the messages), runs deterministic truthfulness and tone checks, repairs once, then falls back. Contacts and the person's own contact details never reach the AI: prompts use placeholders that HireTitan fills afterwards, keeping 002b's FR-022. Resume facts (employers, titles, dates) are copied from the profile by id; the model only rewords. Files are rendered on request with `python-docx` and `reportlab`. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22).

**Primary Dependencies**: as today (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, procrastinate, OpenAI SDK through the LLM port, Jinja2 prompts, rapidfuzz; React 19, TanStack Query, React Router, Tailwind 4 + shadcn/ui). **Changed**: `reportlab` moves from the dev group to runtime (BSD). `python-docx` is already runtime. Nothing else added.

**Storage**: PostgreSQL 16, schema `app`. New tables `job_keywords`, `outreach_drafts`, `tailored_resumes` ([data-model.md](data-model.md)); migration `0021_drafts` (parent `0020_first_rules`). No existing table changes. No stored files (PDF and DOCX are rendered on request).

**Testing**: pytest + Testcontainers Postgres (repos, constraints, cascades, delete-all, API); pure domain tests for the checks, tone rules, keyword match and placeholder filling; the scripted fake LLM (`HIRETITAN_LLM=fake`) for worker tasks, repair and fallback, and a recorded-call test for privacy; render tests that read the PDF and DOCX back (`pdfplumber`, `python-docx`); Vitest + Testing Library; the Playwright job-search journey extended. Two eval sets, synthetic only. Test names follow the matrix in [contracts/rest-api.md](contracts/rest-api.md).

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA).

**Performance Goals**: a connection request is ready in under 10 s at p95 with the fast model; a referral message under 10 s; a tailored resume under 60 s with the strong model. Keywords are extracted once per job description. Rendering a PDF or DOCX takes under 1 s.

**Constraints**:
- Nothing is sent, posted or opened outside the app (constitution I; `test_no_send.py` covers the new module).
- Only confirmed-profile facts; deterministic rejection of numbers, technology terms and names not in the profile (constitution II, research R4).
- The raw job description never reaches a drafting or tailoring prompt; only the bounded keyword extraction sees it (constitution III, R3).
- Contacts and the person's own contact details never reach the AI (002b FR-022, R2).
- No cost display or budget (constitution IV).
- `search` may not import `drafts`; `drafts.workflow` may not import contacts code.

**Scale/Scope**: one person, tens of drafts and resumes. 1 migration, 4 prompts, 13 endpoints (one of them in `search`: paste a description), 4 events, 1 new back-end module, 1 change to `DELETE /jobs/{id}` (clean-up hook), 4 new UI pieces (compact row, draft panel, resume page, Profile list), 2 eval sets.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | Drafts and resumes are shown, editable and only copied or downloaded by the person. No adapter can send; the no-send architecture test scans `hiretitan.drafts`. No request to LinkedIn is made. | ✅ | ✅ |
| **II. Truthful profile** | Only confirmed-profile facts. Drafts cite fact ids; numbers, technology terms and names outside the profile are rejected by deterministic checks (R4). Resume employers, titles and dates are copied by id, not written by the model (R5). Only profile-backed keywords may be added (R6). | ✅ | ✅ |
| **III. Untrusted input is data** | The description is sanitized and screened, then only a tool-less fast step with a strict, bounded schema reads it (R3). Drafting and tailoring see only that structured result. Signals are stored and shown. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | Four versioned prompts through the LLM port, each with its tier in `meta.yaml` (R1); schema validation, then the checks, one repair, then a defined fallback; every call logged with prompt version and model. Out of credit pauses and shows the provider's message. No cost figures. v1 prompts have eval sets ready for v2 gating (R12). | ✅ | ✅ |
| **V. Test-first** | Tests first, named after FR/US/SC ids (matrix); real Postgres; fakes only for the LLM. | ✅ | ✅ |
| **VI. Lean architecture** | No new external boundary: the module uses the existing LLM port and renders files with no storage. Three narrow lookups (`ProfileFactsSource`, `JobSource`, `ContactLookup`) let `drafts` read the profile, jobs and contacts without importing `profile` or `search` internals, implemented in `drafts_wiring.py` like 002f's `ResumeLookup`. The lookups, the new module and a job clean-up hook are justified below. The two workflows reuse the existing runner as one-node graphs (R7). | ✅ | ✅ |
| **VII. Permitted sources only** | Adds no source and fetches nothing. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Data stays in the person's database; per-item delete, job delete and Delete all remove it (tested). Contacts never leave the install, not even to the AI provider. Eval data is synthetic. `reportlab` and `python-docx` are pure wheels on all three platforms. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter (new layers contract entry, `drafts.workflow` added to `contacts-stay-out-of-ai-paths`, `drafts-boundary`), coverage gate, licence gate (reportlab BSD), frontend gates including `npm run build`, Playwright. Reviews: Python/FastAPI, database, React, security. Evals before merge (Ravi approves the spend). | ✅ | ✅ |

**Result**: passes; four items are justified in Complexity Tracking. (Re-checked after `/speckit-analyze` on 2026-11-17: injection signals are now shown (III), the lookups are justified (VI), a tailored resume can be deleted on its own (VIII), and every test name carries an FR, SC, US or EC id (V).)

## Project Structure

### Documentation (this feature)

```text
specs/002k-explore-actions-and-outreach/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── rest-api.md      # Phase 1 (endpoints, events, test matrix)
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0021_drafts.py
├── pyproject.toml                               # reportlab -> runtime
├── .importlinter                                # drafts in layers/pure-domain; drafts-boundary;
│                                                # drafts.workflow in contacts-stay-out-of-ai-paths
├── src/hiretitan/
│   ├── drafts/
│   │   ├── domain/
│   │   │   ├── recipient.py                     # kind from role keywords; first name; placeholders fill
│   │   │   ├── facts.py                         # profile facts for drafting, years of experience
│   │   │   ├── checks.py                        # numbers, tech terms, names, citations, 200-char limit
│   │   │   ├── tone.py                          # pressure phrases, easy-decline rule
│   │   │   ├── keywords.py                      # backed / matched / missing, score
│   │   │   ├── resume_doc.py                    # document model, build from profile by id, plain reorder
│   │   │   └── fallback.py                      # basic connection/referral templates from facts
│   │   ├── application/
│   │   │   ├── ports.py                         # ProfileFacts, JobFacts, ContactLookup (implemented in wiring)
│   │   │   ├── drafts.py                        # request, edit, delete; in-progress and state rules
│   │   │   └── tailoring.py                     # request, edit (recompute match), list
│   │   ├── infra/
│   │   │   ├── models.py                        # JobKeywordsRow, OutreachDraftRow, TailoredResumeRow
│   │   │   ├── repos.py
│   │   │   └── render/{pdf.py,docx.py}          # one template, single column
│   │   ├── workflow/
│   │   │   ├── outreach.py                      # OUTREACH_WORKFLOW: one-node graph (keywords -> write -> check
│   │   │   │                                    # -> repair/fallback -> store -> event), like search/workflow/recheck.py
│   │   │   ├── tailor.py                        # TAILOR_WORKFLOW: same shape for the resume
│   │   │   └── keywords.py                      # extract_job_keywords call and staleness
│   │   └── api/
│   │       ├── drafts.py                        # recipients, drafts endpoints
│   │       └── resumes.py                       # tailored resume endpoints, downloads, list
│   ├── prompts/
│   │   ├── extract_job_keywords/v1/             # tier: fast
│   │   ├── draft_connection_request/v1/         # tier: fast
│   │   ├── draft_referral_message/v1/           # tier: fast (eval compares strong)
│   │   └── tailor_resume/v1/                    # tier: strong
│   ├── drafts_wiring.py                         # ports from search/profile; job clean-up registration
│   ├── search/api/jobs.py                       # DELETE runs registered job clean-ups;
│   │                                            # new PUT /jobs/{id}/description (paste a description)
│   ├── api_main.py, worker_main.py              # include routers; add both workflows to workflow_registry
├── evals/outreach_drafts/, evals/tailor_resume/  # synthetic cases, runners
└── tests/{unit,integration,api,workflow,architecture,security}/drafts/

frontend/src/
├── features/jobs/PipelineControl.tsx            # compact form; "Pick a date"
├── features/explore/ExplorePage.tsx             # compact row; details hold full control + Act on this job
├── features/drafts/
│   ├── ActOnJob.tsx                             # three buttons
│   ├── DraftPanel.tsx                           # recipient choice, Writing…, text, count, cited facts, Copy
│   ├── TailoredResumePage.tsx                   # /jobs/:id/resume preview editor, keyword match, downloads
│   ├── TailoredResumesList.tsx                  # Profile page section
│   └── api.ts
└── features/jobs/JobDetails.tsx                 # ActOnJob on the job page too
```

**Structure Decision**: one new back-end feature module `drafts`, following the existing api > workflow > infra > application > domain layers, and one new front-end feature folder. Existing modules change only at their edges (`DELETE /jobs` clean-up hook, `PipelineControl` compact form, routes).

## Delivery order

US1 (Explore row) first, alone mergeable. Then the shared drafting path with US2, then US3, then US4. US4 is the largest piece. Ravi can stop after US3 and ship, then do US4 as its own PR on the same spec, and `tasks.md` keeps that cut clean.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New feature module `hiretitan.drafts` | Drafting is a separate capability with its own tables, prompts and endpoints; it lets the contacts contract name `drafts.workflow` as an AI path. | Putting it in `search` grows the largest module and needs a finer contacts contract. |
| Three lookups in `drafts/application/ports.py` (`ProfileFactsSource`, `JobSource`, `ContactLookup`) implemented in `drafts_wiring.py` | `drafts` needs the confirmed profile, a job and a company's contacts; the import contracts let a module use another only through its application layer, and the wiring keeps `drafts` testable with plain fakes. Same pattern as 002f's `ResumeLookup` and 002i's `ProposalSource`. | Importing `profile.infra` / `search.infra` repos directly breaks the boundary contracts; copying the queries into `drafts` duplicates them. |
| Job clean-up hook on `DELETE /jobs/{id}` (list of callables injected by wiring) | Jobs are soft-deleted, so CASCADE does not fire; `search` may not import `drafts`. | Calling drafts code from `search` breaks the module boundary; leaving rows behind breaks FR-009. |
| One-node graphs instead of the multi-node W5/W6 in `docs/architecture.md` | The review edits the stored row afterwards, so there is no interrupt; one node keeps a retry simple. The runner still gives retries, pause and resume. | A multi-node graph with an interrupt adds checkpoints and a review state with nothing to resume. |
