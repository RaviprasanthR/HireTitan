# Success-criteria map: 002d navigation and pipeline

Each success criterion from `spec.md`, and the tests that check it.

| SC | Criterion (short) | Tests |
|---|---|---|
| SC-001 | The menu has 4 entries; every old screen is within 2 clicks; the review list is 1 click from the Home notice | `frontend/src/features/home/ReviewNotice.test.tsx` (`SC001 menu has four entries`, `US5 AS2 ... shows the count and links to the review page`, `US5 AS4 the review page still opens`); `frontend/src/features/profile/ProfileTabs.test.tsx` (three tabs, `US4 AS3`); `frontend/e2e/setup-and-profile.spec.ts` (menu lists exactly Home, Companies, Profile, Settings) |
| SC-002 | Inquired, applied and Undo are 1 click each; the job is in the right tab after each step | `frontend/src/features/jobs/JobDetailPage.test.tsx` (`US2 AS1`, `US2 AS2`, `US2 AS3`); `backend/tests/api/search/test_pipeline_api.py`; `frontend/e2e/job-search.spec.ts` step 5 (inquire, In pipeline shows Inquired, Undo, applied, shows Applied, the company shows Applied) |
| SC-003 | No screen shows AI cost, spend or budget | `frontend/src/no-cost.test.ts` (scans the source); the per-page `SC003` assertions in the `SearchPanel`, `RunSummaryPage`, `SearchHistoryPage` and `SettingsPage` tests; `backend/tests/architecture/test_no_cost_fields.py` (`test_SC003_no_cost_budget_or_spend_field_in_the_api`, `test_SC003_no_settings_endpoint`); `frontend/e2e/job-search.spec.ts` step 8 (every page's text) |
| SC-004 | No work is paused or refused for budget; out-of-credit still pauses and Check again resumes | `backend/tests/workflow/search/test_stops.py` (`test_SC004_no_budget_stop_however_much_was_used`, `test_FR012_out_of_credit_still_pauses_and_resumes`); `backend/tests/workflow/profile/test_profile_ingest_ai_unavailable.py` (`test_FR012_out_of_credit_pauses_run_and_check_again_resumes_it`); `backend/tests/integration/platform/test_migrations.py` (`test_FR014_0017_budget_paused_runs_become_failed`) |
| SC-005 | The old addresses open the right place | `frontend/src/app/Shell.test.tsx` (`US1 AS4 an old applied link opens the pipeline tab`); `frontend/src/features/profile/ProfileTabs.test.tsx` (`US4 AS3 the old address ... opens the tab`); `ReviewNotice.test.tsx` (`/review` opens) |
| SC-006 | Later searches change 0 inquired jobs | `backend/tests/workflow/search/test_inquired_kept.py` (`test_SC006_search_again_keeps_inquired_jobs`) |
| SC-007 | Theme text reaches 4.5:1 contrast; no gradients | `frontend/src/theme/contrast.test.ts` (`FR021_text_pairs_meet_WCAG_AA`, `SC007_no_gradient_in_the_theme`) |

The full gate run is recorded in `docs/CONTEXT.md` (T029).
