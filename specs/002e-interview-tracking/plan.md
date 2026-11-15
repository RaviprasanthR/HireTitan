# Implementation Plan: Interview tracking

**Branch**: `002e-interview-tracking` | **Date**: 2026-11-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002e-interview-tracking/spec.md`

## Summary

Each job in the pipeline (applied or inquired) gets an expandable detail panel in the In pipeline table, and the same panel on the job's page, holding the point of contact, how the job came (direct or a hiring firm), and interview rounds with their questions, answers and feedback. The Status column shows the latest round ("Round 2 scheduled", "Failed in round 3"), or Applied or Inquired when there are no rounds.

Approach: three new tables in the `search` module (`job_pipeline_details`, `interview_rounds`, `interview_questions`) with check constraints, so every item can be queried by field later. The status is derived at read time by a pure rule and added to the pipeline list with one lateral sub-query. Rules (numbering, Failed blocks new rounds, writes only for pipeline jobs) live in pure domain code and are enforced by the use cases. Soft delete and the duplicate merge are extended to remove or carry the details. A privacy guard (import-linter contract and a recorded-AI-calls test) keeps the data out of every AI path. Design decisions are in [research.md](research.md).

> **Dependency note.** The spec, plan and tasks were written on a branch cut from `002d-navigation-and-pipeline`, which was not merged yet. The constitution requires feature branches cut from `master`, so implementation starts only after 002d's PR merges and this branch is rebased onto `master` (T001). The new migration `0018_interview_tracking` has `0017_no_cost` (from 002d) as its parent.

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22). No runtime image change.

**Primary Dependencies**: as in 002d (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, React 19, TanStack Query, React Router, Tailwind 4 + shadcn/ui). **None added**.

**Storage**: PostgreSQL 16, `app` schema. Three new tables ([data-model.md](data-model.md)); no change to `jobs`. Migration `0018_interview_tracking`.

**Testing**: pytest + Testcontainers Postgres (domain rules, constraints, repos, API, lifecycle, delete-all); the scripted fake LLM recording every call for SC-003; Vitest + Testing Library; one step added to the Playwright job-search journey. Test names follow the matrix in [contracts/rest-api.md](contracts/rest-api.md).

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA), extending 002d. No worker or workflow change: everything is request/response.

**Performance Goals**: the pipeline list stays one query per page plus one lateral sub-query (no per-row lookups); the detail panel loads in one request.

**Constraints**:
- No outbound action and no AI use of this data (constitution I, IV, VIII; FR-010).
- Text from the person is cleaned with 001's sanitizer; links must be `http`/`https` and open with `rel="noopener noreferrer"`; emails and phones are plain text, not `mailto:`/`tel:` links (as in 002b).
- No cost shown anywhere (constitution 2.0.0, FR-015).

**Scale/Scope**: tens to a few hundred pipeline jobs, a handful of rounds each, dozens of questions per round at most. 3 tables, about 10 endpoints, 1 panel used in 2 places, 1 changed column.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | The data is the person's notes. Nothing sends to a contact: emails and phones are plain text, no invitations or reminders. The no-send architecture test scans the new files. | ✅ | ✅ |
| **II. Truthful profile** | Not touched. Interview notes are not candidate facts and are never given to AI. | ✅ | ✅ |
| **III. Untrusted input is data** | Only the person types this text; it is still cleaned (sanitizer, length caps), rendered as text, and links are limited to `http`/`https`. No AI reads it. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | No AI call, prompt or model is added. The import-linter contract that keeps contacts out of workflows, prompts and the LLM platform is extended to the interview modules, and a test asserts no recorded AI call contains interview text. | ✅ | ✅ |
| **V. Test-first** | Tests are written first and named after FR/US/SC ids (test matrix); real Postgres for repos and APIs; no new fakes. | ✅ | ✅ |
| **VI. Lean architecture** | No new module, port or dependency. Three tables inside `search`; pure rules in `search/domain/interviews.py`; status derived, not stored. | ✅ | ✅ |
| **VII. Permitted sources only** | Adds no source. LinkedIn links are stored text, never fetched. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Stored only in the person's database; Delete all my data truncates the new tables (tested); fixtures are synthetic. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter, coverage gate, frontend gates, Playwright. Reviews: Python/FastAPI, database, React, security. No prompt change, so no eval. | ✅ | ✅ |

**Result**: passes with no new deviation.

## Project Structure

### Documentation (this feature)

```text
specs/002e-interview-tracking/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── rest-api.md      # Phase 1 (endpoints and test matrix)
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0018_interview_tracking.py
├── .importlinter                         # contacts-stay-out-of-ai-paths gains the interview modules
├── src/hiretitan/search/
│   ├── domain/interviews.py              # kinds, states, limits, field checks, next number,
│   │                                     # can_add_round, status_summary (pure)
│   ├── application/interviews.py         # use cases: read, contact, source, rounds, questions
│   ├── infra/models.py                   # + PipelineDetailsRow, InterviewRoundRow, InterviewQuestionRow
│   ├── infra/repos.py                    # + InterviewsRepo (incl. rounds_matching); JobsRepo.page adds the summary
│   └── api/
│       ├── interviews.py                 # the routes in contracts/rest-api.md
│       ├── jobs.py                       # (002d) JobCardOut.interview; delete_job removes details
│       └── duplicates.py                 # (002) merge carries details (R7)
└── tests/
    ├── unit/search/test_interviews.py
    ├── integration/search/test_interviews_repo.py
    ├── api/search/test_interviews_api.py
    ├── api/search/test_interviews_lifecycle.py
    └── security/test_contacts_privacy.py # (002b) + interview text never in AI calls

frontend/src/features/
├── jobs/interview/
│   ├── InterviewPanel.tsx                # contact + source, rounds, questions; used in two places
│   ├── RoundCard.tsx
│   ├── QuestionList.tsx
│   ├── interviewApi.ts                   # query ['job-interview', id] and mutations
│   └── *.test.tsx
├── explore/PipelinePage.tsx              # (002d) expandable row with the panel; Status from `interview`
└── jobs/JobDetailPage.tsx                # (002d) the panel under the pipeline control
frontend/e2e/job-search.spec.ts           # + the interview step
```

**Structure Decision**: extend `search`, as 002b did for company contacts (research R1). The panel lives in `features/jobs/interview/` because both the pipeline table and the job page use it.

## Complexity Tracking

No constitution violations to justify.

| Addition | Why it is needed | Simpler option rejected |
|---|---|---|
| Three tables instead of one JSON column | FR-009 and SC-005: query by field, with the database enforcing kinds, states and the firm rule | JSONB per job: analytics would parse JSON and nothing enforces the rules |
| Explicit detail removal in `delete_job` and the merge | Jobs are soft-deleted, so cascades do not fire (R7) | Relying on cascades would leave orphaned notes on deleted jobs |
