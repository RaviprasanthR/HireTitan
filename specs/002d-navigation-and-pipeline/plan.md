# Implementation Plan: Navigation and pipeline

**Branch**: `002d-navigation-and-pipeline` | **Date**: 2026-11-11 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002d-navigation-and-pipeline/spec.md` (1 clarification, 2026-11-11)

## Summary

Five things, all on code that 001, 002 and 002b already built:

- **Home with two tabs.** `/` is Explore (unchanged content) and `/pipeline` is In pipeline: one table of applied and inquired jobs (the 002 Applied table, generalised). The Applied page and route go; `/applied` redirects.
- **Inquired.** A fifth job state, `inquired`, with its own date column and the same rules and Undo as applied. `explore|skipped → inquired → applied`; inquired and applied both mean "in the pipeline". Searches already keep a job's state when they meet it again, so inquired jobs are left alone with no search change. The Companies list's `has_application` becomes `pipeline: "applied" | "inquired" | null`.
- **No AI cost (constitution 2.0.0).** Remove the budget guard, the price table and cost calculator, the `tiktoken` dependency, the settings budget, the `budget_reached` pause and search stop, cost columns on AI calls and search runs, the settings API, and every cost display. The provider's out-of-credit pause stays exactly as it is. Runs paused for the budget are failed with a clear message by the migration.
- **Navigation.** The sidebar becomes Home, Companies, Profile, Settings. Profile gets tabs (`/profile`, `/profile/preferences`, `/profile/search-rules`); old addresses redirect. Review leaves the menu and becomes a count notice on Home. Settings shows only the key status and Delete all.

- **A calmer, flat look** (User Story 6, Ravi's mockup, 2026-11-12): one flat dark navy theme with an orange accent and no gradients; an icon sidebar with a right divider and a logo block; Companies rows as lines with a second line, a soft see-through rust hover and coloured action icons; slate chip buttons. Theme tokens change in `tokens.ts` and `theme.css`; the contrast test checks them.

Design decisions are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22).

**Primary Dependencies**: unchanged, minus **`tiktoken`** (only the budget guard used it; removing it also removes the one-off download of `o200k_base` from a host outside the outbound allowlist, an open item since 001).

**Storage**: PostgreSQL 16, `app` schema. Two migrations ([data-model.md](data-model.md)): `0016_inquired` (`jobs` gains `inquired_on` and the `inquired` state) early, and `0017_no_cost` after the code no longer uses cost (`settings.budget_cap_usd`, `llm_calls.cost_usd` and `estimated_cost_usd`, and `search_runs.ai_cost_usd` are dropped; runs paused for `budget_reached` become `failed`; the pause-reason check loses `budget_reached`).

**Testing**: pytest + Testcontainers Postgres (state machine, mark and undo, pipeline list, migration up and down with a budget-paused run, company pipeline flag); a scan test that no API response or page carries a cost field; Vitest + Testing Library (tabs, inquired button, redirects, menu, review notice, settings); the Playwright journeys updated (no cost, new menu) plus a pipeline step.

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA). No new workflow; the search and profile workflows lose their budget branches.

**Performance Goals**: the In pipeline list is one keyset-paged query like the Applied list today; the Companies list stays at a fixed number of queries.

**Constraints**: no cost anywhere (constitution IV, 2.0.0); never send anything (I); old addresses keep working.

**Scale/Scope**: about 30 backend files touched for the cost removal (listed in research R5), two endpoints and one list value for inquired and pipeline, about 15 frontend files.

## Constitution Check

*GATE: passed before Phase 0 and re-checked after Phase 1.*

| Principle | How this plan complies |
|---|---|
| **I. No outbound actions** | "I inquired" is a note the person makes; nothing is sent. The no-send architecture test stays green. |
| **II. Truthful profile** | Not affected. |
| **III. Untrusted input is data** | Not affected. |
| **IV. Validated, versioned AI (2.0.0)** | This feature *is* the compliance work: no estimate, display or cap of cost; calls logged with provider, model, tokens, latency, outcome; out-of-credit pause unchanged. Until US3 is done the existing code still breaks IV; that temporary deviation is recorded in Complexity Tracking. |
| **V. Test-first** | Every task lists its tests first; the migration has an up/down test with a budget-paused run; real Postgres. |
| **VI. Lean architecture** | Removes a wrapper (budget guard), a dependency and an API; adds one column and one state. No new port or module. |
| **VII. Permitted sources** | Not affected. |
| **VIII. Privacy and portability** | Delete all still wipes everything (inquired marks go with the jobs). |

One temporary deviation, recorded in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002d-navigation-and-pipeline/
├── spec.md
├── plan.md              # this file
├── research.md          # R1-R9
├── data-model.md        # state machine, migration 0016
├── quickstart.md        # how to validate by hand
├── contracts/rest-api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0016_inquired.py, 0017_no_cost.py   # new
└── src/hiretitan/
    ├── platform/llm/
    │   ├── budget.py                # removed
    │   ├── models.py, models.yaml   # tiers only; prices and cost calculator removed
    │   └── factory.py, port.py, validation.py, infra/   # no guard, no cost fields, no budget outcome
    ├── platform/runtime/            # PauseReason.budget_reached removed; resume_paused simplified
    ├── setup/                       # settings API removed; status without budget; budget repo methods removed
    ├── search/
    │   ├── domain/job_state.py      # + inquired
    │   ├── application/applied.py → pipeline.py   # mark/undo applied and inquired
    │   ├── workflow/                # stops, graph, judge, pages: no budget stop, no cost delta
    │   ├── infra/                   # repos: pipeline page, company pipeline flag; search_store: no cost
    │   └── api/                     # jobs: list=pipeline, inquired endpoints; companies: pipeline flag;
    │                                # duplicates: merge keeps the stronger pipeline state; runs: no cost
    └── worker_main.py               # no budget provider
backend/evals/                       # no cost estimate or cost columns; token counts stay
frontend/src/
├── app/routes.tsx, Shell.tsx        # 4 menu entries, redirects, /pipeline, profile tabs
├── features/explore/                # HomeTabs; PipelinePage (from AppliedPage); no cost in search panel,
│                                    # summary, history
├── features/jobs/                   # I inquired next to I applied; undo store generalised
├── features/profile/                # ProfileTabs hosting Preferences and Search rules
├── features/companies/              # Applied / Inquired chip, In pipeline filter and sort
├── features/home/                   # review notice
├── features/settings/               # key status + delete all only
└── features/setup/                  # no budget wording
frontend/e2e/                        # journeys follow the new menu; pipeline step
```

**Structure Decision**: same web-application layout as 001-002b. `AppliedPage` becomes `PipelinePage`; `PreferencesPage` and `SearchRulesPage` keep their components and are shown inside the Profile tabs.

## Complexity Tracking

| Deviation | Why it is needed | Simpler alternative rejected because |
|---|---|---|
| Constitution IV (2.0.0) is not yet met on this branch: the budget guard, budget pause, cost columns and cost displays from 001 and 002 stay in the code until US3 (T017 to T022) removes them; the feature is not merged until they are gone | US1 and US2 are the MVP and are reviewed first; the cost code is removed from the outside in so every task stays green | Removing all cost code in one task first would be one very large commit across about 30 files with no green steps in between |
