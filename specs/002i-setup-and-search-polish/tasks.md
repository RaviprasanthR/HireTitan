---
description: "Task list for 002i-setup-and-search-polish"
---

# Tasks: Setup and search polish

**Input**: Design documents from `specs/002i-setup-and-search-polish/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md).

**Tests**: **Mandatory** (constitution V). Every task is one red → green → refactor cycle and **one commit**: write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, and keep the whole suite green.

**Organization**: grouped by user story in the plan's order: US1, US2, US6 (P1), US3, US5 (P2), US4 (P3), then Polish. US3 comes after US6 because its groups show the `areas` field US6 fills. Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US6 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `search/…` means `backend/src/hiretitan/search/…`; `setup/…` means `backend/src/hiretitan/setup/…`; tests are under `backend/tests/…`; frontend paths are under `frontend/src/…`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`; never run plain `prettier --write` on existing files.
- After any API change run `npm run gen:api` in `frontend/` (writes `backend/openapi.json` and `frontend/src/api/schema.d.ts`) and commit both with the task.
- Before pushing frontend work run `npm run build` in `frontend/`.
- The no-send scanner bans `.delete()`/`.post()`/`.put()`/`.patch()` method names under `search/`; name repo methods `clear_*`, `set_*`, `remove`, `hold`.
- The integration tests need Docker Desktop running (Testcontainers Postgres 16).
- After each phase rebuild the dev stack (`docker compose up --build -d`) so Ravi can look at it on http://127.0.0.1:8000.

---

## Phase 1: Setup

**Purpose**: a known-green baseline.

- [x] T001 Confirm `002i-setup-and-search-polish` is cut from the current `master` (merge `master` in if PR #15 `fix-careers-page-gzip` has merged meanwhile; no rebase, no force push) and record the baseline: backend suite, `ruff`, `ruff format --check`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test`, `npm run build`. Write the counts under a new 002i entry in `docs/CONTEXT.md`. No code change.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the column, the `areas` field and the two reviewed seed tables that US1, US3 and US6 all use.

- [x] T002 [P] Migration `backend/alembic/versions/0020_first_rules.py` (parent `0019_resume_picker`) and `SearchRuleSetRow.approved_by` in `search/infra/models.py`: `approved_by text NULL` with check "`approved_by IN ('person', 'auto')`"; upgrade backfills `approved_by = 'person'` where `approved_at IS NOT NULL`; downgrade drops the check and column. `RuleSetView` / `RuleSetOut` in `search/application/rules.py` and `search/api/rules.py` carry `approved_by: "person" | "auto" | null`; existing `approve` writes `'person'`. Tests first: `backend/tests/integration/platform/test_migrations.py` `test_0020_migration_up_down` and `test_0020_migration_backfills_person`; `backend/tests/integration/search/test_repos.py` `test_0020_migration_check_rejects_other_values`; `backend/tests/api/search/test_rules_api.py` `test_approve_records_person`; the model/migration drift test stays green; `npm run gen:api`.
- [x] T003 [P] `areas` on the rules: `SearchRules.areas: tuple[str, ...] = ()` in `search/domain/rules.py` with `AREAS = {back_end, front_end, full_stack, mobile, data, qa, devops, other}`; `validate()` adds field errors on `areas` for an unknown value, more than 4, or a duplicate ("each in AREAS; at most 4; no duplicates"); `search/domain/rules_serialization.py` writes `areas` as a list and reads a missing key as `()`; `SearchRulesModel` in `search/api/rules.py` gains `areas: list[str] = []`; `npm run gen:api`. Tests first in `backend/tests/unit/search/test_rules.py` and `test_rules_serialization.py`: `test_FR030_areas_validation`, `test_FR030_old_rules_without_areas_read_as_empty`, `test_FR030_areas_round_trip`.
- [ ] T004 [P] Seed tables and loaders: `backend/seed/work_areas.yaml` (per area `signals`, `avoid_in_titles`, `compatible`; synthetic, generic words only) and `backend/seed/tech_names.yaml` (`{name, aliases, kind: language | framework}` for at least Java, JavaScript, TypeScript, C#/.NET, C++, Go/Golang, Python, Ruby/Rails, PHP/Laravel, Kotlin, Swift, Scala, Rust, React, Angular, Vue, Node.js, Django, Spring); loaders with fail-fast checks (unknown area name, empty list, duplicate alias) in `search/application/seed.py` (or a new `search/application/tables_seed.py`), loaded at worker and API start next to `title_synonyms.yaml` and passed to where the proposer and rule engine run (`search_wiring.py`, `worker_main.py`, `api_main.py`); the Dockerfile already copies `backend/seed`. Tests first in `backend/tests/unit/search/test_seed_tables.py`: `test_work_areas_table_loads_and_is_consistent`, `test_tech_names_have_unique_aliases`, `test_seed_tables_reject_bad_files`.

**Checkpoint**: nothing visible changes yet. Ravi reviews.

---

## Phase 3: User Story 1 - Finish setup and search straight away (Priority: P1) 🎯 MVP

**Goal**: finishing setup approves the first rules; start-up does it for installs that finished setup without rules; Explore names any missing step with a link.

**Independent Test**: Delete all, finish the four setup cards, and Explore shows **Search now**; Search rules shows approved rules marked as set up automatically.

- [ ] T005 [US1] Use case `approve_first_rules(session, proposal_source, synonyms, tables, clock) -> FirstRulesOutcome` (`approved | already | not_possible`) in `search/application/rules.py`: takes `pg_advisory_xact_lock(<fixed key>)`, returns `already` when any `search_rule_sets` row has `approved_at` set (new repo method `ever_approved()` in `search/infra/repos.py`), otherwise proposes with the existing proposer, validates, and writes one row `status = 'approved'`, `approved_by = 'auto'`, next version; `RulesUnavailableError` or `RulesInvalidError` → `not_possible`, logged, nothing written. Tests first in `backend/tests/integration/search/test_first_rules.py`: `test_FR001_first_rules_are_approved`, `test_FR002_existing_approval_is_never_replaced`, `test_FR002_double_finish_approves_once` (two concurrent sessions, exactly one approved row), `test_FR004_invalid_proposal_writes_nothing`, `test_FR002_runs_again_after_delete_all`, `test_FR007_first_approval_makes_no_llm_call` (recording fake LLM sees no call).
- [ ] T006 [US1] Wiring: `OnboardingApiDeps.on_completed: Callable[[], Awaitable[None]] | None` in `setup/api/onboarding.py`, called after `complete_setup` commits, in its own session, with any exception logged and swallowed (the `200` body is unchanged, FR-004); `api_main.py` passes a callback built in `search_wiring.py` (`first_rules_callback(sessions, …)`) and, in the lifespan after the company seed, runs `approve_first_rules` when `setup_completed_at` is set (logged, never fatal); `lint-imports` stays clean (no `setup` → `search` import). Tests first: `backend/tests/api/setup/test_onboarding_api.py` `test_FR001_finish_setup_approves_first_rules` (then `GET /status` checklist `rules_approved: true`), `test_FR004_invalid_proposal_leaves_setup_finished`; `backend/tests/api/test_startup.py` (or the existing app start-up test file) `test_FR003_startup_approves_for_finished_setup`, `test_FR003_startup_does_nothing_before_setup`.
- [ ] T007 [US1] Frontend: Explore's empty state in `features/explore/ExplorePage.tsx` names the first missing checklist step with a link (key → `/settings`, profile → `/profile`, preferences → `/profile/preferences`, rules → `/profile/search-rules`, in that order) instead of "No jobs yet. Finish setup first." (FR-006); `features/setup/PreferencesStep.tsx` invalidates `['status']` and `['search-rules']` after Finish so Explore shows **Search now** at once; the current `features/search-rules/SearchRulesPage.tsx` shows the FR-020 line ("HireTitan set these up from your profile and preferences. Change anything you like.") when the approved set has `approved_by === 'auto'` (T018 keeps it in the rewrite). Tests first in `features/explore/ExplorePage.test.tsx`: `FR006 names the missing search rules step with a link`, `FR006 names the missing AI key first`, `US1 AS1 shows Search now once rules are approved`; `features/setup/PreferencesStep.test.tsx` `US1 AS1 finish refreshes status and rules`; `features/search-rules/SearchRulesPage.test.tsx` `US1 AS2 FR020 says the rules were set up automatically`.
- [ ] T007r [US1] Story review: python/FastAPI and database reviewer agents over T002–T007 (advisory lock, transaction boundaries, swallowed errors, start-up hook) and the React reviewer over T007; fix the findings; note them under the 002i entry in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 4: User Story 2 - See that a search is running (Priority: P1)

**Goal**: a clear searching state from the first second, one short progress line, no batches.

**Independent Test**: press Search now with the scripted sources; the panel shows the moving bar and "Searching your companies…" before any company is read, then "Checked n of N companies · m new jobs so far", never "0 of 0" or "Batch".

- [ ] T008 [P] [US2] `features/explore/SearchingIndicator.tsx` (an indeterminate bar while the total is unknown, a determinate bar for `value`/`max` once known; `aria-hidden` on the moving part) and `.ht-searching` styles at the end of `frontend/src/theme/theme.css` with a static form under `@media (prefers-reduced-motion: reduce)`; colours from existing tokens (the contrast and no-gradient tests stay green). Tests first in `features/explore/SearchingIndicator.test.tsx`: `FR008 indeterminate before the total is known`, `FR010 determinate once the total is known`, `FR012 the moving part is hidden from screen readers`.
- [ ] T009 [US2] Rewrite `features/explore/SearchPanel.tsx`: searching state while `start.isPending` or the run has no outcome; before `companies_total > 0` only the indicator and "Searching your companies…"; then "Checked {companies_read} of {companies_total} companies · {added} new jobs so far"; Stop → "Stopping… jobs found so far are kept."; end messages without "batch" ("Search finished.", "Search stopped. Jobs found so far are kept.", out of credit: "Your AI account is out of credit, so the search stopped. Jobs found so far are kept." plus the provider's message); the polite live region holds only the message line; `BATCH_SIZE` no longer imported here. Tests first in `features/explore/SearchPanel.test.tsx` (update the old ones): `US2 AS1 shows searching at once and no zero counts`, `US2 AS2 shows companies checked and new jobs`, `US2 AS4 stopping says jobs are kept`, `US2 AS5 ended messages never say batch`, `SC003 the word batch appears nowhere in the panel`, `US2 AS6 live region announces start, progress and end`.
- [ ] T009r [US2] Story review: React reviewer over T008–T009 (live region, reduced motion, re-renders while polling); fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 5: User Story 6 - Explore shows only jobs that fit me (Priority: P1)

**Goal**: area and stack rules, the real skills on the AI card, descriptions read before the AI check, and prompt v3 behind its eval gate.

**Independent Test**: the job-search journey and workflow tests with a back-end Python and Go profile: front-end and Java roles are skipped with readable reasons; generic titles are decided on their description; an unreadable description is told to the AI.

- [ ] T010 [P] [US6] Pure tech-name rule `search/domain/tech_names.py`: `names_in(title, table) -> tuple[str, ...]` (word-boundary matching through aliases; "Java" never matches "JavaScript"; "Go" only as a whole word in a tech context such as "Go developer", "Golang", "(Go)"), `stack_skip_reason(title, person_skills, table) -> str | None` (skip only when the title names at least one technology and none of them are the person's; reason "needs Java, which is not in your skills" / "needs Java or Kotlin, which are not in your skills"); hooked into `search/domain/apply_rules.py` after the title-word checks, using the approved rules' `stack_keywords` as the person's skills. Tests first in `backend/tests/unit/search/test_tech_names.py` and `test_apply_rules.py`: `test_FR032_title_stack_rule` (Java back end skipped for a Python person), `test_FR032_java_and_python_title_is_kept`, `test_FR032_javascript_is_not_java`, `test_FR032_go_needs_a_tech_context`, `test_FR032_no_tech_in_title_is_kept`, `test_FR036_stack_skip_has_a_reason`.
- [ ] T011 [P] [US6] Pure area guess and avoid words `search/domain/work_areas.py`: `guess_areas(target_roles, recent_titles, skills, table) -> tuple[str, ...]` (counted signals, ties keep both, at most 4, empty when nothing matches) and `avoid_words(areas, table) -> tuple[str, ...]` (words of areas not compatible with any of the person's); `search/domain/proposer.py` fills `areas` and `title_avoid` (origin `area:<name>`), which amends 002 FR-005 (the dated note is T024); `ProposalInput` gains `recent_titles`; `search_wiring.ProfileAndPreferencesSource` reads up to 3 recent job titles from the confirmed profile, newest first. Tests first in `backend/tests/unit/search/test_work_areas.py` and `test_proposer.py`: `test_FR030_proposer_guesses_areas` (back-end Python/Go profile → `back_end`), `test_FR031_avoid_words_for_other_areas` (front end, mobile, QA words; none for `full_stack`), `test_FR030_no_signal_gives_no_area`; existing proposer tests updated.
- [ ] T012 [US6] Profile card fix and new fields in `search/domain/cards.py` and `search_wiring.profile_card_source`: `ProfileCard` = `target_roles`, `areas` (approved rules), `main_skills` (profile skills ∪ preference key skills, deduplicated case-insensitively, languages and frameworks from `tech_names.yaml` first, "≤ 30"), `years_experience`, `seniority`, `recent_titles` ("≤ 3, each ≤ 80 characters"), `preferred_locations`, `work_modes`; `JobCardInput.description_status: "read" | "unreadable" | "none"`; `to_dict` outputs both. v2 keeps working (its template reads only keys it knows). Tests first in `backend/tests/unit/search/test_cards.py` and `backend/tests/workflow/search/test_judge.py`: `test_FR033_profile_card_has_profile_skills_and_areas` (profile skills present when preference key skills are empty: the 2026-11-16 bug), `test_FR033_languages_come_first`, `test_FR033_card_limits`.
- [ ] T013 [US6] Description port and fake: `DescriptionPort` in `search/application/ports.py` (`read(job: DescribeRequest) -> DescriptionResult(status: "read" | "unreadable", text: str | None, error: str | None)`, where `DescribeRequest` has `url`, `ats_vendor`, `board_id`, `posting_id`); `search/infra/descriptions/fake.py` (scripted by URL, files under the e2e fake folder like `career_ops/e2e`); W3 graph (`search/workflow/graph.py`) reads descriptions **after the rules and before the judge**, only for jobs the rules kept, only in `rules_and_ai` mode, then sanitises and screens the text with the existing job-text path, caps it at 30,000 characters, recomputes `skills_found` and `years_found` with `normalize` helpers, sets `description_status`, and stores the description with the job; Stop and out-of-credit still end the search between jobs; `search/workflow/recheck.py` reads first when the job has no description; `SearchDeps.descriptions: DescriptionPort | None` (None = old behaviour); in `search/workflow/judge.py`, when a job is kept and its `description_status` is not `read`, the stored reason gets the fixed sentence " Description could not be read." appended in code (FR-034 does not depend on the model; the reason stays within `REASON_MAX`). Tests first in `backend/tests/workflow/search/test_descriptions.py`: `test_FR029_descriptions_read_for_kept_jobs_only`, `test_FR029_rules_only_reads_nothing`, `test_FR029_description_refreshes_skills_and_years`, `test_FR034_unreadable_description_is_told_to_the_ai`, `test_FR034_kept_without_description_says_so_in_the_reason`, `test_FR029_stop_during_reads_keeps_finished_jobs`, `test_recheck_reads_description_first`; `backend/tests/security/test_job_text_attacks.py` `test_FR029_description_text_is_screened`.
- [ ] T014 [US6] Real description reader `search/infra/descriptions/` (`reader.py`, `vendors.py`, `page.py`, `allowlist.py`): vendor JSON readers for Greenhouse, Lever, Ashby (one board call per search, matched by id), Workday and Recruitee per research R4, and a page reader through `CareersPageFetcher` (JSON-LD `JobPosting.description`, else main text) for everything else and as the fallback when a vendor answer does not match; vendor board and posting ids are parsed from the job's own URL with one known pattern per vendor (`vendors.py`), and a URL that does not match falls back to the page read; 20 s timeout per read; HTML to text with the stdlib parser already used in `careers_page`; request allowlist with robots.txt check dates for each vendor host (check `robots.txt` of each host when recording and write the date); the no-send architecture test scans the package. Record one **synthetic** fixture per vendor (field names confirmed against the vendor's public documentation; no real company text) under `backend/tests/fixtures/descriptions/`. Wire the real reader in `worker_main.py` (cache under `<data_dir>/cache/careers_pages`). Tests first in `backend/tests/contract/descriptions/`: `test_FR029_greenhouse_description`, `test_FR029_lever_description`, `test_FR029_ashby_description`, `test_FR029_workday_description`, `test_FR029_recruitee_description`, `test_FR029_page_json_ld_description`, `test_FR029_page_main_text_fallback`, `test_FR029_vendor_mismatch_falls_back_to_page`, `test_FR029_ids_parsed_from_url`, `test_FR029_description_requests_stay_on_allowlist` (intercepts every request), `test_FR029_robots_disallow_gives_unreadable`.
- [ ] T015 [US6] Prompt `judge_relevance` v3 in `backend/src/hiretitan/prompts/judge_relevance/v3/` (`system.md`, `user.md.j2`, `schema.py` and `checks.py` copied from v2, `meta.yaml` version 3, **not yet active**): judge area first (another area → not relevant), then main stack overlap with `main_skills`, then level against `years_experience`; with `description_status` other than `read`, decide on title, company and place, leave out when the title points to another area or stack, otherwise keep with a reason that says the description could not be read; untrusted-block rules and the `role` rule unchanged. Eval cases in `backend/evals/judge_relevance/cases.py`: a synthetic back-end Python and Go profile (4.5 years, recent titles) and about 40 postings tagged by group (different area in title, different stack in title, generic title with a deciding description, generic title without a description, far above level, true matches); the runner reports the SC-008 rows (share of front-end, mobile, QA and Java roles left out; recall on relevant cases). Tests first: `backend/tests/unit/prompts/test_judge_relevance_v3.py` (renders with every card field, schema and checks shared with v2, the registry still serves v2 as current), `backend/tests/unit/evals/test_judge_relevance_cases.py` (new groups present, synthetic only, SC-008 rows computed).
- [ ] T016 [US6] **Gate (needs Ravi's key)**: run `PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run judge_relevance --models fast --repeat 3 --yes` from the repo root; commit the report; when it passes (precision and recall ≥ 90%, SC-008: ≥ 95% of front-end, mobile, QA and Java roles left out and recall on relevant cases ≥ 95%, 0 unusable), make v3 current in the prompt registry and update the default-version test. If it fails, adjust the v3 prompt (not the cases) and re-run; record each run in `docs/CONTEXT.md`.
- [ ] T016r [US6] Story review: python/FastAPI and security reviewer agents over T010–T016 (untrusted description path, allowlist, robots, timeouts, injection screening, the prompt's data blocks); fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews; then one real search on the dev stack to measure SC-009 (share of kept jobs with a description), recorded in `docs/CONTEXT.md`.

---

## Phase 6: User Story 3 - Understand and change the search rules (Priority: P2)

**Goal**: a plain-language Search rules page with a read view and Edit / Save / Cancel.

**Independent Test**: open Search rules; no per-item tags; Edit, change a title, Save → "Rules saved." and a new version; an invalid edit is refused next to its group.

- [ ] T017 [US3] Endpoints in `search/api/rules.py` and use cases in `search/application/rules.py`: `GET /search/rules/suggested` (proposer output, writes nothing; `409 rules_unavailable` as today) and `PUT /search/rules/approved` (validate; in one transaction write a new approved version with `approved_by = 'person'`, supersede the old one, discard any open proposal; `422` field errors); `npm run gen:api`. Tests first in `backend/tests/api/search/test_rules_api.py`: `test_FR017_suggested_writes_nothing`, `test_FR015_put_approved_saves_new_version`, `test_FR015_put_approved_discards_open_proposal`, `test_FR016_put_approved_rejects_invalid_rules`.
- [ ] T018 [US3] Rewrite `features/search-rules/SearchRulesPage.tsx`: read view with three groups and one-sentence explanations ("Jobs we keep": job titles; "Jobs we leave out": words to avoid, places to skip, oldest posting age; "What helps rank a job when the AI check is on": areas, skills, places you prefer, and work mode, seniority and years read-only with a link to Preferences); no per-item tags (FR-014); the FR-020 line when `approved_by === 'auto'`; **Edit** → edit view with **Save** (`PUT /search/rules/approved`) and **Cancel**; **Start over with suggested rules** fills the editor from `GET /search/rules/suggested`; the stale notice offers **Update from my profile** (opens the editor with suggested rules); a leftover open proposal opens the editor with it; field errors next to their group; unsaved edits register with the `unsaved.ts` registry so `LeaveGuard` asks before leaving; areas edited as checkboxes from the fixed list. Tests first in `features/search-rules/SearchRulesPage.test.tsx` (rewrite): `US3 AS1 shows the three groups`, `SC003 shows none of the old tag texts`, `US3 AS3 edit and save makes a new version`, `US3 AS4 cancel changes nothing`, `US3 AS5 invalid save shows the error next to its group`, `US3 AS6 update from my profile opens suggested rules`, `US3 AS7 start over fills suggested rules unsaved`, `US3 AS8 asks before leaving with unsaved edits`, `FR020 says the rules were set up automatically`, `leftover proposal opens in the editor`, `SC004 change a title in three clicks` (Edit, type, Save).
- [ ] T018r [US3] Story review: python/FastAPI reviewer over T017, React reviewer over T018 (focus after Save/Cancel, leave guard, field error association); fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 7: User Story 5 - Job details open in the Explore row (Priority: P2)

**Goal**: Explore rows expand in place; the title opens the posting in a new tab.

**Independent Test**: click a row → details under it; click the title → posting in a new tab; Enter on the expand button toggles it.

- [ ] T019 [P] [US5] Extract `features/jobs/JobDetails.tsx` from `features/jobs/JobDetailPage.tsx` (place, work mode, posted date, decision and reason, decision history, sources, description, injection warning, duplicate notice, actions: I applied, I inquired, Check again, Restore, Delete) and use it in `JobDetailPage`. Tests: the existing `features/jobs/JobDetailPage.test.tsx` stays green unchanged (behaviour-preserving refactor); add `features/jobs/JobDetails.test.tsx` `renders the description and sources`.
- [ ] T020 [US5] Explore rows in `features/explore/ExplorePage.tsx`: `JobCardItem` becomes an expandable row (expand button with `aria-expanded` and `aria-controls`, Enter/Space toggle, row click outside the title and buttons toggles), the expanded part loads `GET /jobs/{id}` and renders `JobDetails`; the title is `<a href={first source url} target="_blank" rel="noopener noreferrer">` and plain text when there is no link; check (in the API or `search/infra/repos.py`) that `sources` come oldest first and pin it with a test. Tests first in `features/explore/ExplorePage.test.tsx`: `US5 AS1 row expands and collapses in place`, `US5 AS2 title opens the posting in a new tab`, `US5 AS3 first-found source is the title link`, `US5 AS4 no link means plain text`, `US5 AS5 keyboard toggles and announces`, `US5 AS6 actions work in the expanded row`, `FR028 Explore no longer links to the job page`; backend `backend/tests/api/search/test_jobs_api.py` `test_sources_oldest_first`.
- [ ] T020r [US5] Story review: React reviewer over T019–T020 (nested interactive elements, focus, keyboard); fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 8: User Story 4 - A roomier Preferences step in setup (Priority: P3)

**Goal**: a wide card for the Preferences (and Review) step.

**Independent Test**: at 1280 px the Preferences groups sit in two columns; at phone width one column, no sideways scroll.

- [ ] T021 [US4] `features/setup/SetupLayout.tsx` takes `width?: 'narrow' | 'wide'` (`max-w-2xl` / `max-w-6xl`); `SetupGate` passes `wide` for the review and preferences steps; check the embedded Preferences grid reaches two columns at `lg`. Take before and after screenshots at 1280 × 800 for SC-005 (record the scroll heights in `docs/CONTEXT.md`). Tests first in `features/setup/SetupGate.test.tsx`: `FR021 preferences step uses the wide card`, `FR021 name and resume steps stay narrow`; `features/setup/PreferencesStep.test.tsx` `FR022 collects the same fields`.
- [ ] T021r [US4] Story review: React reviewer over T021 (layout at 1280 px and phone width, no sideways scroll, focus order unchanged); fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 9: Polish & cross-cutting

- [ ] T022 [P] Playwright: `frontend/e2e/setup-and-profile.spec.ts` goes from Finish setup straight to Explore and finds **Search now** without visiting Search rules (SC-001); `frontend/e2e/job-search.spec.ts` checks the searching state (no "0 of 0", no "Batch"), expands a row, opens a title link (new page event), and finds front-end and Java postings among the skipped jobs with their reasons; fixtures: synthetic postings in `backend/tests/fixtures/career_ops/e2e/`, descriptions for the fake reader, scripted v3 `judge_relevance` replies in `backend/tests/fixtures/fake_llm/e2e/` (one decision per job that passes the rules); `frontend/e2e/prepare.mjs` copies the new fake folders. Run all three journeys against a rebuilt `hiretitan-e2e` stack.
- [ ] T023 [P] Docs: `docs/user-guide/job-search.md` (searching panel, Explore rows, Search rules page, areas and the stack rule, descriptions), `docs/user-guide/getting-started.md` (rules set up automatically), `docs/architecture.md` (description reader, first approval, prompt v3), README features list if it names these screens.
- [ ] T024 Change notes (FR-024): dated notes in `docs/clarified-requirements.md` §3 and `specs/002-job-search/spec.md` FR-002, FR-004, FR-005, FR-006; a 002i line in `docs/clarified-requirements.md` §12.
- [ ] T025 Gates and `specs/002i-setup-and-search-polish/success-criteria-map.md` (SC-001 … SC-009 → tests, eval report, measurements; also FR-023, English only, no AI cost, theme, keyboard and focus, mapped to the contrast tests and story reviews): backend suite with the coverage gate, `ruff`, `ruff format --check`, `mypy --strict`, `lint-imports`, `pip-audit`, licence gate; frontend `tsc`, `eslint`, `npm test` with coverage, `npm run build`, `npm audit`, licence check; three Playwright journeys.
- [ ] T026 Final review: python/FastAPI, database, React and security reviewer agents over `master...HEAD`; fix the findings; update `docs/CONTEXT.md` §4 and §5. Open the PR to `master` only when Ravi says so (include the v3 eval report).

---

## Dependencies & execution order

- **Phase 1 → Phase 2** before any story.
- **US1** (Phase 3) needs T002 (approved_by) and T004 (tables for the proposer's areas; the proposer runs without them until T011).
- **US2** (Phase 4) is frontend only and depends on nothing but Phase 1.
- **US6** (Phase 5) needs T003 and T004. Inside: T010, T011 in parallel → T012 → T013 → T014; T015 after T012; **T016 gate after T013–T015** and needs Ravi's key.
- **US3** (Phase 6) needs T002, T003 and T011 (areas in proposals) for its groups.
- **US5** (Phase 7) is frontend only plus one ordering test; independent of the others.
- **US4** (Phase 8) is frontend only; independent.
- **Polish** after all stories.

Story completion order: US1 → US2 → US6 → US3 → US5 → US4. US2, US5 and US4 could be built in any order or alongside the others.

## Parallel opportunities

- Phase 2: T002, T003, T004 touch different files.
- US2: T008 alongside any backend task.
- US6: T010 and T011 together; T015's eval cases can be written while T014 is in progress.
- US5: T019 alongside US3 backend work (T017).
- Polish: T022 and T023 together.

Example (US6 start): run T010 (`tech_names.py`) and T011 (`work_areas.py`, proposer) as separate commits in parallel; then T012.

## Implementation strategy

- **MVP**: Phase 1, Phase 2 and US1. Ravi can delete his data, finish setup and search at once.
- Then US2 (trust the search), then US6 (the jobs are right), each a reviewable increment.
- US3, US5 and US4 polish what is already working.
- Pause for Ravi's review after every phase; rebuild the dev stack each time.
