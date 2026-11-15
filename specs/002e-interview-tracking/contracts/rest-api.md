# REST API: Interview tracking (002e)

Base `/api/v1`. JSON. Errors are RFC 9457 problems as in 001/002 (`422` with `errors: [{field, message}]`, `409` with a `reason`, `404` for an unknown id). Nothing here starts a workflow or calls the AI.

## Read

### `GET /jobs/{job_id}/interview`

200:

```json
{
  "job_id": "…",
  "can_edit": true,
  "can_add_round": true,
  "contact": {"name": "Asha Rao", "role": "Recruiter", "email": null, "phone": null, "linkedin_url": null},
  "source": {"kind": "hiring_firm", "firm_name": "TalentBridge"},
  "rounds": [
    {
      "id": "…", "number": 1, "kind": "technical", "state": "cleared",
      "scheduled_at": "2026-11-14T10:30:00Z", "interviewers": "Ben (EM)",
      "feedback": "Good on systems design.",
      "questions": [{"id": "…", "position": 1, "question": "Design a rate limiter", "answer": "Token bucket…"}]
    }
  ],
  "status": {"state": "cleared", "round": 1}
}
```

- `contact` and `source` are `null` until saved. `source.kind` is `direct` or `hiring_firm`.
- `can_edit` is false when the job is not applied or inquired (R6); `can_add_round` is false then, or when a round is failed (R5).
- `status` follows data-model `status_summary`; `{"state": "applied"|"inquired", "round": null}` without rounds.

### Job list change

`GET /jobs?list=pipeline` items (`JobCardOut`) gain `interview: {"state", "round"} | null`. Other lists return `null`.

## Contact and source

### `PUT /jobs/{job_id}/interview/contact`

Body `{"name", "role"?, "email"?, "phone"?, "linkedin_url"?}`; `name` required. `DELETE` on the same path clears the contact. 200 returns the full `GET` shape. 422 field errors (`name`, `email`, `phone`, `linkedin_url`, length). 409 `not_in_pipeline`.

### `PUT /jobs/{job_id}/interview/source`

Body `{"kind": "direct"}`, `{"kind": "hiring_firm", "firm_name": "…"}` or `{"kind": null}`. 200 full shape. 422 `firm_name` required for a hiring firm. 409 `not_in_pipeline`.

## Rounds

### `POST /jobs/{job_id}/interview/rounds`

Body `{"kind", "scheduled_at"?, "interviewers"?}`; the server numbers the round and it starts `scheduled`. 201 full shape. 409 `not_in_pipeline`, `process_failed`. 422 unknown `kind`, bad date-time, length.

### `PATCH /interview/rounds/{round_id}`

Any of `kind`, `scheduled_at`, `interviewers`, `state`, `feedback` (null clears an optional field). 200 full shape. 409 `not_in_pipeline` (the job left the pipeline). 404 unknown round.

### `DELETE /interview/rounds/{round_id}`

Deletes the round and its questions. 200 full shape. Other rounds keep their numbers.

## Questions

### `POST /interview/rounds/{round_id}/questions`

Body `{"question", "answer"?}`. 201 full shape; the new pair goes last.

### `PATCH /interview/questions/{question_id}`

Any of `question`, `answer`. 200 full shape.

### `DELETE /interview/questions/{question_id}`

200 full shape.

Every write returns the job's full interview shape, so the panel redraws from one response.

## Test matrix (names reference requirement and scenario ids)

| Area | Tests |
|---|---|
| Domain | `test_FR004_next_round_number`, `test_FR006_failed_blocks_new_rounds`, `test_FR007_status_summary_*`, `test_FR014_line_breaks_kept` |
| Repo / DB | `test_FR009_checks_reject_bad_values`, `test_FR003_firm_iff_hiring_firm`, `test_FR004_unique_round_number`, `test_SC005_rounds_matching_by_field` |
| API | `test_US1_AS2_contact_with_only_a_name`, `test_US1_AS3_bad_email_refused`, `test_US1_AS4_hiring_firm_needs_a_name`, `test_US2_AS1`…`AS7`, `test_US3_AS1`…`AS4`, `test_R6_not_in_pipeline_refused`, `test_SC002_pipeline_status_column` |
| Lifecycle | `test_FR011_undo_keeps_details` (SC-006), `test_FR011_delete_job_removes_details`, `test_FR012_merge_keeps_winner_fills_gaps`, `test_SC004_delete_all_removes_interview_data` |
| Privacy | `test_SC003_no_interview_text_in_ai_calls`, import-linter `contacts-stay-out-of-ai-paths` extended, no-send scan |
| Frontend | `US1 AS1 row expands to the detail panel`, `US1 AS5 job page shows the same panel`, `US2 AS1 status reads Round 1 scheduled`, `US2 AS4 failed disables Add round`, `US3 AS1 question kept in order`, `FR013 collapse with unsaved edits asks first`, `FR015 no cost text` |
| E2E | job-search journey: add a contact and a hiring firm, two rounds, a question; In pipeline shows "Round 2 scheduled" |
