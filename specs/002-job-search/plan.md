# Implementation Plan: Job Search and Home Page List

**Branch**: `002-job-search` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-job-search/spec.md` (4 clarifications, 2026-11-05)

## Summary

Turn the confirmed profile and preferences into a short list of real, open, **relevant** jobs on the home page (**Explore**):
- The person approves **search rules**, proposed deterministically from their preferences and profile.
- **Search now** works through the company list in **batches of 8 companies**. For each batch it fetches jobs from the companies' public job boards through the bundled, pinned **career-ops** scanner (or from their careers pages, in US3). It then normalizes and deduplicates them, **skips obvious noise with the rules for free**, and has the **`fast`-tier model judge the rest** in compact batches of 10 job cards per call. The relevant jobs are added to Explore as soon as the batch is done, with the cost so far shown live.
- The search **stops cleanly** on Stop, on the monthly budget, or on the provider's **out-of-credit** error (OpenAI `insufficient_quota`, which today's adapter wrongly retries). It keeps what it found, and the next search continues with the companies not yet read.
- Skipped jobs keep their reason and can be restored.
- The person marks jobs **"I applied"**, which moves them to the **Applied** list (filled from Gmail in 003).
- They can paste a job, and manage the company list (add with board discovery, hide, edit, CSV import and export, a check-manually list).

Design decisions are in [research.md](research.md): career-ops as a subprocess (R1), provider allowlist and robots (R2), batching (R4), rules then AI (R5), out of credit (R7).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22). **New in the runtime image:** Node 22 + career-ops v1.38.0 (pinned; no Playwright browser download).

**Primary Dependencies**: as in 001 (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, Procrastinate, LangGraph, openai, rapidfuzz, React 19, TanStack Query, Tailwind 4 + shadcn/ui). **New:**
- `extruct` or a small JSON-LD parser over `selectolax` for careers pages, chosen in the US3 task with a licence check;
- `protego` (robots.txt parser, BSD);
- `httpx` (already a transitive dependency) for careers pages with a per-host rate limiter and cache;
- career-ops (MIT; Node).

**Storage**: PostgreSQL 16, `app` schema. New tables: `companies`, `search_rule_sets`, `search_runs`, `search_run_companies`, `jobs`, `job_sources`, `relevance_decisions`, `possible_duplicates` ([data-model.md](data-model.md)). A career-ops data folder lives on the data volume (`<data>/career-ops/`). Seed data: `backend/seed/companies.yaml`, `backend/seed/title_synonyms.yaml`.

**Testing**:
- pytest + Testcontainers Postgres.
- `FakeCareerOps` and recorded `scan.mjs --json` outputs; a recording-proxy allowlist test that runs the real pinned career-ops.
- Recorded careers pages and robots.txt.
- Recorded OpenAI 429 bodies (`insufficient_quota`, `rate_limit_exceeded`).
- The scripted fake LLM.
- An injection set for job text.
- The `judge_relevance` eval (60 labelled synthetic postings × 2 profiles, 3 repeats).
- Vitest + Testing Library; a Playwright journey on the synthetic seed.

**Target Platform**: the user's machine via `docker compose up` (Windows, macOS, Linux); browser on `127.0.0.1`.

**Project Type**: web application (api + worker + SPA), extending 001.

**Performance Goals**: first relevant jobs visible after the first batch (SC-006); a full search under 5 minutes (SC-002); Explore's first page under 2 s with 1,000 jobs (SC-010, keyset paging and an index).

**Constraints**:
- No outbound actions.
- Permitted sources only: allowlisted career-ops providers and robots.txt-honouring careers pages.
- AI cost for a full first search under $0.25 (estimated at about $0.08, research R15).
- Each job is judged by the AI at most once.
- Job excerpts ≤ 1,200 chars and ≤ 10 job cards per call.
- Stored descriptions ≤ 30,000 chars.
- One search at a time.
- No personal data in the seed (company columns only).

**Scale/Scope**:
- 62 shipped companies, about 17 readable by board at first (feasibility study) and more after the maintainer's resolution pass.
- Hundreds to low thousands of jobs per install.
- 6 new screens: Explore (home), Applied, Job detail, Search rules, Search run summary and history, Companies.
- About 30 new endpoints.
- 2 workflows: W3 `job_search` and W8 company discovery.
- 2 prompts: `judge_relevance` v1 and, in US3, `extract_jobs_from_page` v1.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | Rules are proposed and only used after approval (FR-004). Every skip, whether by a rule or the AI, stores a visible reason and can be restored (FR-024/025). Applied, delete and merge are the person's own actions. Nothing applies or sends; the no-send architecture test is extended to the `search` module, and career-ops can only reach allowlisted read-only endpoints (R2). | ✅ | ✅ |
| **II. Truthful profile** | `judge_relevance` gets a profile card built only from the confirmed profile and preferences, and returns yes/no plus a reason. It writes no profile facts (FR-035). Scoring, which would cite facts, is out of scope (clarification 1). | ✅ | ✅ |
| **III. Untrusted input is data** | All job and page text goes through 001's sanitize and screen pipeline. Flags are stored and shown. Raw excerpts reach only tool-less, bounded-schema steps (`judge_relevance`, `extract_jobs_from_page`), with ref checks on the output (FR-038/039). The injection test set covers every step that reads job text (SC-011). | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | Versioned prompts with provenance on each decision. Schema check, then business check, one repair, then fallback to rules only. Every call is logged and counted against the budget, and blocked at the cap. `judge_relevance` must pass its eval before it is active (R6). Out of credit is handled in the port (R7). **"Batch AI actions MUST show an estimated cost first"** is met by showing the live cost per batch with Stop, not an upfront estimate: **recorded deviation D3**, decided by Ravi. D1 (OpenAI only) stays open from 001. | ⚠️ D3 | ⚠️ D3 |
| **V. Test-first** | Tests are named after US/FR/SC ids ([test matrix](contracts/job-search-workflow.md#test-matrix-names-reference-requirement-and-scenario-ids)). Real Postgres. Fakes only for career-ops (external CLI), careers pages (external source), the LLM and the clock. Contract tests for `CareerOpsPort`, `CareersPageSource` and the OpenAI 429 mapping. | ✅ | ✅ |
| **VI. Lean architecture** | Two new ports, both at real boundaries: `CareerOpsPort` (external CLI) and `CareersPageSource` (job source). The rules engine, dedup, rule proposer and synonym expansion are pure functions in `search/domain`, enforced by import-linter. One new module, `search`. W3 reuses the 001 runtime and adds no new infrastructure. | ✅ | ✅ |
| **VII. Permitted sources only** | Public ATS board APIs via allowlisted career-ops providers, with robots.txt checked per provider and Keka disabled until cleared (R2). Careers pages with robots.txt honoured, ≥ 2 s per host, a cache and an honest User-Agent (R3). Content the person pastes. Nothing from LinkedIn, Naukri, Indeed or Cutshort. Sources are isolated per company (FR-011). | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | The seed list has company columns only. Delete-all clears all search data and re-seeds (SC-013). Per-item delete (job, user company). career-ops runs from HireTitan's own data folder. Synthetic fixtures only. The compose image still works on all three OSes (Node is added to the runtime stage; checked by the compose-smoke CI job). | ✅ | ✅ |
| **Quality gates** | ruff, mypy --strict, import-linter, coverage, frontend gates, licence and vulnerability checks (now including the Node packages of career-ops). The prompt eval report goes in the PR. Per-story reviews: python/FastAPI, security (sources and injection), database, React. | ✅ | ✅ |

**Result**: passes with one new recorded deviation (D3, decided by Ravi on 2026-11-05) and D1 carried over from 001.

## Project Structure

### Documentation (this feature)

```text
specs/002-job-search/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── rest-api.md
│   └── job-search-workflow.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
Dockerfile                       # runtime stage gains Node 22 + career-ops v1.38.0 (pinned, no browser)
docker-compose.e2e.yml           # e2e: synthetic seed + fake career-ops + scripted LLM

backend/
├── seed/
│   ├── companies.yaml           # shipped list, company columns only (R10)
│   └── title_synonyms.yaml      # role synonyms for rule proposal and matching (R9)
├── alembic/versions/0012_out_of_credit.py, 0013_search.py
├── src/hiretitan/
│   ├── search/
│   │   ├── domain/              # SearchRules, rule proposer, apply_rules, dedup keys + fuzzy,
│   │   │                        #   location aliases, job state machine (pure)
│   │   ├── application/         # rules (propose/edit/approve), start/stop search, jobs (paste,
│   │   │                        #   restore, applied, delete, duplicates), companies (CRUD, CSV,
│   │   │                        #   discovery), seed loader, delete_all
│   │   ├── infra/               # SQLAlchemy models + repos, CareerOpsAdapter, CareersPageAdapter
│   │   │                        #   (robots, rate limit, cache, JSON-LD, heuristics)
│   │   ├── workflow/            # W3 job_search graph + nodes; W8 company discovery
│   │   └── api/                 # /search/*, /jobs/*, /companies/* routers
│   ├── platform/llm/            # out_of_credit mapping (R7); PAUSE_REASONS += out_of_credit
│   └── prompts/
│       ├── judge_relevance/v1/  # system.md, user.md.j2, schema.py, meta.yaml
│       └── extract_jobs_from_page/v1/   # US3
├── evals/judge_relevance/       # 2 profiles × 60 labelled synthetic postings + runner task
└── tests/
    ├── unit/search/ · integration/search/ · api/search/ · workflow/search/
    ├── contract/careerops/ · contract/careers_page/ · contract/openai/ (429 bodies)
    ├── security/test_job_text_attacks.py
    └── fixtures/companies/ · fixtures/careerops/ · fixtures/careers_pages/   # synthetic only

frontend/src/features/
├── explore/                     # home page Explore list, search button + live progress, summary
├── jobs/                        # job detail, paste form, applied list, duplicates
├── search-rules/                # proposal editor + approve
└── companies/                   # list, add + discovery confirm, check-manually, CSV import/export
frontend/e2e/job-search.spec.ts
```

**Structure Decision**: a new `search` feature module with the same layers as 001 (`domain → application → workflow → api`, `infra` beside them). It reads the confirmed profile and preferences only through `profile.application` and `preferences.application`. `setup` calls `search.application.delete_all()` and reads `search.application` for the checklist. The home route moves from `features/home` to `features/explore`, and the setup checklist component is reused at the top.

### Import-linter contracts (added or extended)

1. `search` follows the layer contract from 001.
2. `search.domain` must not import frameworks (as in 001's contract 2).
3. The modules `profile`, `preferences`, `setup` and `search` import each other only through `<module>.application`.
4. `platform` still imports no feature module.

## Delivery order (input for /speckit-tasks)

1. **Foundation**:
   - **Out of credit** in `platform/llm` (R7) with adapter contract tests. Also fixes 001's ingest.
   - Migrations `0012_out_of_credit`, `0013_search` and the `search` module skeleton plus import-linter.
   - Seed loader with the synthetic seed.
   - Runtime image with Node 22 + career-ops (pinned, version checked, no browser), `CareerOpsPort` + `FakeCareerOps`, and the recorded-output contract tests.
   - **Provider allowlist test** (R2), with Keka disabled.
2. **US2 (P1) Search rules**: `SearchRules` domain and limits, synonym table, deterministic proposer, apply_rules, the rules endpoints, the stale-rules check, and the editor UI.
3. **US1 (P1) Search now and Explore**:
   - normalize (untrusted pipeline), dedup (exact and fuzzy), the job state machine;
   - `judge_relevance` v1 prompt, eval set and runner task;
   - **eval run before activation (gate)**;
   - W3 batched workflow with stop, budget, out-of-credit and continuation;
   - the search endpoints and SSE events;
   - the Explore home page with live progress, the summary and skipped list, restore, and job detail;
   - the status checklist additions;
   - the injection test set.
4. **US5 (P2) I applied + Applied list**: endpoints, Applied page, undo.
5. **US4 (P2) Paste a job**: paste endpoint, dedup against existing jobs, form UI.
6. **US3 (P2) Companies**: list, hide and edit, user add with W8 discovery and confirm, `CareersPageSource` (robots, rate limit, cache, JSON-LD, heuristics) and `extract_jobs_from_page` v1 with its eval, the check-manually list, CSV import and export, and the real `companies.yaml` from Ravi's sheet (company columns only; maintainer resolution pass).
7. **Polish**: delete-all extension and test (SC-013); the Playwright journey (quickstart A); the SC-010 performance test with 1,000 jobs; docs (user guide: sources, rules, costs; `docs/CONTEXT.md`); ADR updates (W3 batching, relevance in the default search, which changes architecture §7 W3/W3b).

Each user story is reviewed (python/FastAPI, security, database, React reviewers) before it's marked done.

## Complexity Tracking

### Recorded deviations

| ID | Principle | Deviation | Justification | Closing condition |
|---|---|---|---|---|
| D1 (from 001) | IV, providers | Only the OpenAI adapter exists | Unchanged from 001 (ADR-02) | The other adapters land before the first public release. `judge_relevance` and `extract_jobs_from_page` evals must then run on each provider |
| D3 | IV, "Batch AI actions MUST show an estimated cost first" | The search shows the **actual cost so far, live per batch, with a Stop button**, instead of an upfront estimate and confirmation | Ravi, 2026-11-05 (clarification 4): the estimate is a guess, and the number of jobs is unknown until fetched. Batches make spend visible from the first batch, and the hard budget cap plus the stop on out-of-credit bound it. The research estimate is ≈ $0.08 per first search | Revisit when the constitution is next amended: either amend IV to allow "live cost with stop" for open-ended batch actions, or add an upfront estimate if real searches show it would be accurate |

### Notable additions

| Addition | Why needed | Simpler alternative rejected because |
|---|---|---|
| Node 22 + career-ops in the runtime image | R1: reuse mature public-board providers | Porting the providers to Python is a large job and loses upstream fixes |
| `CareerOpsPort` and `CareersPageSource` ports | Real external boundaries (CLI, job source), so contract tests and fakes are possible | Calling them inline would make workflow tests need the network |
| Batched W3 with a stored company cursor | Clarification 4: early results, a clean stop, continuation | One fan-out gives nothing until the end and cannot continue |
| Relevance AI in the default search (architecture had it optional, W3b) | Clarification 3: "we dont need irrelavant jobs" | Rules alone leave many unrelated jobs, or hide good ones with strict keywords |
| `relevance_decisions` history table instead of a column on `jobs` | Reasons for every decision, provenance for AI ones, restore and re-check history (FR-024, constitution IV) | A single column would lose the reason trail and the AI provenance |
| Tombstones for deleted built-in companies and deleted jobs | So the seed loader and later searches don't bring them back (FR-018, FR-041) | Hard delete would re-add them on the next seed or search |
