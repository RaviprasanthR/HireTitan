# Success criteria map: Resume picker

Each success criterion of [spec.md](spec.md) and the tests that prove it. Backend tests are under `backend/tests/`, frontend tests under `frontend/src/`, the journey in `frontend/e2e/job-search.spec.ts`.

| Criterion | Proof |
|---|---|
| **SC-001** Recording the resume costs at most one extra step, and marking without one costs nothing extra | `PipelineControl.test.tsx`: `US1 AS3 one click still marks the job, recording None when nothing was picked`, `US1 AS4 starts on the last choice and sends it with the mark`, `US1 AS6 sends no resume field and shows no choice without stored files`; `api/search/test_resume_choice_api.py`: `test_FR001_mark_applied_records_the_chosen_resume`, `test_FR002_mark_without_resume_field_behaves_as_before`; the journey's step 7c (choose while marking, one click) |
| **SC-002** Every pipeline job with a resume shows its name in the list and its name and added day in the details | `test_FR004_pipeline_cards_carry_the_resume`, `test_FR005_interview_details_and_job_detail_carry_the_resume`; `PipelinePage.test.tsx`: `US2 AS1 shows the name of the resume used`, `US2 AS2 shows a dash without a resume`, `US2 AS4 shortens a long name and keeps the full name in a title`, `US2 AS3 shows the name and the day it was added`; `InterviewPanel.test.tsx`: `US2 AS3 shows the resume name and the day it was added`; `JobDetailPage.test.tsx`: `US2 AS3 the job page shows the resume name and the day it was added` |
| **SC-003** Set, change or clear the resume of an existing job in under 30 seconds | Checked by hand with [quickstart.md](quickstart.md) step 5 (a few clicks, no typing). The steps are automated: `test_FR006_edit_card_sets_changes_and_clears`, `InterviewPanel.test.tsx`: `US3 AS1 choose a resume and save`, `US3 AS2 change the resume, then clear it`, and the journey's step 7c, which sets, changes and clears it |
| **SC-004** After a file is removed, no job fails to load or offers it, jobs show its name marked removed (or a dash when the names were cleared), the dialog states the count, and clearing leaves nothing | `integration/search/test_resume_choice_repo.py`: `test_FR009_removing_a_file_keeps_its_name_as_a_removed_note`, `test_FR009_usage_counts_jobs_per_file`, `test_FR009_clear_everywhere_drops_a_row_that_held_only_the_resume`; `test_FR009_a_removed_file_shows_as_a_removed_note`, `test_FR009_clear_all_uses_of_a_file`, `test_FR009_a_removed_note_can_be_cleared`, `test_edit_card_resume_of_a_removed_file_is_refused`; `ResumeFiles.test.tsx`: `US4 AS1 says how many jobs use the file and that the name stays as a note`, `US4 AS6 also clear the name clears the jobs first, then removes the file`, `FR009 while the use counts load, the dialog says so and cannot remove the file`; the journey's step 7c |
| **SC-005** No resume name or choice reaches an AI model, and none remains after Delete all | `security/test_contacts_privacy.py`: `test_SC005_no_resume_name_in_ai_calls` (a recorded search), `test_FR022_workflows_cannot_import_contacts` (extended to the three new modules), and the import-linter contract `contacts-stay-out-of-ai-paths`; `api/setup/test_delete_all_api.py`: `test_SC005_delete_all_removes_resume_choices_and_last_choice`; `test_FR011_removing_a_job_removes_its_resume` |
| **SC-006** Existing pipeline jobs and the one-click marks behave as before | The 002, 002d and 002e suites are unchanged apart from the new `resume` field in their expected responses and fixtures (`test_read_empty_details`, the interview fixtures in `PipelinePage.test.tsx` and `JobDetailPage.test.tsx`) and the `resume_lookup` dependency in their app setup; the full suites pass (below). Behavioural guards: `test_FR002_mark_without_resume_field_behaves_as_before`, `test_FR003_inquired_to_applied_keeps_the_resume` |

## Gates (2026-11-15, branch `002f-resume-picker`)

| Gate | Result |
|---|---|
| `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports` | clean (8 contracts kept) |
| Backend tests with coverage | 1638 passed, 8 skipped (image tests, career-ops checkout, private deny list); coverage gate passed on the T016 run (1639 tests; one redundant unit test was removed in T017) |
| `pip-audit --skip-editable` | no known vulnerabilities |
| Backend licence gate | passed (81 packages) |
| Frontend `tsc`, `eslint`, tests with coverage | clean (0 errors, 1 old warning); 462 tests after T017 (458 and 92.5% lines on the T016 coverage run) |
| Frontend `npm run build` | passed |
| `npm audit --omit=dev`, licence check | 0 vulnerabilities; licence check exit 0 (101 packages) |
| Playwright (company contacts, job search with the resume step, setup and profile) | 3 passed against a stack built from the branch |

Story reviews (python/FastAPI, security, database, React) ran after each user story; their findings and the accepted leftovers are in `docs/CONTEXT.md`.
