# REST API contract: Setup and Profile (first slice)

Base `http://127.0.0.1:8000/api/v1` · JSON · no auth (local only) · errors follow RFC 9457 `application/problem+json` with `type`, `title`, `detail` and, for validation errors, `errors: [{field, message}]`. The authoritative schema is FastAPI's generated OpenAPI. This file is the agreed contract it must match, and API tests are written from it. Shapes refer to [data-model.md](../data-model.md).

## Resumes and ingestion (profile)

| Method & path | Body → Response | Notes / requirement |
|---|---|---|
| `POST /resumes` | multipart `file` → `202 {resume_file_id, run_id}` | FR-001, FR-003. `415` for wrong type, `413` over 10 MB, `422` encrypted or corrupt. `409 {open_review_id}` when a review is open, unless `?discard_open_review=true` (edge case). |
| `POST /resumes/text` | `{text: str 200–60000}` → `202 {resume_file_id, run_id}` | FR-002. Same `409` rule. |
| `GET /resumes` | → `[ResumeFile]` | name, kind, size, created_at, parse_status, has_open_review. |
| `DELETE /resumes/{id}` | → `204` | FR-034. Cancels its open review or run. |

## Workflow runs (platform/runtime)

| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /runs/{id}` | → `{id, workflow, status, pause_reason, waiting_for, current_step, error, updated_at}` | progress (FR-013) |
| `POST /runs/{id}/decision` | `{decision: "continue_extraction" \| "manual_entry"}` → `202` | FR-007; only when `waiting_for = injection_decision`. |
| `POST /runs/{id}/retry` | → `202` | only when `status = failed` ("Try again"). |
| `GET /review-items` | → `[{kind: "profile_review" \| "injection_decision" \| "paused_run", run_id, review_id?, title, since}]` | FR-033, US3-AS6 |

## Profile reviews (profile)

| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /profile/reviews/{id}` | → `{id, status, extraction: ProfileContent, draft: ProfileContent \| null, dropped_items, flags: {hidden_text, injection_flags, truncated_at}, compare_to: ProfileContent \| null, changed_paths: [str], provenance}` | US1-AS1/3/4, FR-014/015 |
| `PUT /profile/reviews/{id}/draft` | `ProfileContent` (incomplete allowed; confirm rules not applied) → `200 {draft_saved_at}` | FR-016 autosave |
| `POST /profile/reviews/{id}/confirm` | `ProfileContent` → `202 {run_id}`, or `422` with confirm-rule errors | FR-017/018; resumes the run, which saves the version |
| `POST /profile/reviews/{id}/discard` | → `204` | cancels the run; the current profile is unchanged |

## Profile and versions (profile)

| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /profile` | → `{current_version: ProfileVersion \| null}` | FR-022 |
| `POST /profile/versions` | `ProfileContent` → `201 ProfileVersion`, or `422` | FR-019 manual create, FR-020 edit (`created_by` set by server) |
| `GET /profile/versions` | → `[{id, number, created_at, created_by, source_file: {id, name} \| null, source_deleted, is_current}]` | FR-021 |
| `GET /profile/versions/{id}` | → `ProfileVersion` | read-only |

`ProfileVersion` = `{id, number, created_at, created_by, source_file_id, source_deleted, content: ProfileContent}`.

## Preferences

| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /preferences` | → `{content: Preferences, saved_at: datetime \| null, suggestions: {target_roles: [str], key_skills: [str]}}` | US2-AS1/3. Defaults are returned when never saved; suggestions come from the current profile (most recent title, skills not already chosen). |
| `PUT /preferences` | `Preferences` → `200 {saved_at}`, or `422` with per-field errors | FR-023/025/026 |

## Setup: status, settings, data

| Method & path | Body → Response | Notes |
|---|---|---|
| `GET /status` | → `{ai: {provider: "openai", status, message, checked_at}, checklist: {key_ok, resume_uploaded, profile_confirmed, preferences_saved}, budget: {cap_usd, spent_usd, period: "YYYY-MM"}}` | FR-028/029/030. One call powers the banner and Home. **Never includes the key.** |
| `POST /status/ai/check` | → `202` | "Check again" (enqueues the key check) |
| `GET /settings` | → `{budget_cap_usd, spent_this_month_usd, tiers: [{tier, provider, model}], key_status}` | FR-031 (tiers read-only) |
| `PUT /settings` | `{budget_cap_usd: decimal 0–10000}` → `200` | Raising the cap re-queues budget-paused runs (R9). |
| `POST /data/delete-all` | `{confirm: "DELETE"}` → `204`, or `422` | FR-035 |

## Events (SSE)

`GET /events` (`text/event-stream`). Event types, each with JSON `data`:

| event | data | Used by |
|---|---|---|
| `run.updated` | `{run_id, workflow, status, current_step, pause_reason, waiting_for}` | progress, Review list |
| `status.updated` | `{ai_status}` | banner |
| `profile.updated` | `{current_version_id}` | Home checklist, Profile |

The client re-fetches through TanStack Query on each event. If the stream drops, it falls back to polling `GET /runs/{id}` every 3 s (ADR-08).
