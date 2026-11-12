# Research: Interview tracking (002e)

Each decision: what was chosen, why, and what else was considered. No open questions remain.

## R1. Where the code lives

- **Decision**: extend the `search` module (next to jobs, the pipeline marks and 002b's contacts): `search/domain/interviews.py` (pure checks and the status rule), `search/application/interviews.py` (use cases), `search/api/interviews.py` (routes), tables in `search/infra/models.py`, repos in `search/infra/repos.py`.
- **Rationale**: the details have no meaning without a job in the pipeline and share its lifecycle (delete, merge, undo). 002b made the same call for company contacts.
- **Alternatives**: a new `interviews` module (needs cross-module wiring to read jobs, for no gain; constitution VI).

## R2. Three tables, not one JSON column

- **Decision**: `job_pipeline_details` (one row per job: contact and source), `interview_rounds` (one row per round), `interview_questions` (one row per question, ordered by `position`).
- **Rationale**: FR-009 and SC-005 ask that every item be queryable by field ("technical rounds that failed", "hiring firm vs direct"). Columns with check constraints give that directly and keep the database honest (state and type values, firm name present when the source is a hiring firm).
- **Alternatives**: one JSONB document per job (simple to save, but analytics would parse JSON and the database could not enforce the rules); contact and source in `jobs` itself (widens a hot table used by every search for data most jobs never have).

## R3. Round numbers

- **Decision**: a new round gets `max(number) + 1` for that job (1 when none); a unique key `(job_id, number)`. Deleting a round never renumbers the others. If the latest round is deleted, the next round added reuses its number.
- **Rationale**: matches US2 AS3 and AS6: numbers follow the order added and stay stable for the person's notes. Reusing the top number after deleting it is what the person expects ("I deleted round 3 by mistake, add it again").
- **Alternatives**: a sequence that never reuses numbers (a deleted round 3 would leave the next one as round 4, which reads as a gap); renumbering after delete (breaks references in the person's own notes).

## R4. The Status column is derived, not stored

- **Decision**: the status is computed when the pipeline list is read: if any round is Failed, "Failed in round N" (N = the highest failed round); else the highest-numbered round's state ("Round N scheduled" or "Round N cleared"); else Applied or Inquired. The list query adds the summary with one lateral sub-query; the rule itself is a pure function in `search/domain/interviews.py`, used by both the API response and its tests.
- **Rationale**: nothing to keep in sync when a round is edited or deleted (US2 AS5, AS6); one query, no per-row lookup.
- **Alternatives**: a stored `interview_status` column on `jobs` (must be updated on every round change; drift risk).

(Spec FR-007 states the same rule since the 2026-11-12 analysis.)

## R5. Failed blocks new rounds

- **Decision**: adding a round when any round of the job is Failed returns 409 `process_failed`; editing or deleting rounds and questions stays allowed. Changing the failed round back to Scheduled or Cleared lifts the block (US2 AS4, AS5).
- **Rationale**: the spec's rule, enforced in the use case (pure check in the domain) and shown in the UI by disabling **Add round** with the reason.
- **Alternatives**: a database trigger (harder to test and to explain, constitution VI).

## R6. Only pipeline jobs take new details

- **Decision**: writes (contact, source, add round, add question) require the job to be applied or inquired; otherwise 409 `not_in_pipeline`. Reads work in any state. Undoing a mark does not touch the details (FR-011, SC-006).
- **Rationale**: details are for jobs in motion; keeping them on undo means an accidental undo loses nothing.
- **Alternatives**: deleting details on undo (loses data on a mis-click, which the spec forbids).

## R7. Deleting and merging jobs

- **Decision**: jobs are soft-deleted (`state = 'deleted'`), so the foreign keys' `ON DELETE CASCADE` alone does not fire. `delete_job` therefore deletes the job's details in the same transaction (FR-011). The duplicate merge (002's `duplicates.py`) moves the loser's contact and source to the winner only where the winner has none, moves the loser's rounds only when the winner has no rounds (renumbering them 1..n in their order), and then deletes what is left on the loser (FR-012, edge case 1). Cascades still exist for a hard delete (Delete all my data truncates every table anyway).
- **Rationale**: matches the spec's "no silent overwrite"; mixing two sets of rounds would make the numbering meaningless.
- **Alternatives**: merging rounds from both jobs (the person would get two round 1s).

## R8. Date and time

- **Decision**: `scheduled_at` is `timestamptz`, optional. The browser sends an ISO date-time with its offset (from a `datetime-local` input converted to an instant); the UI shows it in local time. Past values are allowed on any state (US2 AS8).
- **Rationale**: an interview is an instant; storing UTC with the offset avoids day shifts across time zones.
- **Alternatives**: a date only (the person asked for date and time); a naive local time (wrong after a time-zone change).

## R9. Text limits and cleaning

- **Decision**: reuse 002b's `clean()` (001's sanitizer: control characters removed, surrounding space trimmed, empty becomes null) and its email, phone and LinkedIn checks. Limits: name, role, firm 120; interviewers 300; question 2,000; answer and feedback 10,000. Line breaks are kept (the sanitizer keeps `\n`; a test pins it). The UI shows the limit as a counter near the end (FR-014).
- **Rationale**: same rules the person already meets on company contacts; long answers fit (several paragraphs).
- **Alternatives**: no limit (an accidental paste of a whole document would bloat the list).

## R10. Privacy guard

- **Decision**: add `hiretitan.search.domain.interviews` and `hiretitan.search.application.interviews` to the import-linter contract `contacts-stay-out-of-ai-paths`; extend 002b's privacy test so a search runs with interview data present and asserts no recorded AI call contains any of its text; the no-send architecture test already scans every module.
- **Rationale**: FR-010, SC-003 and constitution I and VIII, enforced by the build, not by care.
- **Alternatives**: a code-review rule only (not enforced).

## R11. Saving in the UI

- **Decision**: each section has its own form and **Save** button: Contact and source together, then each round, then each question pair inline. Collapsing a row with unsaved edits asks first; leaving the page asks first (`useBlocker`). TanStack Query key `['job-interview', jobId]`; saving invalidates it and `['jobs']` (the Status column).
- **Rationale**: FR-013; small saves keep a failed save from losing other sections.
- **Alternatives**: autosave on blur (hard to show errors per field; nothing in HireTitan saves by itself today).

## R12. Analytics readiness

- **Decision**: no stats page. A repo method `InterviewsRepo.rounds_matching(kind=None, state=None, source=None)` exists for the SC-005 test and the later analytics feature.
- **Rationale**: proves the data can be queried by field without adding screens the spec leaves out.
- **Alternatives**: an export endpoint now (out of scope; feature 003 brings "Export all my data").
