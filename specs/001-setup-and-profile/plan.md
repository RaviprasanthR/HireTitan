# Implementation Plan: Setup and Profile (first slice)

**Branch**: `001-setup-and-profile` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-setup-and-profile/spec.md`

## Summary

Build the first working slice of HireTitan:
- a person uploads (or pastes) a resume;
- the app parses it, screens it as untrusted input, masks contact details, and runs one AI extraction (OpenAI, `fast` tier) through the LLM port with validation and a deterministic grounding check;
- the person reviews, edits and confirms the result as an immutable profile version linked to its source file.

A first-time user is led through four setup cards (name, resume, profile review, preferences) before the usual app appears (US5, amended 2026-11-04; design `docs/superpowers/specs/2026-11-04-first-run-onboarding-design.md`). Alongside that, they save job preferences (no AI) and see a dark dashboard with a setup checklist, an AI-key status banner and a budget cap. A key or budget problem pauses AI work without losing anything.

Technically, this slice also lays the foundation every later feature reuses: the backend skeleton (FastAPI api + Procrastinate worker + PostgreSQL), the `platform/` layer (LLM port + OpenAI adapter + budget guard + validation chain, untrusted-input pipeline, workflow runs + LangGraph checkpointer, file storage, SSE), the React shell, docker compose, and CI gates. Design follows the approved [architecture](../../docs/architecture.md); open points are settled in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, managed with uv); TypeScript 5 strict (frontend, Node 22)

**Primary Dependencies**:
- Backend: FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, psycopg 3, Procrastinate, LangGraph + langgraph-checkpoint-postgres, openai SDK, tiktoken, pdfplumber, pypdf, python-docx, phonenumbers, rapidfuzz, sse-starlette.
- Frontend: React 19, Vite, React Router, TanStack Query, Tailwind 4 + shadcn/ui, react-hook-form + zod, openapi-typescript.

Versions and licences: research R1.

**Storage**: PostgreSQL 16 (schemas `app`, `lg`, plus Procrastinate tables); a local file volume for resumes, content-addressed by sha256 (`FileStoragePort`).

**Testing**: pytest + Testcontainers PostgreSQL 16 (integration, API, workflow), a fake LLM (scripted, prompt-recording), respx recorded fixtures (OpenAI adapter contract), import-linter (architecture), a security attack set; Vitest + Testing Library; Playwright e2e against the stack with the fake LLM.

**Target Platform**: the user's own machine (Windows, macOS, Linux) via `docker compose up`; browser on `127.0.0.1`.

**Project Type**: web application (backend api + worker, frontend SPA served by the api).

**Performance Goals**: extraction of a two-page resume ≤ 60 s p95 (SC-002, measured by the eval in T051/T067); a 5 MB upload accepted (202) in < 2 s (asserted in T042).

**Constraints**:
- local only (127.0.0.1), no login;
- API keys only in `.env`, never stored, logged or sent to the browser;
- ≤ $0.05 per extraction (SC-007);
- AI input ≤ 30,000 characters;
- uploads ≤ 5 MB / 20 pages;
- no outbound actions (constitution I);
- no personal data in the repo.

**Scale/Scope**: one user per install; tens of resume files and versions; 5 screens (Home, Profile + review + versions, Preferences, Review, Settings) plus the four setup cards; about 25 endpoints; 1 workflow (W1); 1 prompt (`extract_profile` v1).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | Extraction ends in a review interrupt; nothing becomes the profile until the user confirms (FR-017). The high-severity injection pause hands the decision to the user (FR-007). Dropped items are shown with reasons (FR-011). No sending code exists; the architecture no-send test is added in this slice. | ✅ | ✅ |
| **II. Truthful profile** | The deterministic grounding check drops anything not in the resume text (R5). Only the confirmed version is visible to other modules (FR-022, public `profile.application.get_current_profile`). Item ids enable later citation. | ✅ | ✅ |
| **III. Untrusted input is data** | Sanitize → screen → mask → delimit → quarantined `extract_profile` (no tools, strict bounded schema). Hidden text is excluded and shown (R6). Flags are stored and shown (R7). An attack test set ships. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | One `LlmPort`. The OpenAI adapter comes first; Anthropic, Gemini and OpenAI-compatible adapters land before the public release (ADR-02, approved; **recorded deviation D1**). Schema → rules → grounding, one repair, then fallback. The prompt is a versioned file with provenance on every artifact. Every call is logged. The budget guard blocks before the call. Native structured output, or JSON mode + strict parse as fallback (degrade gracefully). Eval runner for SC-003 (gate from v2). | ✅ | ✅ |
| **V. Test-first** | Every task starts with failing tests named after FR/US/SC ids (contract matrix in [profile-ingest-workflow.md](contracts/profile-ingest-workflow.md)). Real Postgres via Testcontainers. Fakes only for the LLM provider and the clock; file storage uses a real temporary folder. Respx contract tests for the OpenAI adapter. | ✅ | ✅ |
| **VI. Lean architecture** | Ports only for the LLM, file storage and clock. The document parser, sanitizer and grounding check are plain functions, not ports. SQLAlchemy is used directly in `infra/`. Pure `domain/` packages enforced by import-linter. Three feature modules (`profile`, `preferences`, `setup`) + `platform`. | ✅ | ✅ |
| **VII. Permitted sources only** | No job sources in this slice. The only outbound host is the OpenAI API (allowlisted). | ✅ n/a | ✅ n/a |
| **VIII. Self-hosted privacy and portability** | Local only; key in `.env`; contact masking (FR-008a); no telemetry; logs redact resume text; delete-file and delete-all (FR-034/035); synthetic fixtures only; `docker compose up` works on all three OSes (R14); defaults documented and nothing person-specific (FR-024). A guided first-run setup ships in this slice (US5), which closes **recorded deviation D2**. | ✅ | ✅ |
| **Quality gates** | CI runs ruff, mypy --strict, import-linter, pytest with coverage gates, frontend typecheck/lint/tests, and licence + vulnerability checks (R15). Per-story reviews: python, FastAPI, security, database and React reviewers. The prompt eval report goes in the PR. | ✅ | ✅ |

**Result**: passes before research and after design, with two recorded, time-limited deviations (D1, D2 in Complexity Tracking), both approved by Ravi. D2 is closed in this slice by US5; D1 must close before the first public release.

## Project Structure

### Documentation (this feature)

```text
specs/001-setup-and-profile/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── rest-api.md
│   └── profile-ingest-workflow.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks, not created here)
```

### Source Code (repository root)

```text
docker-compose.yml               # db, migrate, api, worker (127.0.0.1 only)
Dockerfile                       # multi-stage: build SPA → Python 3.12 slim image
.github/workflows/ci.yml         # gates (R15)

backend/
├── pyproject.toml               # uv; ruff, mypy, import-linter, pytest config
├── alembic/                     # migrations (app schema)
├── src/hiretitan/
│   ├── api_main.py              # FastAPI composition root (+ static SPA)
│   ├── worker_main.py           # Procrastinate worker composition root
│   ├── profile/
│   │   ├── domain/              # ProfileContent, confirm rules, grounding, diff (pure)
│   │   ├── application/         # ingest commands, review/confirm, versions, get_current_profile
│   │   ├── infra/               # SQLAlchemy tables/repos, document parsing (pdf/docx)
│   │   ├── workflow/            # W1 LangGraph graph + nodes
│   │   └── api/                 # /resumes, /profile/* routers
│   ├── preferences/
│   │   ├── domain/              # Preferences, defaults, validation (pure)
│   │   ├── application/ · infra/ · api/
│   ├── setup/
│   │   ├── domain/              # checklist rules, setup step (pure)
│   │   ├── application/         # status, settings, key check, onboarding, delete-all
│   │   ├── infra/ · api/        # /status, /settings, /onboarding, /data
│   ├── platform/
│   │   ├── llm/                 # LlmPort, OpenAiAdapter, FakeLlm, budget guard, validation chain,
│   │   │                        #   prompt registry, models.yaml (tiers + prices)
│   │   ├── untrusted/           # sanitize, screen (rules), hidden_text, mask_contacts, delimit
│   │   ├── runtime/             # Procrastinate app, workflow_runs + run state machine,
│   │   │                        #   LangGraph checkpointer, pause/resume, events (NOTIFY → SSE)
│   │   ├── storage/             # FileStoragePort + local volume adapter
│   │   ├── clock/ · config/ · db/ · security/ (log redaction)
│   └── prompts/extract_profile/v1/{system.md, user.md.j2, schema.py, meta.yaml}
├── evals/extract_profile/       # 11 synthetic English resumes + expected facts + runner (R10)
└── tests/
    ├── unit/ · integration/ · contract/ · workflow/ · api/
    ├── architecture/            # import-linter, no-send test
    ├── security/                # attack set (hidden text, injections, masking)
    └── fixtures/resumes/        # synthetic only (+ generator script)

frontend/
├── package.json · vite.config.ts · tsconfig.json
├── src/
│   ├── app/                     # router, query client, layout shell, banner
│   ├── theme/                   # CSS variables from the palette (architecture §10)
│   ├── api/                     # generated OpenAPI types + fetch client, SSE hook
│   ├── features/
│   │   ├── setup/               # first-run setup cards (US5) and the guard around the shell
│   │   ├── home/                # greeting + setup checklist
│   │   ├── profile/             # upload, progress, review editor, versions, manual entry
│   │   ├── preferences/         # form (LPA handling)
│   │   ├── review/              # items waiting for the user
│   │   └── settings/            # key status, budget, tiers (read-only), delete-all
│   └── components/ui/           # shadcn components
└── e2e/setup-and-profile.spec.ts
```

**Structure Decision**: web application with `backend/` (package by feature, layers inside, shared `platform/`, as in architecture §3) and `frontend/` (feature folders). W1's LangGraph code lives in `profile/workflow/`; it depends on `application` and `platform`, never the other way round (import-linter contract). A new `setup` module owns settings, AI status and delete-all. Delete-all calls each module's public `application.delete_all()` instead of reaching into their tables.

### Import-linter contracts (added in this slice)

1. Layers per module: `api → workflow → application → domain`; `infra` may import `application` and `domain` only.
2. `*.domain` must not import fastapi, sqlalchemy, langgraph, procrastinate, openai, pydantic_settings, or `hiretitan.platform.runtime`.
3. Modules independent: `profile`, `preferences` and `setup` import each other only via `<module>.application`.
4. `platform` must not import any feature module.

## Delivery order (input for /speckit-tasks)

1. **Foundation** (blocks everything): repo tooling (uv, ruff, mypy, import-linter, pytest + Testcontainers), Alembic baseline, `platform/db`, `clock`, `config` (reads `.env`), `storage`, `runtime` (Procrastinate, workflow_runs + state machine, checkpointer, NOTIFY/SSE), FastAPI app with problem+json, frontend scaffold + theme + shell, compose + Dockerfile, CI workflow, architecture tests (layers, no-send).
2. **AI platform**: `LlmPort`, FakeLlm, budget guard + `llm_calls`, validation chain, prompt registry, OpenAI adapter (respx contract tests), `models.yaml`, provider key check + `provider_status`, pause/resume of runs.
3. **US1 (P1)**: untrusted pipeline (sanitize, screen, hidden text, masking), parsers (PDF/DOCX/paste), grounding + confirm rules, W1 graph, review endpoints + autosave, versions, manual create/edit, review editor UI, attack set, eval runner.
4. **US2 (P2)**: preferences domain + defaults, endpoints, form UI with LPA and suggestions.
5. **US3 (P3)**: status/checklist endpoint, banner, Home, Review list, Settings page (budget, tiers read-only, key status, Check again).
6. **US5 (P1, added 2026-11-04)**: onboarding state (name, setup-completed time, step rule), manual reviews that autosave (W1 manual mode), setup cards and the guard that shows them instead of the shell. Built after US3 because it reuses the status, banner and Settings, and before US4 so delete-all clears it too.
7. **US4 (P3)**: delete file, delete all (backend + Settings UI).
8. **Polish**: Playwright journey (quickstart A), eval run + report (ADR-11 decision), docs (README run steps, user-guide defaults), `docs/CONTEXT.md` update.

Each user story is reviewed (python/FastAPI, security, database, React reviewers) before it's marked done.

## Complexity Tracking

### Recorded deviations (constitution governance: deviations recorded and justified here)

| ID | Principle | Deviation | Justification | Closing condition |
|---|---|---|---|---|
| D1 | IV (OpenAI, Anthropic, Gemini and OpenAI-compatible MUST be supported) | Only the OpenAI adapter is built in this slice | ADR-02, decided by Ravi 2026-11-03: build and evaluate with one provider first. The port, fake LLM and all tests are provider-neutral, so adding adapters changes no callers | The other three adapters, each with recorded-fixture contract tests, are merged before the first public release (tracked as a follow-up in T070) |
| D2 | VIII (`docker compose up` plus a first-run setup wizard) | No guided wizard; the Home setup checklist links each step | Spec Out of scope: wizard polish comes later in 001. The checklist covers the same steps (key, resume, profile, preferences) | **Closed by US5 (T071–T077, added 2026-11-04)**: guided first-run setup cards |

### Notable additions

Recorded for transparency (not deviations):

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| `setup` feature module (not in architecture §3's list) | Owns settings, AI status and delete-all, which belong to no other feature | Putting them in `platform/` would make platform own user data and endpoints, against the "platform is shared building blocks" rule |
| `profile_reviews` table alongside the LangGraph checkpoint | Autosaved drafts and the Review list need queryable rows (R11) | Drafts in the checkpoint would need a graph update per autosave, and LangGraph internals would leak into queries |
| `paused` run status + `resume_paused_runs` task | FR-030/032: pause, never fail, on key or budget problems (R9) | Retry-with-backoff wastes calls and hides the cause; failing loses work |
| `display_name` + `setup_completed_at` on `app.settings` (US5) | The setup step and the greeting need the user's name and "setup finished" to survive a closed tab (FR-038/040) | Browser storage is lost with another browser or a cleared profile, and the server could not tell an existing install from a fresh one |
| W1 "manual" mode (a run and review with no resume file) | "Type it in myself" must autosave like any review (FR-019) | A second draft store for manual profiles would duplicate review autosave, confirm and the Review list |
| docker compose + CI in the first slice | Constitution VIII (compose must work) and quality gates on every PR | Deferring them means finding cross-OS and gate problems late |
