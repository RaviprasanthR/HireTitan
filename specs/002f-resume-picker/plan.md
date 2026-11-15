# Implementation Plan: Resume picker

**Branch**: `002f-resume-picker` | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002f-resume-picker/spec.md`

## Summary

A pipeline job (applied or inquired) can record which stored resume file the person used. The choice is offered beside the date in the mark control ("I applied" / "I inquired"), starting on the person's last choice, and can be set, changed or cleared later in the edit card. The In pipeline list gets a Resume column, and the details show the name and the day the file was added. Removing a resume file leaves its name on the jobs as a "removed" note the person can clear.

Approach: three nullable columns on 002e's `job_pipeline_details` row (`resume_file_id` with a foreign key `ON DELETE SET NULL`, and a snapshot of the file's name and added day), plus a one-row `pipeline_settings` table holding the last choice (also `ON DELETE SET NULL`). Because the name and day are copied when the person chooses, removing the file needs no code in `profile`: the database clears the link and the snapshot becomes the "removed" note. The `search` module checks a chosen file through a small lookup port implemented in `search_wiring.py` (the existing composition pattern), so `search` never imports `profile`. Design decisions are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22). No runtime image change.

**Primary Dependencies**: as in 002e (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, React 19, TanStack Query, React Router, Tailwind 4 + shadcn/ui). **None added**.

**Storage**: PostgreSQL 16, `app` schema. Three columns added to `job_pipeline_details`, one new one-row table `pipeline_settings` ([data-model.md](data-model.md)). Migration `0019_resume_picker` (parent `0018_interview_tracking`). No change to `resume_files` or `jobs`.

**Testing**: pytest + Testcontainers Postgres (domain rule, constraints, foreign-key behaviour on file removal, repo, API, merge, undo, delete-all); the scripted fake LLM recording every call for SC-005; Vitest + Testing Library; one step added to the Playwright job-search journey. Test names follow the matrix in [contracts/rest-api.md](contracts/rest-api.md).

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA), extending 002e. No worker or workflow change.

**Performance Goals**: the pipeline list stays one query per page (the resume snapshot is on the details row already joined by 002e's lateral sub-query); no per-row file lookups.

**Constraints**:
- No outbound action and no AI use of the choice or the name (constitution I, IV; FR-013).
- The system never picks a resume except the person's own last choice (FR-014).
- Removed-file notes are plain text, never a link to a file (FR-009).
- `search` may not import `profile` (import-linter `search-boundary`).

**Scale/Scope**: a handful of resume files, up to a few hundred pipeline jobs. 1 migration, 4 endpoints added, 2 request bodies extended, 1 response field, 1 new UI control used in 2 places, 1 list column, 1 change to the profile's removal dialog.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | The choice is a label. Nothing attaches, uploads or sends a resume. The no-send architecture test already scans the touched `search` modules. | ✅ | ✅ |
| **II. Truthful profile** | Not touched: the resume files and profile are read, never changed. | ✅ | ✅ |
| **III. Untrusted input is data** | The only stored text is the file's own name (already cleaned at upload, ≤255 characters), rendered as text. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | No AI call, prompt or model is added. The new fields live in the details row and repo that the `contacts-stay-out-of-ai-paths` contract already forbids to AI paths; SC-003's recorded-call test is extended to seed a resume name (SC-005). | ✅ | ✅ |
| **V. Test-first** | Tests first, named after FR/US/SC ids (matrix); real Postgres, including the `ON DELETE SET NULL` behaviour; no new fakes. | ✅ | ✅ |
| **VI. Lean architecture** | No new module or dependency. One narrow lookup port (`ResumeLookup`) so `search` can check a file without importing `profile`; it follows the existing `ProposalSource` / `SetupFacts` composition pattern and is recorded in Complexity Tracking. | ✅ | ✅ |
| **VII. Permitted sources only** | Adds no source. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Stored only in the person's database; Delete all truncates the new table and the columns go with the details rows (tested). Removing a resume file keeps its name on jobs as a note by default (Ravi, 2026-11-15), but complete removal stays possible in one action: the removal dialog's "also clear the name from those jobs" option (off by default) and per-job Clear (FR-009). The note is plain text, never linked to the file or its content, and goes with the job and with Delete all (FR-011). | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter, coverage gate, frontend gates (including `npm run build`, see CONTEXT 2026-11-15), Playwright. Reviews: Python/FastAPI, database, React, security. No prompt change, so no eval. | ✅ | ✅ |

**Result**: passes; two items are justified below.

## Project Structure

### Documentation (this feature)

```text
specs/002f-resume-picker/
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
├── alembic/versions/0019_resume_picker.py      # 3 columns on job_pipeline_details, pipeline_settings
├── src/hiretitan/
│   ├── search/
│   │   ├── domain/resume_choice.py             # display rule (chosen / removed / none),
│   │   │                                       # offerable(parse_status) (pure)
│   │   ├── application/resume_choice.py        # ResumeLookup port; set/clear on a job; record on mark;
│   │   │                                       # last choice; usage counts
│   │   ├── infra/models.py                     # + PipelineDetailsRow.resume_*; PipelineSettingsRow
│   │   ├── infra/interviews_repo.py            # resume fields in details(), _prune keeps rows with a resume,
│   │   │                                       # merge_details carries the resume (R6), undo clears it
│   │   ├── infra/pipeline_settings_repo.py     # last choice read/write
│   │   └── api/
│   │       ├── jobs.py                         # AppliedIn/InquiredIn.resume_file_id; JobCardOut.resume
│   │       ├── interviews.py                   # GET .../interview adds resume; PUT/DELETE .../interview/resume
│   │       └── pipeline.py                     # GET /pipeline/resumes (last choice + usage counts);
│   │                                           # DELETE /pipeline/resumes/{id}/uses (clear a file from all jobs)
│   └── search_wiring.py                        # SqlResumeLookup over profile's ResumeFilesRepo
└── tests/
    ├── unit/search/test_resume_choice.py
    ├── integration/search/test_resume_choice_repo.py   # FK SET NULL, prune, merge, undo
    ├── api/search/test_resume_choice_api.py
    ├── security/ (interview privacy test)              # + resume name never reaches the model (SC-005)
    └── delete-all tests                                # + pipeline_settings and resume columns emptied

frontend/src/
├── features/jobs/
│   ├── resume/ResumeSelect.tsx                 # the choice (files newest first + None), shared
│   ├── resume/resumeApi.ts                     # useResumeOptions (GET /resumes filtered),
│   │                                           # usePipelineResumes (last choice, usage)
│   ├── PipelineControl.tsx                     # ResumeSelect beside the date; sends resume_file_id
│   ├── EditJobDialog.tsx / interview/InterviewPanel.tsx   # set, change, clear; removed note; read-only view
│   └── JobDetailPage.tsx                       # resume in the details
├── features/explore/PipelinePage.tsx           # Resume column (truncated, full name on hover)
└── features/profile/ResumeFiles.tsx            # removal confirmation says "used on N jobs"
frontend/e2e/job-search.spec.ts                 # mark applied with a resume, see it in the list
```

**Structure Decision**: extend the existing `search` module and its 002e pipeline-details row; no new module. The only cross-module need (checking a resume file) goes through a port wired in `search_wiring.py`, as for `ProposalSource`.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| `ResumeLookup` port in `search.application`, implemented in `search_wiring.py` | `search` must check that a chosen file exists and is not "not a resume", and read its name and added day for the snapshot, without importing `profile` (import-linter `search-boundary`). | Reading `app.resume_files` with raw SQL from `search.infra` couples `search` to another module's table behind the linter's back; trusting the client's name and day lets a request store a name that is not a stored file. |
| Two calls for "remove the file and clear its name from jobs" (search's `DELETE /pipeline/resumes/{id}/uses`, then profile's `DELETE /resumes/{id}`) | `profile` and `search` may not import each other, so one backend transaction would need a new cross-module dependency. | A profile use case calling into `search` breaks the module boundary. If the second call fails, the jobs simply lost the link early and the file stays, which the person sees and can retry (research R9). |
