# Implementation Plan: Setup and search polish

**Branch**: `002i-setup-and-search-polish` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002i-setup-and-search-polish/spec.md`

## Summary

Six changes, shipped together. **US1**: finishing setup approves the first search rules automatically (and start-up does it for installs that finished setup without rules), so Explore is ready to search. **US2**: the Search panel shows a clear "searching" state with no "0 of 0" and no batch numbers. **US3**: the Search rules page is rewritten in plain language with a read view and an Edit / Save / Cancel flow. **US4**: the Preferences step of setup gets a wide card. **US5**: Explore rows expand in place and the title opens the posting. **US6**: Explore shows only jobs that fit: a description is read for each job the free rules kept, the rules gain an area of work with avoid words and a "stack named in the title" rule, the AI check gets the person's real skills, areas and recent titles, and a new relevance prompt v3 must pass its evaluation before it goes live.

Approach: one migration (`0020_first_rules`, an `approved_by` column), two new rules endpoints (`GET /search/rules/suggested`, `PUT /search/rules/approved`), a composition callback on `POST /onboarding/complete`, a start-up hook, a new description reader in `search/infra/descriptions/` behind a job-source port, two reviewed seed files (`work_areas.yaml`, `tech_names.yaml`), prompt `judge_relevance/v3`, and frontend rewrites of the Search panel, Search rules page and Explore rows. Design decisions are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5.9 strict (frontend, Node 22). No runtime image change.

**Primary Dependencies**: as today (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, LangGraph, httpx, protego; React 19, TanStack Query, React Router, Tailwind 4 + shadcn/ui). **None added.**

**Storage**: PostgreSQL 16, `app` schema. `search_rule_sets.approved_by` (new) and `areas` inside the `rules` JSON ([data-model.md](data-model.md)). Migration `0020_first_rules` (parent `0019_resume_picker`). Descriptions use the existing `jobs.description`, `skills_found`, `years_found`.

**Testing**: pytest + Testcontainers Postgres (first approval incl. a concurrent double finish, start-up hook, new endpoints, migration); pure unit tests for the area guess, avoid words and title stack rule; contract tests with synthetic recorded fixtures per description source and an allowlist test that intercepts requests; workflow tests with the fake description reader and the scripted fake LLM (no LLM call during first approval, the card holds profile skills, an unreadable description is told to the AI); `judge_relevance` eval v3 (needs Ravi's key); Vitest + Testing Library for the panel, rules page, Explore rows and setup width; the Playwright setup journey (Finish setup → Search now) and job-search journey (searching state, Explore row expand, area and stack skips). Test names follow the matrix in [contracts/rest-api.md](contracts/rest-api.md).

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA). Worker change: the W3 search graph and the `recheck_job` workflow read descriptions before the AI check.

**Performance Goals**: description reads only for jobs the free rules kept (tens per search, not hundreds), 20 s timeout each, spaced per host by the existing fetcher; the panel keeps polling as today. Explore list query unchanged (details load on expand).

**Constraints**:
- No outbound action (constitution I); the description reader only `GET`s public endpoints and is covered by the no-send scan.
- Every description is untrusted text: sanitised, screened, capped, delimited (constitution III).
- Prompt v3 becomes active only after its evaluation report passes and is committed (constitution IV).
- `setup` may not import `search`; the first approval runs through a callback from the composition root.
- No AI cost shown anywhere; English only; flat navy and orange theme; do not run prettier on existing frontend files (use `--no-semi --single-quote --print-width 100` on new files only); run `npm run build` before pushing.

**Scale/Scope**: 1 migration, 2 new endpoints, 1 changed endpoint behaviour, 1 start-up hook, 1 new infra package with 6 source readers, 2 seed files, 1 new prompt version and ~40 new eval cases, 4 frontend areas rewritten (Search panel, Search rules page, Explore rows, setup layout), 2 Playwright journeys extended.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | The first rules come from the deterministic proposer, not an AI, and are shown and editable on the Search rules page at any time (FR-020 says they were set up automatically); every later change needs the person's Save. New skips (area avoid words, stack in title, stricter AI) record a visible reason and stay restorable (FR-036). The description reader only reads public endpoints; the no-send architecture test scans the new package. | ✅ | ✅ |
| **II. Truthful profile** | The profile is read, never changed. The AI card now carries the profile's own skills and job titles (fixing the empty-skills bug); nothing is invented. | ✅ | ✅ |
| **III. Untrusted input is data** | Descriptions go through the same sanitise + screen + cap path as other job text, injection signals are stored and shown, and only the 1,200-character excerpt reaches the AI inside the untrusted data block. A security test feeds attack text through the description path. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | New prompt version `judge_relevance/v3` with the same schema and checks; the eval set grows with the new cases; v3 is made active only after the report passes (SC-008 rows included) and is committed with the PR. No cost figures. | ✅ | ✅ |
| **V. Test-first** | Tests first, named after FR/US/SC ids; real Postgres for persistence and the advisory-lock concurrency; fakes only for the description sources (a job source boundary) and the LLM; contract tests with recorded synthetic fixtures for each description source. | ✅ | ✅ |
| **VI. Lean architecture** | One new port (`DescriptionPort`) at a real boundary (job sources). One callback on the onboarding deps to respect the setup/search boundary. Domain rules (`tech_names.py`, area guess) are pure and covered by the domain import-linter contract. Recorded in Complexity Tracking. | ✅ | ✅ |
| **VII. Permitted sources only** | Descriptions are read only from the public ATS APIs HireTitan already uses for listings and from companies' own posting pages, through an allowlist (vendor APIs, robots.txt checks dated) and the careers-page fetcher (robots.txt, spacing, cache). No new kind of source. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Seed files are generic (areas and technology names), no personal data. Descriptions are stored with jobs as today and go with Delete all. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter, coverage gate, frontend gates incl. `npm run build`, licence and vulnerability checks, Playwright. Reviews per story: Python/FastAPI, database (US1), security (US6), React (US2-US5). Eval report for v3 in the PR. | ✅ | ✅ |

**Result**: passes; the justified items are below.

**Amendments recorded by this feature** (dated change notes written during implementation, FR-024): `docs/clarified-requirements.md` §3 (first rules approved automatically); `specs/002-job-search/spec.md` FR-002 (source no longer shown), FR-004 (first approval automatic), FR-005 (effect shown per group; avoid words proposed from the area), FR-006 (unchanged behaviour, note only).

## Project Structure

### Documentation (this feature)

```text
specs/002i-setup-and-search-polish/
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
├── alembic/versions/0020_first_rules.py          # search_rule_sets.approved_by + backfill
├── seed/work_areas.yaml                          # areas: signals, avoid_in_titles, compatible
├── seed/tech_names.yaml                          # languages and frameworks with aliases
├── src/hiretitan/
│   ├── api_main.py                               # start-up approve_first_rules; on_completed wiring
│   ├── search_wiring.py                          # approve_first_rules callback; profile card with
│   │                                             # profile skills, areas, recent titles (bug fix)
│   ├── setup/api/onboarding.py                   # OnboardingApiDeps.on_completed callback
│   ├── prompts/judge_relevance/v3/               # system.md, user.md.j2, schema.py, checks.py, meta.yaml
│   └── search/
│       ├── domain/rules.py                       # SearchRules.areas + validation
│       ├── domain/rules_serialization.py         # areas in and out
│       ├── domain/work_areas.py                  # area guess + avoid words (pure)
│       ├── domain/tech_names.py                  # names in a title; stack rule (pure)
│       ├── domain/proposer.py                    # areas and avoid words in proposals
│       ├── domain/apply_rules.py                 # stack-in-title skip with reason
│       ├── domain/cards.py                       # ProfileCard / JobCardInput fields
│       ├── application/ports.py                  # DescriptionPort
│       ├── application/rules.py                  # approve_first_rules, save_approved, suggested
│       ├── infra/models.py                       # SearchRuleSetRow.approved_by
│       ├── infra/repos.py                        # rule-set repo: ever_approved, write approved
│       ├── infra/descriptions/                   # reader.py, vendors.py, page.py, allowlist.py, fake.py
│       ├── workflow/graph.py                     # read descriptions between rules and judge
│       ├── workflow/judge.py                     # description_status on the card
│       ├── workflow/recheck.py                   # read description before re-judging
│       └── api/rules.py                          # GET suggested, PUT approved, approved_by out
├── evals/judge_relevance/cases.py                # back-end Python/Go profile + ~40 postings
└── tests/
    ├── unit/search/                              # work areas, tech names, proposer, cards
    ├── integration/search/                       # first approval (+ concurrency), save approved, 0020
    ├── api/search/test_rules_api.py              # suggested, approved
    ├── api/setup/                                # finish setup approves first rules
    ├── contract/descriptions/                    # one recorded synthetic fixture per source + allowlist
    ├── workflow/search/                          # descriptions before judge, recheck, card contents
    └── security/                                 # description text attacks

frontend/src/
├── features/explore/SearchPanel.tsx              # searching state, one progress line, no batches
├── features/explore/SearchingIndicator.tsx       # moving bar (static under reduced motion)
├── features/explore/ExplorePage.tsx              # expandable JobRow; title opens the posting;
│                                                 # empty state names the missing step with a link
├── features/jobs/JobDetails.tsx                  # shared details (row and job page)
├── features/jobs/JobDetailPage.tsx               # uses JobDetails
├── features/search-rules/SearchRulesPage.tsx     # read view, edit view, Save / Cancel, groups,
│                                                 # Update from my profile, Start over, leave guard
├── features/setup/SetupLayout.tsx                # width narrow | wide
├── features/setup/PreferencesStep.tsx, ReviewStep # wide
└── theme/theme.css                               # .ht-searching (+ reduced motion)
frontend/e2e/setup-and-profile.spec.ts            # Finish setup → Search now (no Search rules visit)
frontend/e2e/job-search.spec.ts                   # searching state, row expand, area and stack skips
```

**Structure Decision**: extend the existing `search` and `setup` modules; one new infra package (`search/infra/descriptions/`) because reading a posting is a job-source boundary with its own fixtures and allowlist. The cross-module need (approve rules when setup finishes) goes through a callback wired in the composition root, like `SetupFacts`.

## Phases (for /speckit-tasks)

1. **Setup**: baseline gates; migration `0020`; seed files and their loaders.
2. **US1** (P1): first approval use case, callback, start-up hook, Explore empty-state links.
3. **US2** (P1): Search panel and indicator.
4. **US6** (P1): stack rule, areas and avoid words, profile card fix, description reader (fake first, then each source with its fixture), workflow wiring, prompt v3 and eval cases, eval run (Ravi's key) before v3 is made active.
5. **US3** (P2): rules endpoints and the page rewrite (depends on `areas` from US6 for the groups).
6. **US5** (P2): `JobDetails` extraction and Explore rows.
7. **US4** (P3): setup width.
8. **Polish**: docs and change notes (FR-024), journeys, success-criteria map, gates, final reviews.

Review pause after every phase (Ravi's standing rule).

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| `DescriptionPort` and `search/infra/descriptions/` with per-vendor readers | Jobs reach the AI check with no text today, so relevance is decided on titles (US6 findings). The vendors' public JSON endpoints are the reliable source; Workday and Ashby pages have no text without a browser. | Patching career-ops' providers (upstream, pinned, not patched by HireTitan); a headless browser (heavy image, slow); page reads only (empty for JavaScript-rendered boards, SC-009 would fail). |
| `OnboardingApiDeps.on_completed` callback | `setup` must trigger a `search` use case without importing it (import-linter boundary). | Calling search from setup (breaks the boundary); a frontend follow-up call (leaves the dead end when it fails or an old tab finishes setup). |
| Start-up hook for the first approval | Installs that finished setup before this feature (Ravi's) must get rules without the person doing anything, and a `GET` must not write. | Approving inside `GET /status` (a read that writes). |
| Two reviewed seed files | Area avoid words and technology names must be deterministic, explainable and reviewable, like `title_synonyms.yaml`. | Asking the AI (adds calls, a prompt gate and cost to setup and to every search). |
