# REST API: Resume picker

All paths under `/api/v1`. Errors use the existing problem format (`detail`, `errors[{field, message}]`). See [../data-model.md](../data-model.md).

## Shapes

`ResumeChoiceOut` (added to `JobCardOut` as `resume` and to the interview details as `resume`):

```json
{ "state": "chosen", "resume_file_id": "uuid", "name": "Backend_2025.pdf", "added_on": "2026-10-02" }
{ "state": "removed", "resume_file_id": null, "name": "Backend_2024.pdf", "added_on": "2025-03-14" }
{ "state": "none", "resume_file_id": null, "name": null, "added_on": null }
```

## Changed endpoints

| Method and path | Change |
|---|---|
| `POST /jobs/{job_id}/applied` | Body `AppliedIn` gains optional `resume_file_id` (uuid or `null`). Absent: the job's choice and the last choice are unchanged. Present: both are set (null = None). Unknown or not-offerable file: 422, field `resume_file_id`. |
| `POST /jobs/{job_id}/inquired` | Same as applied, with `InquiredIn`. |
| `DELETE /jobs/{job_id}/applied`, `DELETE /jobs/{job_id}/inquired` | Also clear the job's resume (FR-008). |
| `GET /jobs?list=pipeline` and `GET /jobs/{job_id}` | Each card has `resume: ResumeChoiceOut`. |
| `GET /jobs/{job_id}/interview` | Adds `resume: ResumeChoiceOut`. |

## New endpoints

| Method and path | Body | Result |
|---|---|---|
| `PUT /jobs/{job_id}/interview/resume` | `{ "resume_file_id": "uuid" }` | 200 `InterviewOut` (the full details, as the other interview writes return, so `resume` is in it). 404 job unknown; 409 `not_in_pipeline`; 422 unknown, removed or not-offerable file (field `resume_file_id`). Does not change the last choice. |
| `DELETE /jobs/{job_id}/interview/resume` | none | 200 `InterviewOut`. Clears the choice or a removed note. 404 and 409 as above. |
| `GET /pipeline/resumes` | none | 200 `{ "last_choice": "uuid" \| null, "usage": [{ "resume_file_id": "uuid", "jobs": 2 }] }` |
| `DELETE /pipeline/resumes/{file_id}/uses` | none | 204. Clears the resume (id and snapshot) on every job pointing at the file, and the last choice if it is that file. Used by the removal dialog's "also clear the name" option before `DELETE /resumes/{file_id}` (research R9). 204 also when nothing pointed at it. |

The offerable files themselves come from the existing `GET /resumes` (profile), filtered by the frontend to `parse_status != 'not_resume'` and sorted newest first; the server re-checks on every write.

## Test matrix

| Test name | Covers |
|---|---|
| `test_FR001_mark_applied_records_the_chosen_resume` | US1-AS1 |
| `test_FR002_mark_without_resume_field_behaves_as_before` | FR-002, SC-006 |
| `test_FR003_inquired_to_applied_keeps_the_resume` | US1-AS2 |
| `test_FR001_mark_with_null_records_none_and_remembers_none` | US1-AS3, US1-AS4 |
| `test_FR014_last_choice_follows_marks_not_edit_card` | US1-AS4, FR-014 |
| `test_FR014_last_choice_resets_when_its_file_is_removed` | US1-AS5 |
| `test_FR012_not_a_resume_file_is_refused` | FR-012 |
| `test_FR001_unknown_file_is_a_field_error` | edge case |
| `test_FR008_undo_clears_the_resume` | US1-AS7 |
| `test_FR004_pipeline_cards_carry_the_resume` | US2-AS1/AS2 |
| `test_FR005_interview_details_carry_the_resume` | US2-AS3 |
| `test_FR006_edit_card_sets_changes_and_clears` | US3-AS1/AS2 |
| `test_FR006_jobs_before_the_feature_have_none` | US3-AS4 |
| `test_FR009_removing_a_file_keeps_its_name_as_a_removed_note` | US4-AS1, SC-004 |
| `test_FR009_a_removed_note_can_be_cleared` | US4-AS2 |
| `test_FR009_usage_counts_jobs_per_file` | US4-AS1 (count) |
| `test_FR009_clear_all_uses_of_a_file` | US4-AS6, constitution VIII |
| `test_edit_card_resume_of_a_removed_file_is_refused` | edge case (file removed while the card is open) |
| `test_FR010_merge_keeps_own_resume_else_takes_the_other` | US4-AS3 |
| `test_FR011_removing_a_job_removes_its_resume` | US4-AS4 |
| `test_SC005_delete_all_removes_resume_choices_and_last_choice` | US4-AS5, SC-005 |
| `test_SC005_no_resume_name_in_ai_calls` | FR-013, SC-005 |
| `test_prune_keeps_a_row_whose_only_detail_is_the_resume` | R6 |
| `test_resume_columns_constraints` | data model constraints |
| Frontend: `ResumeSelect` lists files newest first plus None, hidden with no files | FR-001, US1-AS6 |
| Frontend: `PipelineControl` starts on the last choice and sends it; one click unchanged | US1-AS1/AS4, SC-001 |
| Frontend: `PipelineControl` on a job that has a resume starts on that resume | US1-AS2, FR-003 |
| Frontend: `ResumeFiles` "also clear the name" option clears, then removes | US4-AS6 |
| Frontend: `PipelinePage` Resume column, dash, truncation with title | US2-AS1/AS2/AS4 |
| Frontend: edit card set/change/clear, removed note with Clear, unsaved guard | US3-AS1/AS2/AS3, US4-AS2 |
| Frontend: `ResumeFiles` removal dialog says "Used on N jobs" | US4-AS1 |
| Playwright: mark applied with a resume, see it in In pipeline | SC-001, SC-002 |
