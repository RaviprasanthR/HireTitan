---
description: "Task list for 002b-company-contacts"
---

# Tasks: Company contacts, notes and open roles

**Input**: Design documents from `specs/002b-company-contacts/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md). **Feature 002 (PR #4) must be merged into `master` and this branch rebased onto it before T001** (migration `0015` has parent `0014_job_role_short`).

**Tests**: **Mandatory** (constitution V). Every task is one red → green → refactor cycle and **one commit**: write the listed tests first, watch them fail for the right reason, write the minimum code, then refactor. Test names reference the requirement or scenario ID they verify (`test_FR006_…`, `test_US1_AS3_…`). Persistence and API tests run against real PostgreSQL 16 (Testcontainers; start Docker Desktop first). No new fakes are needed; the scripted fake LLM is reused for the privacy test.

**Organization**: tasks are grouped by user story. Order: US1 and US2 (P1), then US3 and US4 (P2). Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `backend/src/hiretitan/search/…` (shortened to `search/…` below), `backend/tests/…`, `frontend/src/…`
- Constraints from data-model.md are quoted in the task text so they are not left to implementation time.
- Synthetic data only (FR-026): names like "Jane Example", links like `https://www.linkedin.com/in/jane-example`, emails at `example.com`.

---

## Phase 1: Setup

**Purpose**: guard rails and fixtures; no feature behaviour yet.

- [ ] T001 Extend `backend/.importlinter` and `backend/tests/architecture/test_import_contracts.py`. Test first: `test_FR022_workflows_prompts_and_llm_cannot_import_contacts` plants an import of `hiretitan.search.application.contacts` in `search/workflow/`, `hiretitan/prompts/` and `hiretitan/platform/llm/` and expects the contract to fail for each. Then add the forbidden-import contract for `search.domain.contacts`, `search.domain.contacts_cell`, `search.domain.sheet`, `search.application.contacts`, `search.application.sheet_import` (files may not exist yet; list them by module name). R9.
- [ ] T002 [P] Extend `backend/tests/architecture/test_no_send.py` to scan the new contacts files: `test_FR015_no_send_path_in_contacts_code` (no `smtplib`, `email.mime` senders, `sendgrid`, `twilio`, `slack_sdk`, `telegram`) and `test_FR015_contacts_code_has_no_http_client` (none of `httpx`, `requests`, `aiohttp`, `urllib.request` imported by `search/domain/contacts*.py`, `search/domain/sheet.py`, `search/domain/company_match.py`, `search/application/contacts.py`, `search/application/sheet_import.py`).
- [ ] T003 [P] Create the synthetic fixtures with a README stating "synthetic only": `backend/tests/fixtures/sheets/product_companies_sample.csv` (same shape as the maintainer's sheet: five empty rows and two empty columns before the header; headers `Org Name, Location, Company site, Careers page, HR / LinkedIn contacts, Frontend openings, Backend openings, Notes`; about 12 rows covering: a company on the 002 test seed (`seed_v1.yaml`) matched by website with `www.` and trailing slash, one matched by name only, one unknown company, a contacts cell with 3 people with `[High]`/`[Med]`/`[Low]` tags and a link on the next line, a free-text contacts cell, a row with no company name, a row matching two companies, a contacts cell with 25 people, a note of 6,000 characters), `backend/tests/fixtures/sheets/job_titles_labelled.csv` (100 synthetic titles with expected areas `frontend|backend|qa|none` combinations), and `backend/tests/fixtures/sheets/not_a_sheet.csv` (a CSV with no company-name column).

**Phase 1 checkpoint**: guards in place; stop for review.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the tables, the pure keys and field checks, and the repositories every story uses.

- [ ] T004 [P] Write `search/domain/contacts.py` (pure). Test first in `backend/tests/unit/search/test_contacts.py`: `test_FR009_only_name_is_required`, `test_FR012_link_must_be_http_or_https` (accepts `https://…`, adds `https://` to a bare `linkedin.com/in/x`, rejects `javascript:`, `not a link`, no host), `test_FR012_email_and_phone_shapes`, `test_FR006_name_key_ignores_case_spacing_punctuation_accents`, `test_FR006_link_key_drops_scheme_www_query_fragment_trailing_slash`. Constraints, quoted from data-model.md: name "1–120 chars", name_key "lower-case, NFKD, punctuation and spaces removed; 1–120 chars", role "≤ 120", linkedin_url "`http`/`https` URL with a host, ≤ 500", email "plausible `local@domain.tld`, ≤ 254", phone "5–30 characters of digits, spaces, `+ - ( )`", confidence "`high` | `medium` | `low`", contact note "≤ 2,000", company note "≤ 5,000". Control characters are stripped using 001's sanitizer. Returns field errors in the shape `FieldIssue` used by 002's `paste.py`.
- [ ] T005 Add migration `backend/alembic/versions/0015_company_contacts.py` and the models `ContactRow`, `CompanyNoteRow` in `search/infra/models.py`. Test first in `backend/tests/integration/search/test_contacts_repo.py`: `test_FR006_same_company_and_name_is_unique` (`uq_company_contacts_company_name (company_id, name_key)`), `test_FR023_deleting_own_company_removes_contacts_and_note` (`ON DELETE CASCADE` on both FKs), `test_data_model_check_constraints` (confidence values, empty name_key, length limits), `test_migration_0015_upgrade_and_downgrade`. Create `ix_company_contacts_company_link (company_id, link_key) WHERE link_key IS NOT NULL`. `company_notes.company_id` is the primary key; `body` "1–5,000 chars"; `source` `import` | `typed` on both tables.
- [ ] T006 Add `ContactsRepo` and `NotesRepo` to `search/infra/repos.py` and the `ContactsStore`/`NotesStore` protocols in `search/application/contacts.py` (protocols and use-case signatures only here). Test first in `backend/tests/integration/search/test_contacts_repo.py`: `test_repo_add_get_list_update_delete_contact`, `test_repo_find_by_name_key_and_by_link_key`, `test_repo_counts_per_company_in_one_query`, `test_repo_note_upsert_and_delete_on_empty`. The counts query returns `{company_id: (contact_count, has_note)}` for all companies in one statement (no N+1).
- [ ] T007 [P] Prove the existing wipe and seed paths cover the new tables, with no production change expected. Tests in `backend/tests/integration/search/test_contacts_repo.py`: `test_SC007_delete_all_removes_contacts_and_notes` (use the real wipe store from `setup_wiring.py`), `test_FR025_seed_update_keeps_contacts_attached` (load 002's `seed_v1.yaml`, add a contact to a built-in company, load `seed_v2.yaml`, assert the contact is still attached to the same company id), `test_FR021_seed_with_contacts_field_is_rejected` (a seed file with a `contacts` field raises `SeedError`). If a test fails, fix the wipe or loader and note it in the commit.

**Phase 2 checkpoint**: tables, keys and repos done; stop for review.

---

## Phase 3: User Story 1 - Bring my company sheet in (Priority: P1)

**Goal**: import the maintainer-style CSV with contacts and notes, with a preview and an idempotent confirm.

**Independent Test**: the fixture `product_companies_sample.csv` against a fresh install with the seed: rows match the right companies, unknown companies are added as own, contacts and notes attach, bad rows are listed with reasons, and a second import changes nothing.

- [ ] T008 [P] [US1] Write `search/domain/sheet.py` (pure). Test first in `backend/tests/unit/search/test_sheet.py`: `test_FR002_header_found_below_empty_rows_and_columns`, `test_FR002_unknown_columns_are_reported_ignored`, `test_FR008_openings_columns_are_ignored`, `test_FR001_no_name_column_refuses_the_file` (error carries the headers seen), `test_FR001_bom_and_crlf_are_handled`, `test_edge_header_search_stops_after_30_rows`. Header aliases exactly as in research R2. Control characters stripped from every cell; each cell capped (name 120, city 80, URL 500, notes 5,000) with a `shortened` flag for the notes cap.
- [ ] T009 [P] [US1] Write `search/domain/contacts_cell.py` (pure): `parse(cell) -> ParsedCell` and `render(contacts) -> str`. Test first in `backend/tests/unit/search/test_contacts_cell.py`: `test_US1_AS3_one_contact_per_person_with_role_tag_and_link`, `test_FR005_confidence_tags_high_med_medium_low`, `test_FR005_unplaceable_text_is_kept_as_a_note`, `test_FR005_cell_without_a_person_becomes_a_company_note`, `test_edge_url_line_without_person_is_leftover`, `test_edge_more_than_20_people_is_shortened` (first 20 kept, flag set), `test_edge_labelled_email_and_phone_lines`, `test_FR024_render_then_parse_round_trips` (property test with `hypothesis` if already a dev dependency, else a table of 30 synthetic cases). Rules exactly as research R3, including the 6-word/capital/no-punctuation test for a new person.
- [ ] T010 [P] [US1] Write `search/domain/company_match.py` (pure). Test first in `backend/tests/unit/search/test_company_match.py`: `test_FR003_website_ignores_www_scheme_and_trailing_slash`, `test_FR003_website_match_beats_name_match`, `test_FR003_name_ignores_case_spacing_punctuation_and_suffix`, `test_US1_AS4_two_matches_are_ambiguous` (names listed in the result), `test_edge_subdomain_is_not_the_same_website`, `test_US1_AS2_no_match_is_no_match`. Keys as research R4.
- [ ] T011 [US1] Write `search/application/sheet_import.py`: `preview_sheet(...)` builds a `SheetPreview` and `apply_sheet(...)` applies it in one transaction. Depends on T004, T006, T008, T009, T010. Test first in `backend/tests/integration/search/test_sheet_import.py` (real Postgres, 002's `seed_v1.yaml`): `test_US1_AS1_contacts_attach_and_shipped_facts_unchanged` (FR-004: a built-in company's name, city, careers link and board never change; own companies may get a missing website or careers link filled), `test_US1_AS2_unknown_company_added_as_own` (origin `user`, `resolution = unresolved`, so board discovery and confirmation still apply as for a company added by hand), `test_US1_AS2_row_without_careers_link_is_added_unresolved` (imports add companies through a relaxed `add_company_from_import` in `search/application/discovery.py`, careers link optional; the manual add keeps requiring it), `test_SC001_every_named_contact_in_the_sample_is_attached` (expected count is a constant stated in `fixtures/sheets/README.md`), `test_edge_same_name_at_two_companies_stays_two_contacts`, `test_US1_AS3_contacts_created_with_four_facts`, `test_US1_AS4_skipped_rows_save_nothing`, `test_US1_AS5_second_import_changes_nothing`, `test_US1_AS5_changed_role_or_link_updates_not_duplicates` (R4: name key first, link key to rename), `test_R5_typed_note_is_kept_on_reimport` and `test_R5_imported_note_is_replaced_when_text_differs` and `test_R5_empty_notes_cell_changes_nothing`, `test_FR006_import_never_deletes`, `test_edge_row_fields_that_fail_checks_drop_only_that_field` (R11), `test_edge_note_over_5000_is_shortened_and_reported`. Counts in the result exactly as `SheetResult` in data-model.md (FR-007).
- [ ] T012 [US1] Add the sheet-import routes to `search/api/companies.py` and generalise `ImportPreviews` to hold either plan type. Test first in `backend/tests/api/search/test_sheet_import_api.py`: `test_US1_AS6_result_counts`, `test_US1_AS4_skipped_rows_listed_with_reason`, `test_SC003_every_skipped_row_is_reported` (rows in = matched + added + skipped), `test_FR001_wrong_file_type_is_refused_before_saving` (415; uses 002's `CsvFileError` rules, extension plus content check), `test_FR001_over_1mb_is_413`, `test_FR001_over_2000_rows_is_422`, `test_FR001_no_name_column_is_422_with_headers_seen`, `test_preview_expires_after_30_minutes_is_404`, `test_SC001_sixty_two_rows_under_ten_seconds`, `test_SC002_reimport_preview_has_nothing_to_do`. Contract in contracts/rest-api.md ("Sheet import"). Update the 002 `companies` API tests that touch `ImportPreviews`.
- [ ] T013 [US1] Frontend: sheet import dialog in `frontend/src/features/companies/SheetImportDialog.tsx` with `api.ts` hooks (`useSheetPreview`, `useSheetConfirm`), reached from the existing import/export area (`ImportExport.tsx`). Test first in `SheetImportDialog.test.tsx`: shows columns used and ignored, counts, the skipped list with reasons, a Confirm button that is disabled while nothing changes, the result summary after confirm, and an error message for a refused file. Plain text rendering only.

**Phase 3 checkpoint (US1 done)**: the importer works through API and UI. Before marking US1 done, review it (constitution, Development Workflow): the Python/FastAPI reviewer on the importer and routes, the security reviewer on the untrusted file, links and formula cells, the database reviewer on the uniqueness and cascade rules. Record findings and fixes in the commit or `docs/CONTEXT.md`. Then stop for Ravi's review.

---

## Phase 4: User Story 2 - See and keep my contacts and notes (Priority: P1)

**Goal**: the Companies page shows counts and a panel; the person adds, edits and deletes contacts and the note; job detail shows the company's contacts.

**Independent Test**: with a company that has two imported contacts and a note: open it, check both and the note, add, edit, delete, change the note, reload, check the changes stayed.

- [ ] T014 [US2] Write the use cases in `search/application/contacts.py` (`list_contacts`, `add_contact`, `edit_contact`, `delete_contact`, `set_note`) and `search/api/contacts.py` (router wired in `api_main.py`). Test first in `backend/tests/api/search/test_contacts_api.py`: `test_US2_AS2_contact_with_only_a_name`, `test_US2_AS3_edit_and_delete_persist`, `test_US2_AS6_bad_link_is_refused` (422 with field name), `test_FR012_bad_email_and_phone_refused`, `test_FR006_typed_duplicate_name_is_409_contact_exists`, `test_rename_into_existing_name_is_409`, `test_FR010_note_set_and_clear` (empty body deletes), `test_FR010_note_over_5000_is_422`, `test_unknown_company_is_404`, `test_US2_AS5_job_company_panel_data` (a job's `company_id` gives contacts and note in one call). Contract in contracts/rest-api.md ("Contacts and notes").
- [ ] T015 [US2] Add `contact_count`, `has_note` and an `openings` placeholder (`null` until T022 fills it; the frontend ignores `openings` until T023, so a placeholder `null` is never shown as "not searched yet") to `CompanyView`/`CompanyOut` in `search/application/companies.py` and `search/api/companies.py`, using the one-query counts from T006. Test first in `backend/tests/api/search/test_companies_api.py`: `test_US2_AS1_company_row_has_contact_count_and_note_flag`, `test_companies_list_runs_a_fixed_number_of_queries` (statement-count assertion, no N+1).
- [ ] T016 [P] [US2] Frontend: company panel `frontend/src/features/companies/CompanyPanel.tsx` (contacts list, add/edit form with the field errors from the API, delete with a confirm that names the contact, note editor) and hooks in `api.ts`. Test first in `CompanyPanel.test.tsx`: `US2 AS1 shows contacts and note`, `US2 AS2 adds a contact with only a name`, `US2 AS3 edit and delete with confirmation`, `US2 AS4 link opens in a new tab with rel noopener noreferrer and is never fetched`, `US2 AS6 shows the field error for a bad link`, `email and phone render as plain text, not links`.
- [ ] T017 [US2] Frontend: show contact count and a note marker on each row of `CompaniesPage.tsx`, open the panel from the row, and update the own-company delete confirmation to say how many contacts will go (uses `GET /companies/{id}/contacts`, FR-023). Test first in `CompaniesPage.test.tsx`: `US2 AS1 row shows counts and note marker`, `FR023 delete confirmation states the contact count`, `SC004 contacts reachable in two clicks`.
- [ ] T018 [P] [US2] Frontend: show the same panel in job detail for a job with a `company_id` (read and edit), in `frontend/src/features/jobs/` (the job detail screen from 002). Test first: `US2 AS5 job detail shows company contacts and note`, `pasted job with no company shows no panel`.

**Phase 4 checkpoint (US2 done; P1 complete)**: before marking US2 done, review it: the Python/FastAPI reviewer on the contacts routes, the React reviewer on the panel and rows, the security reviewer on link handling and plain-text rendering, the database reviewer on the counts query. Record findings and fixes. Then stop for Ravi's review. This is the first shippable increment.

---

## Phase 5: User Story 3 - Open front end, back end and QA roles (Priority: P2)

**Goal**: per-company open-role counts from HireTitan's own jobs, with filters and click-through.

**Independent Test**: jobs titled "Senior Frontend Engineer", "Backend Developer (Go)", "SDET", "Marketing Manager" at two companies give the right counts, closed/applied/skipped jobs are not counted, never-searched shows "not searched yet", and the count links match the jobs.

- [ ] T019 [US3] Write `search/domain/job_area.py` (pure): `areas_of(title) -> frozenset[Area]`. Test first in `backend/tests/unit/search/test_job_area.py`: `test_FR017_full_stack_counts_for_front_end_and_back_end`, `test_FR017_unrelated_title_counts_nowhere`, `test_FR017_go_counts_only_with_capital_G`, `test_FR017_designer_excluded_unless_engineering_word`, `test_SC005_labelled_titles_95_percent` (reads `job_titles_labelled.csv`; asserts at least 95 of 100 exactly right and prints the misses). Word lists as the starting point in research R6; adjust them until the labelled test passes, but never tune the labelled file to fit the code.
- [ ] T020 [US3] Write `search/application/openings.py`: `openings_by_company(...)` and `jobs_for_area(...)`. Test first in `backend/tests/integration/search/test_openings.py` (real Postgres): `test_US3_AS1_counts_per_area`, `test_US3_AS3_full_stack_counts_in_both`, `test_US3_AS4_applied_skipped_deleted_and_unlisted_not_counted` (only `state = 'explore'` and `listed = true`), `test_US3_AS5_never_searched_is_null_not_zero` (`last_checked_at IS NULL` gives `None`), `test_SC005_counts_equal_explore_list_for_every_company`, `test_openings_use_one_query_for_all_companies`.
- [ ] T021 [US3] Add or confirm the `company_id` filter, and add the `area` filter, on `GET /jobs` in `search/api/jobs.py`. Test first in `backend/tests/api/search/test_openings_api.py`: `test_US3_AS1_counts_per_area_link_to_jobs` (length of the filtered list equals the count), `test_FR020_area_requires_company_id` (422), `test_area_filter_returns_whole_set_without_cursor`, `test_unknown_area_is_422`.
- [ ] T022 [US3] Fill `openings` in the companies list response (`search/api/companies.py`, `search/application/companies.py`) from T020. Test first in `backend/tests/api/search/test_companies_api.py`: `test_US3_AS1_company_row_has_openings`, `test_US3_AS5_row_openings_null_when_never_searched`.
- [ ] T023 [P] [US3] Frontend: opening-count columns on `CompaniesPage.tsx` (each count links to Explore filtered by company and area; "not searched yet" when null), client-side sort by each count, and filters "has contacts" and "has front end / back end / QA openings". Test first in `CompaniesPage.test.tsx`: `US3 AS1 counts link to the company's jobs`, `US3 AS5 shows not searched yet, not zero`, `FR020 filter by has back end openings shows only that company`, `FR020 sort by front end openings`, `FR020 filter by has contacts`. Explore page reads `company_id` and `area` from the URL and shows a removable "Company: X · Back end" chip (`frontend/src/features/explore/ExplorePage.tsx`; test `explore shows and clears the company/area filter`).

**Phase 5 checkpoint (US3 done)**: before marking US3 done, review it: the Python reviewer on the classifier and openings use case, the database reviewer on the counts and jobs queries, the React reviewer on the new columns and Explore chip. Record findings and fixes. Then stop for Ravi's review.

---

## Phase 6: User Story 4 - My contacts stay mine (Priority: P2)

**Goal**: prove and finish the privacy rules: export opt-in, nothing to the AI, nothing shipped.

**Independent Test**: import contacts, run a search, export with and without contacts, then delete all: the AI calls hold no contact data, the default export has none, the opt-in export imports back, and nothing remains after delete-all.

- [ ] T024 [US4] Extend `export_csv` in `search/application/companies_csv.py` and the export route with `include_contacts`. Test first in `backend/tests/api/search/test_export_contacts.py`: `test_US4_AS2_default_export_has_no_contact_fields` (no `contacts`/`notes` header and no contact string anywhere in the body), `test_US4_AS3_opt_in_export_round_trips_through_sheet_import` (export from install A, delete all, import into a fresh install, same contacts and notes), `test_formula_cells_in_contacts_are_escaped`, `test_002_import_of_an_export_with_contacts_ignores_the_extra_columns`. Uses `contacts_cell.render` (T009).
- [ ] T025 [US4] Write `backend/tests/security/test_contacts_privacy.py` against the real search workflow with the scripted fake LLM recording every request: `test_FR022_no_ai_call_contains_contacts_or_notes` (seed contacts, notes, emails and phones with unique marker strings, run a full search, assert no marker in any recorded request), `test_FR022_workflows_cannot_import_contacts` (reads the import graph), `test_FR021_shipped_files_contain_no_contacts` (scans `backend/seed/` and `docs/` for the markers and for any `linkedin.com/in/` that is not a placeholder). SC-006. If any test fails, fix the leak, not the test.
- [ ] T026 [P] [US4] Frontend: an "Include contacts and notes" option on export in `ImportExport.tsx` (off by default, with one line saying the file will hold other people's details). Test first: `US4 AS2 default export link has no contacts`, `US4 AS3 option adds include_contacts=true`.
- [ ] T027 [US4] Delete-all and company-delete paths end to end in `backend/tests/api/search/test_delete_contacts_api.py`: `test_US4_AS1_delete_all_removes_contacts_and_notes_via_api`, `test_FR023_deleting_own_company_removes_its_contacts_via_api`, `test_hidden_company_keeps_contacts` (edge case), `test_FR025_contacts_survive_a_shipped_list_update`. Fix any gap found.

**Phase 6 checkpoint (US4 done)**: before marking US4 done, review it: the security reviewer on the export, the AI-call privacy test and the shipped-files scan, the database reviewer on the delete paths. Record findings and fixes. Then stop for Ravi's review.

---

## Phase 7: Polish & cross-cutting

- [ ] T028 [P] Playwright: add a contacts step to `frontend/e2e/job-search.spec.ts` against the synthetic stack (import `product_companies_sample.csv`, see counts, open a company, add a contact, run a search, click a count, export with contacts, delete all, assert empty). SC-004: assert that a company's contacts are reached in two clicks or fewer from the Companies page.
- [ ] T029 [P] Docs: add a section "Company contacts and notes" to `docs/user-guide/` (how to export a sheet as CSV, what the import does with each column, what is never sent anywhere), update `docs/architecture.md` and the endpoint table, and note the CSV-only decision.
- [ ] T030 Success-criteria sweep: write the SC-001 to SC-007 map (success criterion to test names, as 001 and 002 did) for the PR description, run the full backend and frontend suites, `ruff`, `mypy --strict`, `lint-imports`, coverage gates. Fix what fails.
- [ ] T031 Final cross-story review pass over the whole branch diff (the per-story reviews already happened at each phase checkpoint): python/FastAPI, security, database, React. Record anything found across stories, and the fixes, in `docs/CONTEXT.md`.
- [ ] T032 Update `docs/CONTEXT.md` (history entry, status, next steps) and `docs/clarified-requirements.md` §12 (renumber the other `002b more-sources`). Open the PR to `master` with the success-criteria map.

---

## Dependencies & Execution Order

- **Phase 1** (T001–T003) has no dependencies; T002 and T003 can run alongside T001.
- **Phase 2** (T004–T007) needs Phase 1. T004 is parallel to T005; T006 needs T004 and T005; T007 needs T005 and T006.
- **US1** (T008–T013): T008, T009, T010 are parallel pure-domain tasks that need only T004's keys; T011 needs all three plus T006; T012 needs T011; T013 needs T012.
- **US2** (T014–T018): T014 and T015 need Phase 2 only (they do not need US1, so US2 can start in parallel with US1 once Phase 2 is done); T016 needs T014; T017 needs T015 and T016; T018 needs T014 and T016.
- **US3** (T019–T023) needs Phase 2 and 002's jobs; independent of US1 and US2 except T022 and T023, which edit the same files as T015 and T017 (do them after).
- **US4** (T024–T027): T024 needs T009 and T011 (render and import); T025 needs T014 (data to leak); T026 needs T024; T027 needs T014.
- **Polish** needs all stories.

## Parallel opportunities

- Phase 1: T002, T003.
- Phase 3: T008, T009, T010 together.
- After Phase 2: US1, US2 and US3's pure part (T019) can proceed on different files.
- Frontend tasks T013, T016, T018, T023, T026 touch different files from each other and from the backend tasks of their story.

## Implementation strategy

1. **MVP = Phases 1 to 4 (US1 + US2)**: import a sheet, see and keep contacts and notes. This is what Ravi asked for first.
2. Then US3 (open-role counts) and US4 (privacy completion). The privacy guards in Phase 1 and the privacy tests in Phase 6 already protect the MVP from leaking contacts, so shipping US1 and US2 first is safe.
3. One commit per task, using the `commit` skill, branch `002b-company-contacts`. Pause after each phase for review. Do not start before Ravi approves the spec, plan and these tasks, and 002 is merged.
