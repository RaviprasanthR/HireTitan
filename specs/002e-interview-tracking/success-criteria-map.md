# Success-criteria map: 002e interview tracking

Each success criterion from `spec.md`, and the tests that check it.

| SC | Criterion (short) | Tests |
|---|---|---|
| SC-001 | Contact, source and a first round recorded in under 1 minute, from In pipeline, without leaving Home | `frontend/e2e/job-search.spec.ts` step 7b (applied, open the row, save contact, save source, add and clear Round 1, add Round 2 and a question, all on Home; the whole journey, search included, runs in about 12 seconds). The stopwatch check with the quickstart is Ravi's, by hand. |
| SC-002 | The Status column matches the latest round, or Applied / Inquired with no rounds | `backend/tests/unit/search/test_interviews.py` (`test_FR007_status_summary_*`: no rounds, latest round, round number not list order, failed wins, highest failed round); `backend/tests/api/search/test_pipeline_api.py` (`test_SC002_pipeline_status_column`); `frontend/src/features/explore/PipelinePage.test.tsx` (`PipelinePage status column`); `frontend/e2e/job-search.spec.ts` step 7b ("Round 2 scheduled") |
| SC-003 | No interview data in any AI request or outgoing request | `backend/tests/security/test_contacts_privacy.py` (`test_SC003_no_interview_text_in_ai_calls` records every model request of a search that finds the pipeline job again; `test_FR022_workflows_cannot_import_contacts` covers the interview modules); `backend/.importlinter` contract `contacts-stay-out-of-ai-paths`; the no-send architecture scan in `backend/tests/architecture` |
| SC-004 | After Delete all my data, nothing remains | `backend/tests/api/setup/test_delete_all_api.py` (`test_SC004_delete_all_removes_interview_data`, all three tables); `backend/tests/api/search/test_interviews_lifecycle.py` (`test_FR011_delete_job_removes_details`) |
| SC-005 | Every item can be listed by field without reading free text | `backend/tests/integration/search/test_interviews_repo_ops.py` (`test_SC005_rounds_matching_by_field`) |
| SC-006 | Undo and marking again loses nothing | `backend/tests/api/search/test_interviews_lifecycle.py` (`test_FR011_undo_keeps_details`) |

The full gate run is recorded in `docs/CONTEXT.md` (T019).
