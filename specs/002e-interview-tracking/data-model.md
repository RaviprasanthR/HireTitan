# Data model: Interview tracking (002e)

PostgreSQL 16, schema `app`. Migration `0018_interview_tracking` (parent `0017_no_cost`). All three tables are the person's own data: never read by a workflow or a prompt (research R10), removed by Delete all my data (it truncates every `app` table).

## `job_pipeline_details` (one row per job, created on first save)

The spec's two entities **Pipeline contact** and **Job source** are the columns of this one table.

| Column | Type | Rules |
|---|---|---|
| `job_id` | uuid, PK | FK `jobs.id` ON DELETE CASCADE |
| `contact_name` | text null | ≤ 120; required when any other contact field is set |
| `contact_role` | text null | ≤ 120 |
| `contact_email` | text null | ≤ 254; email form (002b check) |
| `contact_phone` | text null | 5-30 of digits, space, `+ ( ) -` (002b check) |
| `contact_linkedin` | text null | ≤ 500; `http`/`https` link (002b check) |
| `source` | text null | `direct` or `hiring_firm`; null = not set |
| `firm_name` | text null | ≤ 120 |
| `created_at`, `updated_at` | timestamptz | |

Checks:
- `ck_job_pipeline_details_source_values`: `source IS NULL OR source IN ('direct','hiring_firm')`.
- `ck_job_pipeline_details_firm_iff_hiring_firm`: `(source IS NOT DISTINCT FROM 'hiring_firm') = (firm_name IS NOT NULL)` (null-safe, so a firm name with no source is refused): a firm name exists exactly when the source is a hiring firm (switching to Direct clears it).
- `ck_job_pipeline_details_contact_has_name`: `contact_name IS NOT NULL OR (contact_role, contact_email, contact_phone, contact_linkedin) all NULL`.

## `interview_rounds`

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | UUIDv7 like the other tables |
| `job_id` | uuid | FK `jobs.id` ON DELETE CASCADE; index |
| `number` | int | ≥ 1; unique with `job_id` (`uq_interview_rounds_job_number`) |
| `kind` | text | `screening`, `technical`, `hr`, `managerial`, `other` |
| `scheduled_at` | timestamptz null | any instant, past allowed |
| `interviewers` | text null | ≤ 300, free text ("Asha (EM), Ben") |
| `state` | text | `scheduled` (default), `cleared`, `failed` |
| `feedback` | text null | ≤ 10,000, line breaks kept |
| `created_at`, `updated_at` | timestamptz | |

Checks: `ck_interview_rounds_kind_values`, `ck_interview_rounds_state_values`, `ck_interview_rounds_number_positive`.

## `interview_questions`

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `round_id` | uuid | FK `interview_rounds.id` ON DELETE CASCADE; index |
| `position` | int | ≥ 1; order shown; new = max + 1; gaps allowed after delete |
| `question` | text | required, ≤ 2,000 |
| `answer` | text null | ≤ 10,000 |
| `created_at`, `updated_at` | timestamptz | |

## State and rules

Round state: `scheduled ⇄ cleared ⇄ failed` (any to any; the person corrects mistakes, US2 AS5).

Job-level rules (pure, `search/domain/interviews.py`):

- `next_round_number(numbers) = max(numbers, default=0) + 1` (R3).
- `can_add_round(states) = 'failed' not in states` (R5, FR-006).
- `status_summary(job_state, rounds)` (R4, FR-007):
  - any failed → `("failed", N)` with N the highest failed number;
  - else rounds exist → `(state of the highest number, that number)`;
  - else → `(job_state, None)` (`applied` or `inquired`).
- Writes need `job_state in {applied, inquired}` (R6).

Lifecycle (R7):
- Undo applied or inquired: details untouched.
- Delete job (soft): details deleted in the same transaction.
- Merge: winner keeps its own; loser's contact and source fill only empty winner fields; loser's rounds move only if the winner has none (renumbered 1..n by their number order, questions move with them); the rest of the loser's details are deleted.
- Delete all my data: truncated with every `app` table.

## API shape added to the job list

`JobCardOut` gains `interview: {state: "scheduled"|"cleared"|"failed", round: int} | null` (null when the job has no rounds). The pipeline list reads it with one lateral sub-query per page, not per row.
