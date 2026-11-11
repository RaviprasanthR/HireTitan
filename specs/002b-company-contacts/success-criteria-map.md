# Success criteria → tests (002b)

Each success criterion in `spec.md`, and the tests that prove it. Backend paths are under `backend/tests/`.

| Criterion | What it asks | Tests |
|---|---|---|
| **SC-001** | A synthetic copy of the 62-row sheet attaches 100% of named contacts to the right company, no duplicate companies, under 10 s | `api/search/test_sheet_import_api.py::test_SC001_every_named_contact_in_the_sample_is_attached`, `::test_SC001_sixty_two_rows_under_ten_seconds`, `::test_US1_AS6_result_counts`; Playwright `frontend/e2e/company-contacts.spec.ts` (import step, "3 contacts" on Example Alpha) |
| **SC-002** | Re-importing the same file creates 0 new contacts, companies or notes | `api/search/test_sheet_import_api.py::test_SC002_reimport_preview_has_nothing_to_do`, `integration/search/test_sheet_import.py::test_US1_AS5_second_import_changes_nothing`, `::test_US1_AS5_a_blank_field_in_the_file_keeps_what_is_stored`, `::test_US1_AS5_changed_role_or_link_updates_not_duplicates` |
| **SC-003** | Every skipped row is listed with a reason | `api/search/test_sheet_import_api.py::test_SC003_every_skipped_row_is_reported` |
| **SC-004** | Who to contact at a company in 2 clicks or fewer, from the Companies page or a job | Vitest `CompaniesPage.test.tsx` "SC004 contacts reachable in two clicks" (one click: Details), `JobDetailPage.test.tsx` "US2 AS5 job detail shows company contacts and note"; `api/search/test_contacts_api.py::test_US2_AS5_job_company_panel_data`; Playwright `company-contacts.spec.ts` step 4 |
| **SC-005** | *(dropped 2026-11-11 with the open-role counts; see the change note in `spec.md`)* | — |
| **SC-006** | 0 AI calls contain contact data or notes during a search with contacts present | `security/test_contacts_privacy.py::test_FR022_no_ai_call_contains_contacts_or_notes` (records every model request in a full AI search), `::test_FR022_workflows_cannot_import_contacts`, `::test_FR021_shipped_files_contain_no_contacts`; import-linter contract `contacts-stay-out-of-ai-paths` |
| **SC-007** | After Delete all my data, 0 contacts and 0 notes remain; the default export has 0 contact fields | `integration/search/test_contacts_repo.py::test_SC007_delete_all_removes_contacts_and_notes`, `api/search/test_delete_contacts_api.py::test_US4_AS1_delete_all_removes_contacts_and_notes_via_api`, `api/search/test_export_contacts.py::test_US4_AS2_default_export_has_no_contact_fields`, `::test_US4_AS2_an_explicit_false_is_the_default`; Playwright `company-contacts.spec.ts` steps 6 and 7 |

## Also covered

| Area | Tests |
|---|---|
| Opt-in export round trip (FR-024) | `api/search/test_export_contacts.py::test_US4_AS3_opt_in_export_round_trips_through_sheet_import`, `::test_formula_cells_in_contacts_are_escaped`, `unit/search/test_contacts_cell.py` render/parse round trips |
| Removal paths (FR-023, FR-025) | `api/search/test_delete_contacts_api.py` (own company, hidden company, shipped-list update) |
| Review fixes | `api/search/test_review_fixes_002b.py` (preview_expired, preview used up only after saving, one huge cell gives 422, tab and CR escaped, duplicate name at once gives 409) |
| Applied flag (replaces open roles) | `api/search/test_companies_api.py::test_company_row_says_whether_there_is_an_application`, `::test_the_list_no_longer_carries_open_role_counts`; Vitest `CompaniesPage.test.tsx` "applications" group |

## Gates (2026-11-11)

Backend 1593 passed, 8 skipped (they need the pinned career-ops checkout or a built image), coverage gate passed (94.2% overall); ruff, ruff format, mypy --strict and import-linter (8 contracts) clean. Frontend 325 passed, tsc, eslint (0 errors) and the build clean; coverage 89.9% of lines. Playwright: all three journeys pass (setup and profile, job search, company contacts).
