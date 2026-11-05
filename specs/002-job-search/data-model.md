# Data Model: Job Search and Home Page List (002)

All tables live in the `app` schema of the existing PostgreSQL 16 database. They follow 001's conventions: UUIDv7 primary keys, `created_at` and `updated_at` timestamps, named constraints (`ck_…`, `uq_…`, `fk_…`, `ix_…`), and SQLAlchemy models in `search/infra/models.py`. All tables are owned by the new **`search`** module. Migrations: `0012_search` (tables) and `0013_search_seed_version` if needed. Pure domain types are in `search/domain/`.

## Entities

### Company (`companies`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| key | text, nullable | Stable slug for built-in rows (`devrev`); unique when not null; null for rows the person adds |
| origin | text | `built_in` \| `user` |
| name | text | 1–120 chars |
| city | text, nullable | ≤ 80 |
| website | text, nullable | http(s) URL ≤ 500 |
| careers_url | text, nullable | http(s) URL ≤ 500 |
| ats_vendor | text, nullable | one of the enabled career-ops providers (research R2), else null |
| board_id | text, nullable | ≤ 200; required when `ats_vendor` is set |
| resolution | text | `verified` (maintainer) \| `user_confirmed` \| `unresolved` \| `careers_page` \| `check_manually` |
| hidden | bool | default false; hidden companies are never fetched (US3 AS4) |
| user_modified | bool | set on any edit by the person; the seed loader never updates such rows (FR-018) |
| deleted_at | timestamptz, nullable | tombstone for built-in rows the person deleted (so they are not re-seeded); user rows are hard-deleted |
| seed_version | int, nullable | version of the shipped list that last wrote the row |
| last_checked_at | timestamptz, nullable | set when a search reads the company |
| last_check_result | text, nullable | `ok` \| `failed` \| `no_jobs` \| `blocked` (robots.txt) \| `unreadable` |
| last_check_error | text, nullable | ≤ 300 chars, shown to the person |

Rules: only `origin = user` rows may be hard-deleted (FR-016). A company is **readable** when it is not hidden and not deleted, and either `ats_vendor` is set and enabled, or `resolution = careers_page`. The **check-manually list** is the companies with `resolution = check_manually`, or `last_check_result` in (`blocked`, `unreadable`).

### Search rule set (`search_rule_sets`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| version | int | increasing, unique |
| status | text | `proposed` \| `approved` \| `superseded` |
| rules | jsonb | a `SearchRules` document (below), validated on write |
| based_on | jsonb | `{profile_version_id, preferences_updated_at}`, used to detect "profile or preferences changed" (FR-006) |
| approved_at | timestamptz, nullable | set when approved |

At most one `approved` row, enforced by a partial unique index. A new proposal never changes the approved row until the person approves it (US2 AS4).

`SearchRules` (pure domain dataclass and Pydantic schema):

| Field | Kind | Effect | Limits |
|---|---|---|---|
| `title_words` | list of `{text, origin}` | **skip** if the title matches none of these or their synonyms | 1–30 items, each ≤ 60 chars |
| `title_avoid` | list of `{text, origin}` | **skip** if the title contains one | ≤ 30 |
| `blocked_locations` | list of `{city, country, origin}` | **skip** if the job's city or country matches (alias-aware) | ≤ 30 |
| `max_age_days` | int | **skip** if `posted_at` is older (no date → never skipped) | 1–365, default 30 |
| `stack_keywords` | list of `{text, origin}` | **guides the AI** | ≤ 50 |
| `preferred_locations` | list of `{city, country, origin}` | guides the AI | ≤ 30 |
| `work_modes` | set of `onsite` / `hybrid` / `remote` | guides the AI | |
| `seniority` | list | guides the AI | |
| `years_experience` | decimal, nullable | guides the AI | 0–50 |

`origin` is one of `preference:<field>`, `profile:<field>`, `synonym_table` or `user` (FR-002). Synonyms come from `backend/seed/title_synonyms.yaml` and are expanded when a rule is applied, not stored.

### Search run (`search_runs`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| workflow_run_id | uuid | FK → `workflow_runs.id` (001 runtime); the run's state machine and events |
| rule_set_id | uuid | FK → `search_rule_sets.id` (the approved set when the search started) |
| mode | text | `rules_and_ai` \| `rules_only` |
| outcome | text, nullable | `finished` \| `stopped_by_user` \| `budget_reached` \| `out_of_credit` \| `failed`; null while running |
| stop_message | text, nullable | ≤ 300; for `out_of_credit` the provider's message (sanitized) |
| company_order | uuid[] | companies planned for this run, in order |
| next_index | int | the first company not yet read; the next search continues from `company_order[next_index:]` (FR-010a) |
| stop_requested | bool | set by the Stop button; checked between batches |
| batches_done | int | |
| jobs_found / skipped_by_rules / judged_by_ai / kept / added / merged / not_checked_by_ai | int | summary counts (FR-008) |
| ai_cost_usd | numeric(10,4) | the sum of this run's `llm_calls` cost, updated per batch |
| started_at / finished_at | timestamptz | |

At most one search is active at a time (FR-009). A partial unique index on `workflow_runs (workflow) WHERE workflow = 'job_search' AND status IN ('queued','running','paused')` enforces this, and the API maps a conflict to `409`.

### Search run company (`search_run_companies`)

`(search_run_id, company_id)` PK; `batch_no` int; `result` (`ok` \| `failed` \| `no_jobs` \| `blocked` \| `unreadable`); `jobs_found` int; `error` text ≤ 300. Feeds the per-company part of the summary and the search history (FR-042).

### Job (`jobs`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| company_id | uuid, nullable | FK → companies (ON DELETE SET NULL); pasted jobs may have none |
| company_name | text | as shown; ≤ 120 |
| title | text | sanitized; 1–200 |
| location_text | text, nullable | as posted; ≤ 200 |
| city / country | text, nullable | parsed by rules; never guessed (FR-027) |
| work_mode | text, nullable | `onsite` \| `hybrid` \| `remote` when stated |
| posted_at | timestamptz, nullable | |
| first_seen_at / last_seen_at | timestamptz | |
| sort_key | timestamptz | generated: `coalesce(posted_at, first_seen_at)` |
| description | text | sanitized, ≤ 30,000 chars (constitution III) |
| pay_text | text, nullable | as posted; never guessed |
| skills_found | text[] | stack keywords found by rules in title and description (used in the job card) |
| years_found | numeric, nullable | years of experience parsed by rules |
| canonical_url | text, nullable | unique when not null (exact dedup, R8) |
| ats_vendor / requisition_id | text, nullable | unique pair when both are set |
| state | text | `explore` \| `skipped` \| `applied` \| `deleted` (see transitions) |
| restored | bool | the person restored it; later searches keep it in Explore (FR-025) |
| applied_on | date, nullable | set with `state = applied` (FR-036) |
| listed | bool | false when the source no longer lists it ("no longer listed") |
| injection_flags | jsonb | screening results shown on the job (FR-038) |

Indexes: `ix_jobs_state_sort (state, sort_key DESC, id)` for Explore and Applied paging (SC-010); `ix_jobs_company (company_id)`.

**State transitions**

```text
(new job) ──rules skip──────────────▶ skipped
    │ ──AI not relevant──────────────▶ skipped
    │ ──rules pass + AI relevant─────▶ explore
    │ ──AI unavailable / unusable────▶ explore   (decision "not checked by AI")
    └ ──pasted by the person─────────▶ explore   (decision "added by you", no AI)
skipped ──person restores──▶ explore (restored = true)
explore ──person: I applied──▶ applied (applied_on)
applied ──person: undo──────▶ explore
explore | skipped | applied ──person deletes──▶ deleted (row kept as a tombstone so a later search does not re-add it; purged by delete-all)
```

A job found again by a later search keeps its state and decision. Only `last_seen_at`, `listed = true` and the new source are updated (US1 AS6, FR-026).

> "Not checked by AI" places the job in **Explore**, not skipped. The rules already passed it, and the spec says a fact the AI could not judge must not hide a job. The decision row says so, and the person can ask to re-check.

### Job source (`job_sources`)

`id`; `job_id` FK (cascade); `kind` (`company_board` \| `careers_page` \| `paste`); `url` text ≤ 1000; `search_run_id` nullable FK; `seen_at`. Unique `(job_id, kind, url)`. A job can have several sources (FR-020).

### Relevance decision (`relevance_decisions`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| job_id | uuid | FK (cascade) |
| outcome | text | `shown` \| `skipped` |
| decided_by | text | `rule` \| `ai` \| `person` \| `rules_only_fallback` |
| reason | text | 1–200 chars, always present (SC-005) |
| rule_key | text, nullable | e.g. `blocked_locations`, `title_words` |
| search_run_id | uuid, nullable | |
| prompt_name / prompt_version / provider / model | text, nullable | set for `ai` (constitution IV provenance) |
| llm_call_id | uuid, nullable | FK → `llm_calls` |
| is_current | bool | exactly one current decision per job (partial unique index) |

History is kept. Restore, apply and re-check add a new current row.

### Possible duplicate (`possible_duplicates`)

`id`; `job_a_id`, `job_b_id` (FK, cascade; stored with `job_a_id < job_b_id`; unique pair); `similarity` numeric; `status` (`open` \| `merged` \| `dismissed`); `decided_at`. Merging moves B's sources onto A and marks B `deleted` (FR-021).

## Changes to feature 001 tables and types

| Where | Change |
|---|---|
| `platform/llm/port.py` | `PAUSE_REASONS` gains `out_of_credit`; `AiUnavailable` carries an optional `provider_message` (≤ 300, sanitized) (R7) |
| `workflow_runs` | allowed `pause_reason` values gain `out_of_credit` (check constraint, migration `0012`); `workflow` value `job_search` |
| `setup` delete-all | calls the new `search.application.delete_all()`: truncates the search tables, deletes user companies, clears tombstones and edits, and re-runs the seed loader so the shipped list is back to its original state (FR-041, SC-013) |
| `setup` status/checklist | gains `rules_approved` and `searched_once`, used by Explore's empty and setup states (US1 AS10–11) |

## Validation summary (from the requirements)

- A search needs an approved rule set (FR-004), a confirmed profile and saved preferences (US1 AS11). Otherwise `409` with the missing step.
- Only one active search (FR-009) → `409 search_already_running`.
- A paste needs a URL (http/https, ≤ 1000) and a description (50–30,000 chars) (US4 AS4) → `422` with field errors.
- `applied_on` must not be in the future and not more than 2 years ago → `422`.
- CSV import: at most 1 MB and 2,000 rows; per-row errors are returned in the preview (R11).
- All text from sources and pastes passes the 001 untrusted pipeline (sanitize, screen) before storage; screening flags are stored on the job (FR-038).
