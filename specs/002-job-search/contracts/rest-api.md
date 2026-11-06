# REST API contract: Job Search (002)

Base path `/api/v1`. Bound to localhost; no auth (one user per install). Errors use RFC 9457 `application/problem+json`, as in 001; validation errors carry `errors: [{field, message}]`. Lists are **keyset-paged**: `?limit=25&cursor=<opaque>` → `{items, next_cursor}` (`limit` 1–100, default 25). The OpenAPI document is generated from the routers, and the frontend types are regenerated from it (`npm run gen:api`).

## Search rules (US2)

| Method and path | Request → Response | Notes |
|---|---|---|
| `GET /search/rules` | → `200 {approved: RuleSet \| null, proposal: RuleSet \| null, stale: bool}` | `stale` = profile or preferences changed since the approved set was based on them (FR-006) |
| `POST /search/rules/proposal` | → `201 RuleSet` (status `proposed`) | Deterministic proposal from the confirmed profile and preferences (R9); `409` if there's no confirmed profile or no preferences |
| `PUT /search/rules/proposal` | `SearchRules` → `200 RuleSet` | Save the person's edits to the proposal; `422` with field errors on limits |
| `POST /search/rules/proposal/approve` | → `200 RuleSet` (status `approved`) | The previous approved set becomes `superseded` |
| `DELETE /search/rules/proposal` | → `204` | Discard the proposal; the approved set is unchanged |

`RuleSet = {id, version, status, rules: SearchRules, based_on, approved_at}`. Each rule item carries `origin` and `effect` (`skips` \| `guides_ai`) (FR-002, FR-005).

## Search runs (US1)

| Method and path | Request → Response | Notes |
|---|---|---|
| `POST /search/runs` | `{mode: "rules_and_ai" \| "rules_only"}` → `202 {search_run_id, run_id}` | Starts at once, with no cost confirmation (FR-010). `409 rules_not_approved`, `409 setup_incomplete`, `409 search_already_running` (FR-009). With no usable AI key, `rules_and_ai` runs as rules only and says so in the summary (US1 AS7) |
| `POST /search/runs/{id}/stop` | → `202` | Sets `stop_requested`; the run stops after the current batch (US1 AS9); `409` if not running |
| `GET /search/runs/{id}` | → `200 SearchRunOut` | Live counts, `ai_cost_usd`, `batches_done`, `companies_total`, `companies_read`, `outcome`, `stop_message`, per-company results |
| `GET /search/runs` | → `200 {items: SearchRunSummary[], next_cursor}` | Search history (FR-042), newest first |
| `GET /search/runs/{id}/skipped` | → `200 {items: JobCard[], next_cursor}` | Jobs skipped in this run, each with its reason (FR-025) |
| `GET /search/latest` | → `200 SearchRunSummary \| null` | For the home page header (FR-031) |

Progress events go over the existing SSE stream (`/api/v1/events`): `search.batch_done {search_run_id, batches_done, companies_read, added, ai_cost_usd}` and `search.finished {search_run_id, outcome, stop_message}`.

## Jobs (US1, US4, US5)

| Method and path | Request → Response | Notes |
|---|---|---|
| `GET /jobs?list=explore\|applied&source=&company_id=&work_mode=&city=&sort=newest\|company` | → `200 {items: JobCard[], next_cursor}` | Explore = `state = explore`; Applied = `state = applied`, ordered by `applied_on` desc (FR-029, FR-030, FR-037) |
| `GET /jobs/{id}` | → `200 JobDetail` | Full description, sources with links, current decision and history, the search that first found it, injection flags (FR-032) |
| `POST /jobs/paste` | `{url, description, title?, company?}` → `201 JobDetail` or `200 JobDetail` with `merged_into` | Untrusted pipeline; deduplicated (R8); goes to Explore with "added by you" (FR-033); `422` with field errors (US4 AS4) |
| `POST /jobs/{id}/restore` | → `200 JobDetail` | skipped → explore, `restored = true` (FR-025) |
| `POST /jobs/{id}/recheck` | → `202 {run_id}` | Re-judge one job with the AI (for "not checked by AI"); budget and credit rules apply |
| `POST /jobs/{id}/applied` | `{applied_on?: date}` → `200 JobDetail` | explore/skipped → applied; default today; `422` if in the future or more than 2 years ago (FR-036) |
| `DELETE /jobs/{id}/applied` | → `200 JobDetail` | Undo: applied → explore (US5 AS3) |
| `DELETE /jobs/{id}` | → `204` | Person deletes a job (tombstone, FR-041) |
| `GET /jobs/duplicates?status=open` | → `200 {items: DuplicatePair[], next_cursor}` | |
| `POST /jobs/duplicates/{id}/merge` · `/dismiss` | → `200 DuplicatePair` | FR-021 |

`JobCard = {id, title, company_name, location_text, work_mode, posted_at, first_seen_at, sources: [{kind, url}], decision: {outcome, decided_by, reason}, listed, applied_on}`.

## Companies (US3)

| Method and path | Request → Response | Notes |
|---|---|---|
| `GET /companies?filter=all\|check_manually\|hidden` | → `200 {items: Company[], next_cursor}` | FR-016, FR-019 |
| `POST /companies` | `{name, careers_url, city?, website?}` → `201 Company` (unresolved, not read) | Board discovery (R12) runs while the person waits on `GET .../discovery`, not as a queued workflow, so there is no `discovery_run_id` |
| `GET /companies/{id}/discovery` | → `200 {status, suggestion: {ats_vendor, board_id, live_jobs} \| null}` | |
| `POST /companies/{id}/discovery/confirm` · `/reject` | → `200 Company` | Confirm → `user_confirmed`; reject → careers-page route or `check_manually` (FR-017) |
| `PATCH /companies/{id}` | partial `{name, city, website, careers_url, hidden}` → `200 Company` | Sets `user_modified` (FR-018) |
| `DELETE /companies/{id}` | → `204` | User rows: hard delete. Built-in rows: tombstone (`deleted_at`) |
| `POST /companies/import` | multipart CSV → `200 ImportPreview {add[], update[], invalid[{row, reason}], token}` | ≤ 1 MB, 2,000 rows (R11); nothing changes yet |
| `POST /companies/import/{token}/confirm` | → `200 {added, updated}` | |
| `GET /companies/export` | → `200 text/csv` | Same columns; round-trips through import |

## Changes to 001 endpoints

| Endpoint | Change |
|---|---|
| `GET /status` | `checklist` gains `rules_approved`, `searched_once`; the AI status gains reason `out_of_credit` with `provider_message` |
| `GET /runs/{id}` | `pause_reason` may be `out_of_credit` |
| `DELETE /data` (delete all) | also clears search data and re-seeds the shipped company list (SC-013) |
