# Research: Resume picker

Phase 0 decisions for [plan.md](plan.md). No `NEEDS CLARIFICATION` remained in the Technical Context; the spec's four clarifications (2026-11-15) fixed the behaviour, so this file records the design choices.

## R1. Where the choice is stored

- **Decision**: three nullable columns on 002e's `job_pipeline_details` row: `resume_file_id` (foreign key to `app.resume_files(id)`, `ON DELETE SET NULL`), `resume_name` and `resume_added_on` (copied from the file when the person chooses it).
- **Rationale**: the row already holds the person's other per-job pipeline notes, is joined into the pipeline list by 002e's lateral sub-query, is removed with the job, carried by the duplicate merge, kept out of AI paths by contract and emptied by Delete all. One more table would repeat all of that.
- **Alternatives considered**: a `job_resume` link table (more joins, same lifecycle code again); a column on `jobs` (jobs is 002's search table, and the choice only exists for pipeline jobs).

## R2. Removed files keep their name (spec clarification 2)

- **Decision**: the foreign key is `ON DELETE SET NULL`; the snapshot columns stay. Display rule (pure, `search/domain/resume_choice.py`): `resume_file_id` set → **chosen** (name, added day); `resume_file_id` null and `resume_name` set → **removed** note; both null → **none**.
- **Rationale**: removing a file in `profile` needs no `search` code and cannot forget a job: the database clears every link in the same statement as the file's removal. The name shown never changes, because a file's `original_name` is never edited.
- **Alternatives considered**: `profile`'s removal use case calling into `search` to write the note (a new cross-module dependency in the opposite direction, and easy to bypass); a database trigger (hidden behaviour, harder to test and to read).

## R3. Checking a chosen file across modules

- **Decision**: `search.application.resume_choice.ResumeLookup`, a protocol with `get(file_id) -> ResumeFacts | None` (`name`, `added_on`, `offerable`). `search_wiring.SqlResumeLookup` implements it with `profile`'s `ResumeFilesRepo`. A file is offerable unless its `parse_status` is `not_resume` (FR-012); files still being read (`pending`) or whose reading failed (`no_text`, `failed`) are offered.
- **Rationale**: the import-linter `search-boundary` contract forbids `search` from importing `profile.infra`; `search_wiring.py` already bridges the two modules for `ProposalSource`. The server, not the client, supplies the snapshot, so only real stored files can be recorded.
- **Alternatives considered**: see Complexity Tracking in the plan.

## R4. The last choice (spec clarification 3)

- **Decision**: a one-row table `app.pipeline_settings` (`id = 1`, `last_resume_file_id` foreign key `ON DELETE SET NULL`). It is written only by the mark endpoints when the request carries `resume_file_id` (a resume or `null` for None). The edit card never writes it (FR-014). The frontend reads it from `GET /pipeline/resumes` to set the control's starting value.
- **Rationale**: server-side, so it is the same in every browser and Delete all empties it; `SET NULL` makes a removed file start on None for free.
- **Alternatives considered**: browser `localStorage` (not cleared by Delete all, differs per browser, cannot be tested against the database); deriving it from the most recently marked job (applied and inquired dates are days, can be back-dated, and would not remember an explicit None).

## R5. Mark requests: omitted versus None

- **Decision**: `AppliedIn` and `InquiredIn` gain `resume_file_id: UUID | None`. The handler uses Pydantic's `model_fields_set`: field **absent** → the job's current choice is left as it is (inquired → applied keeps it, FR-003) and the last choice is untouched; field **present** (a file or `null`) → the job's choice is set to it and the last choice is updated. A body-less one-click request stays valid and behaves exactly as today (FR-002, SC-006).
- **Rationale**: keeps every existing caller and test working while giving the picker an explicit way to say None.

## R6. Merge, undo, prune and delete

- **Merge** (FR-010): `InterviewsRepo.merge_details` already keeps the kept job's own contact and source and fills empty ones from the other job; the three resume columns are carried the same way as one unit (all three from the same side).
- **Undo** (FR-008): undoing applied or inquired clears the three resume columns of that job's details (002e keeps contact, source and rounds on undo; the resume is different by spec). The last choice is not touched.
- **Prune**: 002e deletes a details row when contact and source are both empty; the check must also require `resume_name IS NULL`, or a job whose only detail is its resume would lose it. Tested.
- **Delete job / Delete all** (FR-011): the details row goes with the job (002e), and Delete all truncates every `app` table with `CASCADE` in one statement, which covers `pipeline_settings` and the new foreign keys. Tested.

## R7. Removal confirmation count

- **Decision**: `GET /pipeline/resumes` returns `usage`, the number of pipeline jobs per resume file. The profile's `ResumeFiles` removal dialog reads it and says "Used on N jobs; their name stays as a note" (FR-009, SC-004).
- **Rationale**: the frontend may call both modules' APIs; the backend keeps its module boundary.

## R9. Removing a file completely (analyze finding D1)

- **Decision**: the profile's removal dialog offers "Also clear the name from these N jobs" (off by default). When ticked, the frontend first calls `DELETE /pipeline/resumes/{file_id}/uses` (search: clears the three resume columns on every job pointing at the file, and the last choice if it is that file), then the existing `DELETE /resumes/{file_id}` (profile).
- **Rationale**: constitution VIII requires that a person can delete their data completely per item; keeping the name stays the default as Ravi chose. Clearing first is required because after the file is removed the jobs no longer point at it.
- **Alternatives considered**: one backend call (needs `profile` → `search`, against the module boundary); clearing after removal by matching names (names are not unique). If the removal fails after the clear, the file stays and the jobs have no resume; the dialog shows the error and the person can retry.

## R8. The control

- **Decision**: one `ResumeSelect` component (a native `<select>`, styled by the global dark select styles from 002e's polish): the offerable files newest first by name and added day, plus **None**. It is not rendered when the person has no offerable file. Used in `PipelineControl` (beside the date; starting on the job's own resume when it has one, as an inquired job may, else on the last choice, FR-003) and in the edit card (starting on the job's current choice; a removed note shows as a separate read-only line with **Clear**).
- **Rationale**: a native select is accessible by default and keeps one click for people who leave it alone.
