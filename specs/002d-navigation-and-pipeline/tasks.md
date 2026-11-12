---
description: "Task list for 002d-navigation-and-pipeline"
---

# Tasks: Navigation and pipeline

**Input**: Design documents from `specs/002d-navigation-and-pipeline/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md).

**Tests**: **Mandatory** (constitution V). Every task is one red → green → refactor cycle and **one commit**: write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, and keep the whole suite green. Tests that guarded removed behaviour (budget, cost) are deleted in the same task that removes the behaviour.

**Organization**: grouped by user story. Order: Foundational, then US6 (the new look, so later screens are built in it), then US1, US2, US3 (P1), then US4, US5 (P2), then Polish. Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US6 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `backend/src/hiretitan/…` (shortened to the module below), `backend/tests/…`, `frontend/src/…`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`, never `prettier --write` on whole existing files without checking the diff.

---

## Phase 1: Setup

**Purpose**: a known-green baseline before anything changes.

- [x] T001 Record the baseline on branch `002d-navigation-and-pipeline` (cut from `master` at `e6b1af2`): run the backend suite, `ruff`, `mypy --strict`, `lint-imports`, and the frontend `tsc`, `eslint`, `npm test`; write the counts into `docs/CONTEXT.md` under the 002d entry. No code change.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the `inquired` state and its date, used by US1 and US2.

- [x] T002 [P] Add `inquired` to `JobState` in `search/domain/job_state.py` with the transitions from data-model.md: explore → inquired, skipped → inquired, inquired → applied, inquired → explore (Undo), inquired → deleted; **applied → inquired is not allowed**. `JobStatus` gains `inquired_on: date | None`; `transition(…, inquired_on=…)` requires a date for `inquired` ("Say when you inquired."). Test first in `backend/tests/unit/search/test_job_state.py`: `test_US2_AS1_explore_and_skipped_can_become_inquired`, `test_US2_AS2_inquired_can_become_applied`, `test_FR007_applied_cannot_become_inquired`, `test_US2_AS3_undo_inquired_returns_to_explore`, `test_inquired_needs_a_date`.
- [x] T003 Migration `backend/alembic/versions/0016_inquired.py` and `JobRow` in `search/infra/models.py`: add `inquired_on date NULL`; widen the state check to include `'inquired'`; add check `inquired_on_iff_inquired`: `(state = 'inquired') = (inquired_on IS NOT NULL)`. Downgrade moves `inquired` jobs back to `explore`, then drops the column and check and narrows the state check. Test first in `backend/tests/integration/platform/test_migrations.py`: `test_0016_inquired_up_down`; in `backend/tests/integration/search/test_schema.py`: `test_inquired_on_iff_inquired`; the 001 model/migration drift test must stay green.
- [x] T004 `JobsRepo.set_status(job_id, state, applied_on, inquired_on)` in `search/infra/repos.py` writes both dates (clearing the one that does not belong to the new state); `JobCardOut` and `JobDetailOut` in `search/api/models.py` gain `inquired_on: date | None`. Test first in `backend/tests/integration/search/test_repos.py`: `test_set_status_inquired_then_applied_clears_inquired_on`; in `backend/tests/api/search/test_jobs_api.py`: `test_job_card_has_inquired_on`; in `backend/tests/api/setup/test_delete_all_api.py`: `test_delete_all_removes_inquired_jobs` (edge case).

**Checkpoint**: backend knows `inquired`; nothing in the UI changes yet.

---

## Phase 3: User Story 6 - A calmer, flat look (Priority: P2)

**Goal**: one flat dark navy theme with an orange accent, an icon sidebar (no logo; the name is plain text), and the Companies list as lines (Ravi's mockup, 2026-11-12). Done first among the stories so every later screen is built in the new look. The previewed changes are in `git stash` "002d US6 theme preview"; reuse them, then apply the two adjustments below.

**Independent Test**: any page is flat navy with orange as the only accent; the sidebar has icons and a right divider, and no logo; Companies rows are lines with a second line, a soft rust hover and coloured action icons; toolbar buttons are slate chips with icons; the contrast test passes.

- [x] T005 [US6] Theme tokens in `frontend/src/theme/tokens.ts` and `frontend/src/theme/theme.css` (keep them in step): page `#131a24`, panels and sidebar `#18202b`, divider `#2a3444`, decoration `#3a465a`, muted text `#8c97a9`, text `#e3e7ee`, headings `#f1f3f7`, accent and text on primary `#f0a35e`, primary fills `#243044`; all gradients become flat colours; shadows become a hairline border (`rgb(255 255 255 / 0.07)`), no glow; success, warning and danger unchanged. Update `docs/architecture.md` §10's colour table. Test first in `frontend/src/theme/contrast.test.ts`: `FR021 every text colour reaches 4.5 to 1 on the page and panels`, `FR021 the accent on primary fills reaches 4.5 to 1`, `SC007 no gradient in the theme` (reads `theme.css`).
- [x] T006 [US6] Sidebar and no logo: `frontend/src/components/AppName.tsx` shows the name HireTitan as plain text (`Logo.tsx`, the bolt mark, `frontend/public/favicon.svg`, `docs/assets/logo.svg`, the README logo line and the `logo` colour token are all removed; `index.html` has an empty tab icon); `frontend/src/app/Shell.tsx` shows an outline icon (lucide) before each menu item, the active item with the primary fill and accent text, a thin right divider (`border-r`) and the name at the top; the setup header in `frontend/src/features/setup/SetupLayout.tsx` shows the name too. Tests in `Shell.test.tsx`: `FR022 every menu item has an outline icon`, `FR022 the app name is plain text at the top of the sidebar, with no logo`, `FR022 the sidebar has a thin divider on its right edge`; in `AppName.test.tsx`: `shows the app name once, as plain text`, `has no logo or other graphic`, `the tab has no logo icon either`.
- [x] T007 [US6] Companies rows in `frontend/src/features/companies/CompaniesPage.tsx`: each row a plain line with a bottom divider (no card); the website host as a smaller muted second line under the name (only when there is a website); a plain title-case header with a bottom divider; hover tint **soft and see-through: the rust `#9c4f37` at about 25% opacity** (`hover:bg-[#9c4f37]/25`); the action icons keep **their earlier colours**: details slate-300, website orange-300, careers page violet-300, hide yellow-300, edit emerald-300, delete rose-300. Test first in `CompaniesPage.test.tsx`: `FR023 the website is a second line under the name`, `FR023 no second line without a website`, `FR024 action icons keep their own colours` (class check per action), `FR024 the row hover tint is see-through`.
- [x] T008 [US6] Toolbar chips in `frontend/src/features/companies/CompaniesPage.tsx` (and the shared button style if needed): Show (the filter, eye icon), Import / export (upload icon), Check manually (check icon) and Add a company (plus icon) are filled slate chips (`bg-[#243044]`, orange text and icon, hover a little lighter); the All companies / Check manually tabs keep a clear selected state. Test first in `CompaniesPage.test.tsx`: `FR025 toolbar buttons have icons`, `FR025 check manually is selectable`.
- [x] T008a [US6] Ravi's change, 2026-11-12: the Companies page has no import or export. Removed the Import / export button, `ImportExport` and `SheetImportDialog`, the endpoints `GET /companies/export`, `POST /companies/import`, `POST /companies/sheet-import` (and their confirm calls), the use cases and domain code behind them (`companies_csv`, `sheet_import`, `sheet`, `contacts_cell`, `company_match`, `add_company_from_import`, the `list_all` of contacts and notes), their tests and fixtures, the import-linter, no-send and privacy-test entries, the e2e steps, and the user guide sections; `openapi.json` and `schema.d.ts` regenerated.
- [x] T008b [US6] Ravi's changes, 2026-11-12, after reviewing Phase 3: company rows have curved corners (hover tint follows them, the divider stays straight); **Add a company** replaces the table with its form instead of opening above it; the All companies and Check manually tabs and the Show filter are removed (the table, the search box and the header sort remain; the backend `filter` parameter is left as it is).

**Checkpoint**: Ravi reviews the new look before the story work continues.

---

## Phase 4: User Story 1 - One home for new jobs and my pipeline (Priority: P1) 🎯 MVP

**Goal**: Home has Explore and In pipeline tabs; In pipeline lists applied and inquired jobs; the Applied page is gone.

**Independent Test**: with jobs in Explore and jobs marked applied, `/` shows Explore with the search panel; `/pipeline` shows the table of applied jobs; `/applied` lands on `/pipeline`.

- [ ] T009 [US1] Backend: `GET /jobs?list=pipeline` in `search/api/jobs.py` and `JobsRepo.page` (`search/infra/repos.py`) returns jobs with `state IN ('applied', 'inquired')`, ordered by `coalesce(applied_on, inquired_on) DESC, id`, keyset-paged; `list=applied` is replaced. Test first in `backend/tests/api/search/test_pipeline_api.py`: `test_US1_AS2_pipeline_lists_applied_and_inquired_newest_first`, `test_pipeline_pages_with_a_cursor`; update `backend/tests/api/search/test_applied_api.py` callers of `list=applied`.
- [ ] T010 [US1] Frontend Home tabs: `frontend/src/features/explore/HomeTabs.tsx` (tab bar "Explore" and "In pipeline", links to `/` and `/pipeline`, `aria-current` on the active one); `ExplorePage` renders it above its list; new `frontend/src/features/explore/PipelinePage.tsx` built from `features/jobs/AppliedPage.tsx` (columns company, role, date, status Applied or Inquired, source; rows expand to description and sources and link to the job page; empty state "Nothing in your pipeline yet. Mark a job as applied or inquired in Explore."), using `list=pipeline`; routes in `frontend/src/app/routes.tsx`: `/pipeline`, and `/applied` → `<Navigate to="/pipeline" replace />`; remove the Applied page, its route and its menu entry in `frontend/src/app/Shell.tsx`; regenerate `frontend/src/api/schema.d.ts`. Test first: `US1 AS1 explore is the default tab`, `US1 AS2 pipeline lists applied and inquired`, `US1 AS3 the tab is in the address`, `US1 AS4 applied link opens the pipeline tab`, `US1 AS5 empty pipeline message`; update `Shell.test.tsx` and the moved Applied tests.

**Checkpoint**: Ravi reviews; In pipeline shows applied jobs (inquired arrive with US2).

---

## Phase 5: User Story 2 - Mark a job as inquired (Priority: P1)

**Goal**: I inquired next to I applied, with Undo; inquired jobs are in the pipeline, kept by searches, shown on Companies.

**Independent Test**: mark an Explore job inquired, see it in In pipeline as Inquired; mark it applied; undo returns it to Explore; a later search leaves an inquired job alone; its company shows Inquired.

- [ ] T011 [US2] Use cases in `search/application/pipeline.py` (move `mark_applied`, `undo_applied`, `check_applied_date` here from `application/applied.py`, rename the date check `check_pipeline_date`) plus `mark_inquired` and `undo_inquired`: default date the server's today, **"not in the future, not more than two years ago"**; `mark_applied` also accepts an `inquired` job. Endpoints in `search/api/jobs.py`: `POST /jobs/{id}/inquired` (`{inquired_on?}`; `422` field `inquired_on`; `409 already_inquired`; `409 already_applied`) and `DELETE /jobs/{id}/inquired` (`409 not_inquired`). Test first in `backend/tests/api/search/test_pipeline_api.py`: `test_US2_AS1_mark_inquired_defaults_to_today`, `test_US2_AS5_inquired_date_rules`, `test_US2_AS3_undo_inquired`, `test_FR007_applied_job_cannot_be_inquired_409`, `test_US2_AS2_inquired_then_applied`, `test_skipped_job_can_be_inquired`, `test_undo_applied_after_inquired_returns_to_explore` (edge case: it does not restore the inquiry).
- [ ] T012 [P] [US2] Prove searches leave inquired jobs alone (no code change expected; fix if the test finds one). Test in `backend/tests/workflow/search/test_inquired_kept.py`: `test_SC006_search_again_keeps_inquired_jobs` (a job marked inquired, the same posting found by a second search: state and `inquired_on` unchanged, not in Explore).
- [ ] T013 [P] [US2] Duplicates merge keeps the stronger state (research R9) in `search/api/duplicates.py`: the kept job takes `applied` > `inquired` > its own state, with that job's date. Test first in `backend/tests/api/search/test_duplicates_api.py`: `test_R9_merge_keeps_the_stronger_pipeline_state` (loser applied, kept explore → kept becomes applied with the loser's `applied_on`; loser inquired likewise).
- [ ] T014 [P] [US2] Companies pipeline flag: replace `has_application: bool` with `pipeline: "applied" | "inquired" | null` in `search/application/companies.py` and `search/api/companies.py`; `AppliedCompaniesRepo` → `PipelineCompaniesRepo.states()` in `search/infra/repos.py` (one query: `applied` if any job is applied, else `inquired` if any is inquired). Test first in `backend/tests/api/search/test_companies_api.py`: `test_FR009_company_pipeline_is_applied_inquired_or_null` (replaces the two `has_application` tests); keep `test_companies_list_runs_a_fixed_number_of_queries` green.
- [ ] T015 [US2] Frontend mark controls: `features/jobs/AppliedControl.tsx` → `PipelineControl.tsx` with **I applied** and **I inquired** (each with the editable date, today by default; I inquired hidden when the job is applied or inquired; I applied shown for inquired jobs); `appliedApi.ts` → `pipelineApi.ts`; `appliedStore.ts` and `UndoToast.tsx` generalised to either mark ("Marked as inquired. Undo"); used on Explore cards and `JobDetailPage.tsx`. Test first: `US2 AS1 I inquired moves the job to the pipeline`, `US2 AS2 inquired job can be marked applied`, `US2 AS3 undo inquired`, `FR007 no I inquired on an applied job`, `US2 AS5 date error shown`.
- [ ] T016 [P] [US2] Frontend Companies: in `features/companies/CompaniesPage.tsx` the chip shows **Applied** or **Inquired** (distinct colours), the Show option "Has an application" becomes **In pipeline**, the header sort orders Applied, Inquired, then the rest; details row says "You have applied to a job here" / "You have asked about a job here" / "Nothing in your pipeline here". Test first in `CompaniesPage.test.tsx`: `FR009 inquired chip`, `FR009 applied wins over inquired`, `FR009 in pipeline filter`, `FR009 sort applied then inquired`.

**Checkpoint**: Ravi reviews the inquired flow end to end.

---

## Phase 6: User Story 3 - No AI cost anywhere (Priority: P1)

**Goal**: nothing estimates, shows or caps AI cost; out-of-credit still pauses and resumes (constitution IV, 2.0.0). Removed from the outside in so every task stays green.

**Independent Test**: run a search with the AI on: no cost anywhere; Settings has no budget; an out-of-credit answer pauses and Check again resumes; the API schema has no cost, budget or spend field.

- [ ] T017 [US3] Frontend: remove cost and budget from `features/explore/SearchPanel.tsx`, `RunSummaryPage.tsx`, `SearchHistoryPage.tsx`, `features/profile/ProfilePage.tsx`, `features/setup/SetupGate.tsx`, `features/setup/SetupLayout.tsx`, `api/useStatus.ts`, `features/explore/api.ts`; Settings (`features/settings/SettingsPage.tsx`) keeps only the AI key status with Check again and Delete all my data (FR-020, a US5 requirement delivered here because the budget section goes) and reads the key status from `GET /status`, no longer from `GET /settings` (removed in T018); fixtures in `test/api.ts`. A search that ended with the old `budget_reached` outcome shows "Stopped". Test first: `SC003 no cost text on the search panel, summary, history, profile and setup pages`, `FR020 settings shows key status and delete all only`; update the affected tests (`SearchPanel`, `RunSummaryPage`, `SearchHistoryPage`, `SettingsPage`, `SetupGate`, `ResumeStep`, `HomePage`, `AiBanner`, `ReviewPage`).
- [ ] T018 [US3] Backend API: remove `ai_cost_usd` from the search runs API (`search/api/runs.py`) and the `search.batch_done` event, `budget` from `GET /status` (`setup/application/status.py`, `setup/api/status.py`), the whole `/settings` router (`setup/api/settings.py`, `setup/application/settings.py`, its wiring in `api_main.py`), and the budget target in `setup/application/review_items.py`; regenerate `backend/openapi.json` and `frontend/src/api/schema.d.ts`. Test first in `backend/tests/architecture/test_no_cost_fields.py`: `test_SC003_no_cost_budget_or_spend_field_in_the_api` (scans `openapi.json` for property names containing `cost`, `budget`, `spend` or `price`); delete `backend/tests/api/setup/test_settings_api.py`; update `test_status_api.py`, `test_runs_api.py`, `test_review_items_api.py`.
- [ ] T019 [US3] Workflows: remove the `budget_reached` stop and the per-batch cost delta from `search/workflow/stops.py`, `graph.py`, `judge.py`, `pages.py`, `recheck.py`, `search/application/search.py`, `search/infra/search_store.py`; remove the budget pause path in profile ingest. Test first in `backend/tests/workflow/search/test_stops.py`: `test_FR012_out_of_credit_still_pauses_and_resumes`, `test_SC004_no_budget_stop_however_much_was_used`; delete `backend/tests/workflow/search/test_cost.py`; update `test_search_usecases.py`, `test_profile_ingest_ai_unavailable.py`.
- [ ] T020 [US3] Platform: delete `platform/llm/budget.py`; remove prices, `prices_checked_on` and the cost calculator from `platform/llm/models.py` and `models.yaml` (tiers stay); remove `cost_usd` from `Usage` (`port.py`), `budget_blocked` from the outcomes new calls can have, cost fields from `validation.py`, `infra/calls_repo.py` (and `spent_in_month`) and `LlmCallRow`; `budget_reached` from `PauseReason` and `PAUSE_REASONS`; the budget branch of `platform/runtime/resume_paused.py`; the guard from `platform/llm/factory.py`; `budget_cap_provider` from `worker_main.py` and `setup/infra/settings_repo.py`; remove `tiktoken` from `backend/pyproject.toml` and the lockfile; ORM models stop mapping the cost and budget columns. Test first in `backend/tests/architecture/test_no_cost_fields.py`: `test_FR011_no_budget_guard_in_the_llm_stack` (no `BudgetGuard`, no `budget` module, no `tiktoken` import); `test_FR013_calls_are_logged_without_cost`; delete `backend/tests/integration/platform/llm/test_budget.py`; update `test_calls_repo.py`, `test_factory.py`, `test_runs_repo.py`, `test_run_state.py`, `test_resume_paused.py`, `test_runner.py`, `test_settings_repo.py`, `test_openai_adapter.py`, `test_delete_all_api.py`.
- [ ] T021 [US3] Migration `backend/alembic/versions/0017_no_cost.py`: runs with `status = 'paused' AND pause_reason = 'budget_reached'` become `status = 'failed'`, `pause_reason = NULL`, `error = 'Paused by the old AI budget, which HireTitan no longer has. Start it again.'`; the pause-reason check drops `budget_reached`; drop `settings.budget_cap_usd` (and check `budget_cap_non_negative`), `llm_calls.cost_usd`, `llm_calls.estimated_cost_usd`, `search_runs.ai_cost_usd`; the `llm_calls.outcome` and `search_runs.outcome` checks keep their legacy values. Downgrade per data-model.md. Test first in `backend/tests/integration/platform/test_migrations.py`: `test_FR014_0017_budget_paused_runs_become_failed`, `test_0017_no_cost_up_down`; drift test green.
- [ ] T022 [P] [US3] Evals: no cost estimate before a run and no cost columns in new reports in `backend/evals/run.py`, `judge_relevance/runner.py`, `extract_jobs_from_page/runner.py`, `extract_profile/…`; the `--yes` guard stays ("This run uses your AI credit."); token counts stay; `tests/unit/evals/test_default_model.py` keeps its quality checks and drops any cost comparison; committed old reports are left as they are. Test first in `backend/tests/unit/evals/test_eval_runner.py`: `test_FR015_report_has_tokens_and_no_cost`, `test_run_still_needs_yes`.

**Checkpoint**: Ravi reviews; the constitution check for IV holds in code.

---

## Phase 7: User Story 4 - Profile holds my preferences and search rules (Priority: P2)

**Goal**: Profile has three tabs; old addresses redirect.

**Independent Test**: `/profile/preferences` and `/profile/search-rules` work like the old pages; `/preferences` and `/search/rules` land on them.

- [ ] T023 [US4] Frontend: `frontend/src/features/profile/ProfileTabs.tsx` (Profile, Preferences, Search rules; links to `/profile`, `/profile/preferences`, `/profile/search-rules`); `PreferencesPage` and `SearchRulesPage` rendered inside it; routes in `routes.tsx` with redirects `/preferences` → `/profile/preferences` and `/search/rules` → `/profile/search-rules` (replace); the setup checklist links in `features/home/setup.ts` and any other internal links point at the new addresses; remove the two menu entries. Test first: `US4 AS1 preferences tab saves`, `US4 AS2 search rules tab approves`, `US4 AS3 old addresses open the tabs`, `US4 AS4 checklist link opens the search rules tab`.

**Checkpoint**: Ravi reviews.

---

## Phase 8: User Story 5 - A shorter menu, with review items on Home (Priority: P2)

**Goal**: four menu entries; review items as a notice on Home.

**Independent Test**: the menu is Home, Companies, Profile, Settings; one waiting item shows "1 item needs your review" on Home, none shows nothing; `/review` still opens.

- [ ] T024 [US5] Frontend: `frontend/src/app/Shell.tsx` menu is exactly Home, Companies, Profile, Settings; `frontend/src/features/home/ReviewNotice.tsx` on both Home tabs uses the review-items query ("N item(s) need your review" linking to `/review`); `/review` stays a route; `frontend/src/app/AiBanner.tsx` links still valid. Test first: `SC001 menu has four entries`, `US5 AS2 review notice with count`, `US5 AS3 no notice when nothing waits`, `US5 AS4 review page still opens`.

**Checkpoint**: Ravi reviews.

---

## Phase 9: Polish & cross-cutting

- [ ] T025 [P] Playwright: update `frontend/e2e/setup-and-profile.spec.ts`, `job-search.spec.ts`, `company-contacts.spec.ts` for the new menu, tabs and addresses and the removed cost text (the budget step goes); add to `job-search.spec.ts`: inquire on a job → In pipeline shows Inquired → mark applied → shows Applied → the company shows Applied; assert no page shows AI cost wording ("AI cost", "cost so far", "budget", "spend"; not `$`, which pay in Preferences can use); each mark (I inquired, I applied, Undo) is one click (SC-002). SC-001 to SC-005.
- [ ] T026 [P] Docs: `docs/user-guide/job-search.md` (remove "What a search costs", describe Explore and In pipeline and I inquired), `getting-started.md` (no budget), `docs/user-guide/company-contacts.md` (Applied or Inquired chip, In pipeline filter), `docs/architecture.md` (§5.1 budget guard removed, §8 settings table, §10 first-level UI, the budget ADR text, the `tiktoken` open item closed), `README.md` if it mentions a budget.
- [ ] T027 Success-criteria map `specs/002d-navigation-and-pipeline/success-criteria-map.md` (SC-001 to SC-006 → tests); full gates: backend suite with the coverage gate, `ruff`, `mypy --strict`, `lint-imports`, frontend `tsc`, `eslint`, `npm test -- --coverage`, all Playwright journeys against the e2e stack.
- [ ] T028 Reviewer agents over the branch diff (python/FastAPI, security, database, React); fix findings; record them in `docs/CONTEXT.md`.
- [ ] T029 Update `docs/CONTEXT.md` (history, next steps) and `docs/clarified-requirements.md` §12 (add 002d); push and open the PR to `master` with the success-criteria map when Ravi says so.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2** before any story.
- **US6** (T005–T008) only touches the frontend theme, `Shell.tsx` and `CompaniesPage.tsx`; it goes first so US1, US4, US5 and US2's Companies work build on the new look.
- **US1** needs T002–T004. **US2** needs T002–T004; T015 and T016 need T011 and T014. US1 and US2 touch different backend files except `search/api/jobs.py` (T009, T011: do T009 first).
- **US3** is independent of US1 and US2 (different files), except the frontend fixtures in `test/api.ts`; within US3 the order T017 → T018 → T019 → T020 → T021 keeps each step green; T022 can run any time after T020.
- **US4** and **US5** touch `routes.tsx` and `Shell.tsx`, which T010 also touches: do them after US1.
- **Polish** after all stories.

## Parallel examples

- Phase 2: T002 (domain) alongside the T003 migration draft.
- US2: T012, T013 and T014 in parallel (different files) after T011.
- US3: T022 (evals) in parallel with T021 (migration).
- Polish: T025 (Playwright) and T026 (docs) in parallel.

## Implementation strategy

- **MVP**: Phases 1–4 (the new look and US1): Home tabs and the pipeline list, with applied jobs.
- Then US2 (inquired), US3 (constitution compliance), US4, US5, each a shippable increment with a review pause.
