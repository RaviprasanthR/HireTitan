# Data Model: Navigation and pipeline (002d)

## Job state (changed)

| State | Meaning | Date column |
|---|---|---|
| `explore` | in the Explore list | — |
| `skipped` | left out by the rules or the AI, restorable | — |
| `inquired` | **new**: the person asked about the job, has not applied | `inquired_on` (new) |
| `applied` | the person applied | `applied_on` |
| `deleted` | tombstone, so a later search does not add it again | — |

In pipeline = `inquired` or `applied`.

### Transitions

| From \ To | explore | skipped | inquired | applied | deleted |
|---|---|---|---|---|---|
| explore | — | yes (AI recheck) | **yes** | yes | yes |
| skipped | yes (restore) | — | **yes** | yes | yes |
| inquired | **yes (Undo)** | no | — | **yes** | **yes** |
| applied | yes (Undo) | no | **no** | — | yes |
| deleted | no | no | no | no | — |

Date rules for `inquired_on`, as for `applied_on`: defaults to the server's today; not in the future; not more than two years ago. Moving to any state other than `inquired` clears `inquired_on`; moving to any state other than `applied` clears `applied_on`.

A later search that finds the job again keeps its state and dates (002's `apply_found_again`, unchanged).

A duplicate merge gives the kept job the stronger of the two states, `applied` > `inquired` > others, with that job's date (research R9).

## Company list row (changed)

`has_application: bool` (002b) is replaced by `pipeline: "applied" | "inquired" | null`: `applied` when any job at the company is applied, else `inquired` when any is inquired, else `null`. Derived at read time with one query; nothing stored.

## Removed

| Where | What |
|---|---|
| `app.settings` | `budget_cap_usd` and its check `budget_cap_non_negative` |
| `app.llm_calls` | `cost_usd`, `estimated_cost_usd` (the `budget_blocked` outcome stays accepted for old rows; no code writes it) |
| `app.search_runs` | `ai_cost_usd` (the `budget_reached` outcome stays accepted for old rows; no code writes it) |
| `app.workflow_runs` | `budget_reached` as a pause reason |
| `platform/llm/models.yaml` | prices and `prices_checked_on` (tiers stay) |

## Migrations

Two migrations, so every task leaves the suite green: the ORM models stop using the cost columns before `0017` drops them.

**`0016_inquired`** (foundational):

1. `jobs`: add `inquired_on date NULL`; widen the state check to include `inquired`; add check `inquired_on_iff_inquired`: `(state = 'inquired') = (inquired_on IS NOT NULL)`.

**`0017_no_cost`** (after the cost code is gone), in one transaction:

1. `workflow_runs`: rows with `status = 'paused' AND pause_reason = 'budget_reached'` become `status = 'failed'`, `pause_reason = NULL`, `error = 'Paused by the old AI budget, which HireTitan no longer has. Start it again.'`; then the pause-reason check drops `budget_reached`.
2. Drop `settings.budget_cap_usd` (and its check), `llm_calls.cost_usd`, `llm_calls.estimated_cost_usd`, `search_runs.ai_cost_usd`.

Downgrades: `0017` re-adds the dropped columns (`budget_cap_usd` default 25.00, costs default 0) and `budget_reached` in the pause-reason check (failed runs stay failed); `0016` moves any `inquired` job back to `explore`, drops `inquired_on` and its check and narrows the state check.

The model/migration drift test from 001 covers the new column and checks.
