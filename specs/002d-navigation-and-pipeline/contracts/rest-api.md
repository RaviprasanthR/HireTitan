# REST API contract: Navigation and pipeline (002d)

Changes to 001, 002 and 002b's contracts. Base path `/api/v1`. Errors are RFC 7807 problem documents; field errors are `422` with `errors: [{field, message}]`.

## Jobs

| Endpoint | Request → Response | Notes |
|---|---|---|
| `GET /jobs?list=explore\|pipeline` | → `200 {items: JobCard[], next_cursor}` | **`pipeline`** (new, replaces `applied`): jobs in `applied` or `inquired`, newest `applied_on`/`inquired_on` first, keyset-paged |
| `POST /jobs/{id}/inquired` | `{inquired_on?: date}` → `200 JobDetail` | **New.** From `explore` or `skipped`. No body: the server's today. `422` field `inquired_on` (future, or more than two years ago); `409 already_inquired`; `409 already_applied` (an applied job cannot be marked inquired) |
| `DELETE /jobs/{id}/inquired` | → `200 JobDetail` | **New.** Undo: back to `explore`. `409 not_inquired` |
| `POST /jobs/{id}/applied` | `{applied_on?: date}` → `200 JobDetail` | Now also accepted from `inquired` (clears `inquired_on`) |
| `JobCard`, `JobDetail` | | `state` may be `inquired`; new field `inquired_on: date \| null` |

## Companies

| Endpoint | Change |
|---|---|
| `GET /companies` | `Company.has_application: bool` is replaced by **`pipeline: "applied" \| "inquired" \| null`** |

## Search runs

| Endpoint | Change |
|---|---|
| `GET /search/runs/{id}`, `GET /search/runs`, `GET /search/runs/latest` | `ai_cost_usd` **removed**. `outcome` never becomes `budget_reached` for new runs (old runs may still carry it). Event `search.batch_done` loses its cost field |

## Setup and settings

| Endpoint | Change |
|---|---|
| `GET /status` | `budget` **removed**; `ai` (key status, out-of-credit message) and `checklist` unchanged |
| `GET /settings`, `PUT /settings` | **Removed.** The key status comes from `GET /status`; Delete all stays at `POST /data/delete-all` |
| `GET /review-items` | Unchanged shape; no item ever points to a budget pause |

## Never in any response

No field whose name contains `cost`, `budget`, `spend` or `price` (checked by a schema scan test over `openapi.json`).

## Test matrix (names reference requirement and scenario IDs)

| Test file | Test names | Covers |
|---|---|---|
| `unit/search/test_job_state.py` | `test_US2_AS1_explore_and_skipped_can_become_inquired`, `test_US2_AS2_inquired_can_become_applied`, `test_FR007_applied_cannot_become_inquired`, `test_US2_AS3_undo_inquired_returns_to_explore` | state machine |
| `api/search/test_pipeline_api.py` | `test_US1_AS2_pipeline_lists_applied_and_inquired_newest_first`, `test_US2_AS1_mark_inquired_defaults_to_today`, `test_US2_AS5_inquired_date_rules`, `test_US2_AS3_undo_inquired`, `test_FR007_applied_job_cannot_be_inquired_409`, `test_US2_AS2_inquired_then_applied` | jobs API |
| `workflow/search/test_inquired_kept.py` | `test_SC006_search_again_keeps_inquired_jobs` | search |
| `api/search/test_duplicates_api.py` | `test_R9_merge_keeps_the_stronger_pipeline_state` | merge |
| `api/search/test_companies_api.py` | `test_FR009_company_pipeline_is_applied_inquired_or_null` | companies |
| `integration/test_migration_0016.py` | `test_FR014_budget_paused_runs_become_failed`, `test_migration_0016_up_down_up` | migration |
| `architecture/test_no_cost_fields.py` | `test_SC003_no_cost_budget_or_spend_field_in_the_api`, `test_FR011_no_budget_guard_in_the_llm_stack` | no cost |
| `workflow/search/test_stops.py` | `test_FR012_out_of_credit_still_pauses_and_resumes`, `test_SC004_no_budget_stop_however_much_was_used` | stops |
| frontend (Vitest) | Home tabs and redirects, I inquired with Undo, pipeline table, menu has four entries, review notice, Profile tabs and redirects, Settings shows key and delete only, no cost text on any page | UI |
| `frontend/e2e/*.spec.ts` | journeys follow the new menu; job search adds inquire → apply → In pipeline; no cost text | journeys |
