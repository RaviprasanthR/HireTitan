# REST API contract: 002k

All paths are under `/api`. Errors use the existing problem format (`{status, title, detail, reason}`). Bodies are JSON unless stated. Nothing here sends, posts or opens anything outside the app (constitution I).

## Recipients

### `GET /jobs/{job_id}/recipients`

The recipient choice for a job (spec FR-010).

```json
{
  "contacts": [
    {"contact_id": "…", "name": "Asha Rao", "role": "Talent Partner", "kind": "recruiter"}
  ],
  "kinds": ["recruiter", "hiring_manager", "engineer", "other"]
}
```

`kind` is pre-selected by the role keyword rule (research R2). `404` unknown or deleted job.

## Outreach drafts

### `GET /jobs/{job_id}/drafts`

`{"drafts": [{id, kind, recipient: {contact_id?, name, role?, kind}, status, paused_reason, text, source, edited, cited_facts: [{id, text}], failure_reason, chars, updated_at}], "injection_signals": [..]}`, drafts newest first. `chars` is the length of `text`. `text` was filled by the workflow (data-model "Filling placeholders"); this read writes nothing. `injection_signals` comes from the job's keywords row (empty when none or not yet read).

### `POST /jobs/{job_id}/drafts` → `202`

```json
{"kind": "connection_request",
 "recipient": {"contact_id": "…"} | {"name": "Asha", "role": "Engineering Manager"},
 "recipient_kind": "hiring_manager",
 "regenerate": false}
```

Creates or reuses the draft for (job, kind, recipient). With an existing `ready` draft and `regenerate: false` → `200` with that draft (FR-008). Otherwise the row goes to `writing`, a worker task is queued, and the response is `202 {id, status: "writing"}`.

| Status | `reason` | When |
|---|---|---|
| 409 | `draft_in_progress` | the same draft is `writing` |
| 409 | `no_confirmed_profile` | spec FR-014 |
| 409 | `ai_unavailable` | provider status is rejected key or out of credit (message from the provider) |
| 404 | | unknown or deleted job, or a contact of another company |
| 422 | | bad kind, empty or too long name (> 120) or role (> 120) |

### `PUT /drafts/{draft_id}`

`{"text": "…"}` (1–2000 chars). Saves the person's edit, `edited = true`. A connection request over 200 is saved and returned with `"over_limit": true` (FR-011). `409` while `writing`.

### `DELETE /drafts/{draft_id}` → `204`

## Tailored resume

### `GET /jobs/{job_id}/tailored-resume`

`{id, status, paused_reason, document, keyword_match, source, edited, failure_reason, injection_signals, updated_at}` or `404 not_tailored`.

### `DELETE /jobs/{job_id}/tailored-resume` → `204`

Removes the job's tailored resume (spec FR-009, constitution VIII). `404 not_tailored`; `409 resume_in_progress` while writing.

### `POST /jobs/{job_id}/tailored-resume` → `202`

`{"regenerate": false}`. Like drafts. Extra refusal: `409 no_description` when the job's description is empty or under 200 characters (US4 scenario 7). The person pastes a description with `PUT /jobs/{id}/description` (below), then asks again.

### `PUT /jobs/{job_id}/tailored-resume`

`{"document": {…}}` (schema in data-model). Saves the edit, recomputes `keyword_match`, `edited = true`. `422` when the document fails its schema or size.

### `GET /jobs/{job_id}/tailored-resume.pdf` and `.docx`

Renders the saved document (research R8). `Content-Disposition: attachment; filename="<name> - <company> - <role>.pdf"` (cleaned to safe characters). `404` when there is no `ready` resume.

### `GET /tailored-resumes`

For the Profile page: `[{job_id, job_title, company, updated_at, source, edited}]`.

## Events (existing event stream)

| Event | Data |
|---|---|
| `draft.ready` / `draft.failed` | `{draft_id, job_id}` |
| `tailored_resume.ready` / `tailored_resume.failed` | `{job_id}` |

## Changes to existing endpoints

- **New** `PUT /jobs/{job_id}/description` (in `search`): `{"description": "…"}` (200–30 000 characters after the existing untrusted-text sanitizer). Replaces the stored description, which makes the job's keywords stale (R3). `404` unknown or deleted job, `422` too short or too long.
- `DELETE /jobs/{job_id}` also deletes the job's keywords, drafts and tailored resume (FR-009), through the registered job clean-up.
- No change to `POST /jobs/{id}/applied` or `/inquired`. The Explore row change is front end only (FR-001 to FR-003).

## Test matrix

| Test (name prefix) | Covers |
|---|---|
| `test_FR001_explore_row_shows_only_two_actions` (Vitest) | US1 AS1 |
| `test_FR002_details_record_resume_and_date` (Vitest) | US1 AS3, AS4 |
| `test_FR003_one_click_unchanged` (Vitest + existing 002e/002f API tests) | US1 AS2, AS5 |
| `test_US2_AS1_draft_for_contact_or_typed_recipient` | US2 AS1, FR-010 |
| `test_FR011_connection_request_at_most_200` | US2 AS2, SC-003 |
| `test_FR005_fabricated_number_skill_or_name_rejected` (domain) | US2 AS3, AS4, SC-004 |
| `test_US2_AS4_repair_then_fallback_template` | FR-007 |
| `test_FR014_no_profile_drafts_nothing` | US2 AS5 |
| `test_US2_AS6_ai_unavailable_reason_and_retry` | FR-007, SC-008 |
| `test_FR008_last_draft_kept_regenerate_on_request` | US2 AS7 |
| `test_FR012_pushy_referral_rejected` (domain) | US3 AS2, SC-005 |
| `test_FR006_description_instructions_have_no_effect` | US3 AS4 |
| `test_FR022_contacts_and_my_details_never_in_a_prompt` (recorded calls) | research R2, 002b FR-022 |
| `test_FR015_tailored_resume_keeps_every_fact` | US4 AS2 |
| `test_FR016_person_edits_kept` | US4 AS3 |
| `test_FR017_only_backed_keywords_match_recomputed` | US4 AS4 |
| `test_FR018_pdf_docx_same_text_single_column` | US4 AS5, SC-006 |
| `test_FR019_listed_and_linked_no_description_refused` | US4 AS6, AS7 |
| `test_FR009_job_delete_and_delete_all_remove_drafts` | FR-009, EC-09 |
| `test_FR009_delete_tailored_resume` | FR-009 |
| `test_FR006_injection_signals_returned_and_shown` | FR-006, EC-12 |
| `test_SC007_no_send` (existing architecture test, extended to `drafts`) | FR-004 |
| `test_FR020_calls_logged_with_prompt_and_model` | FR-020, research R1 |
