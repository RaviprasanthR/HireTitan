# Research: Navigation and pipeline (002d)

## R1. Inquired as a job state, with its own date

- **Decision**: add `inquired` to the job state enum and an `inquired_on date` column. Transitions: `explore → inquired`, `skipped → inquired`, `inquired → applied`, `inquired → explore` (Undo), `inquired → deleted`. `applied → inquired` is not allowed (applying is the later step). DB checks: `(state = 'inquired') = (inquired_on IS NOT NULL)` next to the existing `applied_on` check, so moving on to applied clears the inquired date.
- **Rationale**: the job state already drives every list (Explore, Skipped, Applied) and the search's "seen again keeps its state" rule (`apply_found_again`), so a new state gets the right search behaviour for free (FR-008, SC-006). A separate flag table would duplicate that logic.
- **Alternatives**: a boolean `inquired` on `jobs` independent of state (two sources of truth); a generic `pipeline_on` column replacing `applied_on` (rewrites 002's applied code and data for no gain); keeping the inquired date after applying (YAGNI until feature 003's application history).

## R2. One pipeline list

- **Decision**: `GET /jobs?list=pipeline` returns jobs in `applied` or `inquired`, ordered by `coalesce(applied_on, inquired_on) desc, id`, keyset-paged like the Applied list. `list=applied` is replaced (the only caller is the frontend in this repo).
- **Rationale**: one table in the UI needs one query; the sort key is a date either way.
- **Alternatives**: two lists merged in the browser (paging breaks).

## R3. Marking and undo

- **Decision**: `POST /jobs/{id}/inquired` (`{inquired_on?}`, default the server's today; same two-year and no-future rules as applied, shared check) and `DELETE /jobs/{id}/inquired` (Undo: back to `explore`). `POST /jobs/{id}/applied` also accepts an inquired job. The use cases `mark_applied`/`undo_applied` move into `application/pipeline.py` with `mark_inquired`/`undo_inquired`. The frontend Undo notice (`appliedStore`) is generalised to either mark.
- **Rationale**: mirrors 002's applied API exactly, so the UI and tests reuse the same shapes (409 `already_inquired` / `not_inquired`, 422 on the date field).

## R4. Companies: pipeline flag

- **Decision**: replace 002b's `has_application: bool` with `pipeline: "applied" | "inquired" | null`, computed by one query (`AppliedCompaniesRepo` becomes `PipelineCompaniesRepo`: per company, `applied` if any job is applied, else `inquired` if any is inquired). The chip shows Applied or Inquired; the filter is "In pipeline"; the sort is Applied, Inquired, then the rest (clarification 2026-11-11).
- **Rationale**: one field carries both cases; no extra query.

## R5. Removing AI cost

- **Decision**: remove, in this order so every step stays green:
  1. **UI**: cost in the search panel, search summary and history, Profile page, setup screens, Settings budget and models.
  2. **API**: `ai_cost_usd` on search runs, `budget` in `GET /status`, the whole `/settings` router (`GET`, `PUT`), the budget review-item target.
  3. **Workflows**: the `budget_reached` search stop (`stops.py`, `graph.py`, `judge.py`, `pages.py`, `recheck.py`), the per-batch cost delta (`search.py`, `search_store.py`), the budget pause in profile ingest.
  4. **Platform**: `budget.py` (guard, token counter), the cost calculator and prices in `models.py` / `models.yaml` (tiers stay), cost fields in `Usage`, `LlmCallRecord`, `validation.py`, `calls_repo.py` (and `spent_in_month`), the `budget_blocked` outcome for new calls, `PauseReason.budget_reached`, `resume_paused`'s budget branch, `budget_cap_provider` in `worker_main.py` and `factory.py`; drop `tiktoken`.
  5. **Evals**: no cost estimate before a run (the `--yes` guard stays, because a run still uses the person's credit), no cost columns in new reports; token counts stay. `test_default_model` keeps its quality checks and loses any cost comparison. Old committed reports are history and stay as they are.
  6. **Tests**: `test_SC006_full_search_cost_under_limit` and the budget-guard, budget-pause and settings-budget tests are deleted; a new scan test asserts no API schema has a field whose name contains `cost`, `budget` or `spend`.
- **Rationale**: constitution IV (2.0.0). Removing from the outside in keeps each task's suite green and makes the final schema scan meaningful.
- **Alternatives**: keep the guard with an infinite cap (dead code and still against the constitution); hide the UI only (the constitution forbids estimating too).

## R6. Data already stored

- **Decision**: migration `0016` drops `settings.budget_cap_usd`, `llm_calls.cost_usd`, `llm_calls.estimated_cost_usd` and `search_runs.ai_cost_usd`. Runs with `status = 'paused' AND pause_reason = 'budget_reached'` become `failed` with the error "Paused by the old AI budget, which HireTitan no longer has. Start it again." before the pause-reason check drops `budget_reached`. The `llm_calls.outcome` check and the `search_runs.outcome` check keep `budget_blocked` / `budget_reached` as accepted legacy values (old rows), and no code writes them. The downgrade re-adds the columns (zeros, cap 25.00) and the check value; failed runs stay failed.
- **Rationale**: FR-014 (no run stuck paused); FR-013 (no cost recorded). Failing is deterministic in a migration; a failed profile run can be retried (001) and a failed search is replaced by a new search that continues with leftover companies (002).
- **Alternatives**: resume them from the worker at start (needs a one-off branch in runtime code that lives forever); keep the cost columns unused (the spec allows it, but dropping is cleaner and the data was unreliable).

## R7. Routes and redirects

- **Decision**: `/` Explore, `/pipeline` In pipeline (a tab bar above the list, both routes render the same Home shell). Profile: `/profile` (Profile tab), `/profile/preferences`, `/profile/search-rules`; existing `/profile/edit`, `/profile/review/:id`, `/profile/versions…` stay. Redirects (replace, so Back works): `/applied → /pipeline`, `/preferences → /profile/preferences`, `/search/rules → /profile/search-rules`. `/review` stays as a page with no menu entry. Internal links (setup checklist, AI banner) point at the new addresses.
- **Rationale**: the tab is part of the address (FR-001, FR-016), so reload and Back behave; React Router `Navigate` keeps redirects in one place.

## R8. Review notice on Home

- **Decision**: Home (both tabs) shows "N items need your review → Review" when `GET /review-items` returns any; it uses the same query the Review page uses, refreshed by the existing events.
- **Rationale**: no new API; review items are rare.

## R9. Duplicates merge keeps the pipeline state

- **Decision**: when two jobs are merged, the kept job takes the stronger state of the two (`applied` > `inquired` > anything else) with its date. Today the kept job's state wins even if the other was applied, which would lose an application.
- **Rationale**: spec edge case ("an inquired job merged as a duplicate keeps its status"); fixes the same gap for applied.
