---
description: "Task list for 002f-resume-picker"
---

# Tasks: Resume picker

**Input**: Design documents from `specs/002f-resume-picker/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md).

**Tests**: **Mandatory** (constitution V). Every task is one red → green → refactor cycle and **one commit**: write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, and keep the whole suite green.

**Organization**: grouped by user story in priority order: US1 and US2 (P1), US3 (P2), US4 (P3), then Polish. Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `search/…` means `backend/src/hiretitan/search/…`; tests are under `backend/tests/…`; frontend paths are under `frontend/src/…`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`.
- After any API change run `npm run gen:api` in `frontend/` (writes `backend/openapi.json` and `frontend/src/api/schema.d.ts`) and commit both with the task.
- Before pushing frontend work run `npm run build` in `frontend/` (its `tsc -b` catches errors `tsc --noEmit -p .` misses).
- The no-send scanner bans `.delete()`/`.post()`/`.put()`/`.patch()` method names under `search/`; name repo methods `clear_*`, `set_*`, `remove`.

---

## Phase 1: Setup

**Purpose**: a known-green baseline.

- [x] T001 Confirm `002f-resume-picker` is cut from the current `master` (it holds 0018 from 002e) and record the baseline: backend suite, `ruff`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test`, `npm run build`. Write the counts under a new 002f entry in `docs/CONTEXT.md`. No code change.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the rule, the columns, the repo methods and the file lookup every story uses.

- [x] T002 [P] Pure rule in `search/domain/resume_choice.py`: `ResumeChoice` value (`state`: `"chosen" | "removed" | "none"`, `resume_file_id`, `name`, `added_on`) built by `choice_from(resume_file_id, resume_name, resume_added_on)` per the display rule in data-model.md ("`resume_file_id` set → chosen; null and `resume_name` set → removed; both null → none"); `offerable(parse_status) = parse_status != "not_resume"` (FR-012). Tests first in `backend/tests/unit/search/test_resume_choice.py`: `test_display_rule_chosen`, `test_display_rule_removed`, `test_display_rule_none`, `test_FR012_not_a_resume_is_not_offerable`.
- [x] T003 [P] Migration `backend/alembic/versions/0019_resume_picker.py` (parent `0018_interview_tracking`) and rows in `search/infra/models.py`: on `PipelineDetailsRow` add `resume_file_id uuid NULL` FK `app.resume_files(id)` **`ON DELETE SET NULL`** (FK by table name, no import of `profile`), `resume_name text NULL`, `resume_added_on date NULL`, with checks `resume_name_length` = "`char_length(resume_name) BETWEEN 1 AND 255`", `resume_snapshot_together` = "`(resume_name IS NULL) = (resume_added_on IS NULL)`", `resume_link_has_snapshot` = "`resume_file_id IS NULL OR resume_name IS NOT NULL`", and index `ix_job_pipeline_details_resume_file_id`; new `PipelineSettingsRow` (`pipeline_settings`: `id smallint` PK with check "`id = 1`", `last_resume_file_id uuid NULL` FK `app.resume_files(id)` **`ON DELETE SET NULL`**). Downgrade drops the table, index, checks and columns. Tests first: `backend/tests/integration/platform/test_migrations.py` `test_0019_resume_picker_up_down`; `backend/tests/integration/search/test_resume_choice_repo.py` `test_resume_columns_constraints` (each check rejects a bad row); the model/migration drift test stays green.
- [x] T004 Repo methods (`search/infra/interviews_repo.py`): `set_resume(job_id, file_id, name, added_on)`, `clear_resume(job_id)` (clears all three columns, then `_prune`); `details()` returns the three columns; `_prune` now deletes a row only when contact, source **and** `resume_name` are all null (research R6); `usage() -> {file_id: count}` (one grouped query on `resume_file_id IS NOT NULL`). New `search/infra/pipeline_settings_repo.py`: `last_choice() -> UUID | None` and `set_last_choice(file_id | None)` (`INSERT … ON CONFLICT (id) DO UPDATE`). Tests first in `backend/tests/integration/search/test_resume_choice_repo.py`: `test_prune_keeps_a_row_whose_only_detail_is_the_resume`, `test_clear_resume_prunes_an_otherwise_empty_row`, `test_FR009_usage_counts_jobs_per_file`, `test_last_choice_round_trip`, `test_FR009_removing_a_file_keeps_its_name_as_a_removed_note` (deleting the `resume_files` row sets `resume_file_id` to null and keeps the snapshot), `test_FR014_last_choice_resets_when_its_file_is_removed`.
- [x] T005 File lookup and use cases: `search/application/resume_choice.py` with the `ResumeLookup` protocol (`get(file_id) -> ResumeFacts | None`, `ResumeFacts(name, added_on, offerable)`), `choose_for_job(job_id, file_id)` (a `FieldIssue` on `resume_file_id` for an unknown or not-offerable file), `clear_for_job(job_id)`, `record_on_mark(job_id, provided: bool, file_id | None)` (absent → no change; present → set or clear the job and `set_last_choice`), all requiring the job in a pipeline state under the job row lock as 002e does; `search_wiring.py` `SqlResumeLookup` over `profile`'s `ResumeFilesRepo` (`added_on` = `created_at` date), wired where `ProposalSource` is. Tests first in `backend/tests/integration/search/test_resume_choice_repo.py`: `test_FR001_unknown_file_is_a_field_error`, `test_FR012_not_a_resume_file_is_refused`, `test_record_on_mark_absent_changes_nothing`, `test_record_on_mark_null_sets_none`; `lint-imports` stays clean (no `search` → `profile` import).

**Checkpoint**: the data and its rules exist; nothing visible changes yet. Ravi reviews.

---

## Phase 3: User Story 1 - Say which resume I used when I apply (Priority: P1) 🎯 MVP

**Goal**: an optional **Resume used** choice beside the date when marking applied or inquired, starting on the last choice.

**Independent Test**: with two stored files, mark a job applied choosing the older one; it is recorded; the next job's choice starts on that file; a body-less one-click mark behaves as before.

- [x] T006 [US1] Backend: `AppliedIn` and `InquiredIn` in `search/api/jobs.py` gain `resume_file_id: UUID | None = None`; the handlers pass `"resume_file_id" in body.model_fields_set` and the value to `record_on_mark` inside the same transaction as the mark and **after** the job's state change, so the pipeline-state check passes (research R5); `DELETE /jobs/{job_id}/applied` and `/inquired` call `clear_for_job` (FR-008); new `search/api/pipeline.py` `GET /pipeline/resumes` returning `{ "last_choice": uuid | null, "usage": [...] }` (contracts/rest-api.md), router wired in `api_main.py`; `npm run gen:api`. Tests first in `backend/tests/api/search/test_resume_choice_api.py`: `test_FR001_mark_applied_records_the_chosen_resume`, `test_FR002_mark_without_resume_field_behaves_as_before`, `test_FR003_inquired_to_applied_keeps_the_resume`, `test_FR001_mark_with_null_records_none_and_remembers_none`, `test_FR008_undo_clears_the_resume`, `test_FR012_not_a_resume_file_is_refused` (422 with field `resume_file_id`), `test_pipeline_resumes_last_choice`.
- [x] T007 [US1] Frontend: `features/jobs/resume/resumeApi.ts` (`useResumeOptions` = `GET /resumes` filtered to `parse_status !== 'not_resume'`, newest first by `created_at`; `usePipelineResumes` = `GET /pipeline/resumes`, query key `['pipeline-resumes']`, invalidated by every mark, undo and resume change) and `features/jobs/resume/ResumeSelect.tsx` (native `<select>` labelled "Resume used": each file as name and added day, plus **None**; renders nothing when there is no offerable file); `features/jobs/PipelineControl.tsx` shows `ResumeSelect` beside the date, starting on the job's own resume when it has one (an inquired job, FR-003), else on `last_choice` (None when null or no longer offered), and sends `resume_file_id` only when the select is shown. Tests first in `features/jobs/resume/ResumeSelect.test.tsx` and `features/jobs/PipelineControl.test.tsx`: `US1 AS1 lists files newest first plus None`, `US1 AS6 hidden when there are no stored files`, `US1 AS4 starts on the last choice and sends it`, `US1 AS5 starts on None when the last choice is gone`, `US1 AS2 inquired job starts on its own resume`, `US1 AS3 one click still marks the job`, `FR012 files still being read are offered`.
- [x] T007r [US1] Story review: run the python/FastAPI, security, database and React reviewer agents over the US1 diff (T002–T007); fix the findings before US1 is marked done; note them under the 002f entry in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 4: User Story 2 - See the resume in the pipeline (Priority: P1)

**Goal**: a Resume column in In pipeline and the resume in the details.

**Independent Test**: one job with a resume, one without: the list shows the name and a dash; the details show the name and the added day.

- [x] T008 [US2] Backend: `JobCardOut.resume: ResumeChoiceOut` filled from the details row already joined by 002e's lateral sub-query (no extra query per row); `GET /jobs/{job_id}/interview` adds `resume`; `npm run gen:api`. Tests first in `backend/tests/api/search/test_resume_choice_api.py`: `test_FR004_pipeline_cards_carry_the_resume`, `test_FR005_interview_details_carry_the_resume`, `test_FR006_jobs_before_the_feature_have_none`; the pipeline list query-count test from 002e stays green.
- [x] T009 [US2] Frontend: `features/explore/PipelinePage.tsx` adds a **Resume** column (name truncated with the full name in `title`; a dash for none; "name (removed)" for a removed note); `features/jobs/interview/InterviewPanel.tsx` (read-only view in the expanded row) and `features/jobs/JobDetailPage.tsx` show the resume name and "added <day>"; every `PipelineControl` caller (`ExplorePage.tsx`, `JobDetailPage.tsx`, `EditJobDialog.tsx`, `PasteJobDialog.tsx`) passes `ownResumeId` from the card's `resume.resume_file_id` so an inquired job starts on its own resume (FR-003; T007 added the prop), and `features/jobs/resume/resumeApi.ts` gains `export type ResumeChoice = components['schemas']['ResumeChoiceOut']` (it cannot exist before T008). Tests first in `features/explore/PipelinePage.test.tsx` and `features/jobs/interview/InterviewPanel.test.tsx`: `US2 AS1 resume column shows the name`, `US2 AS2 dash without a resume`, `US2 AS3 details show the name and added day`, `US2 AS4 long names are truncated with a title`.
- [x] T009r [US2] Story review: python/FastAPI and React reviewer agents over the US2 diff; fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews. US1 + US2 together are the MVP.

---

## Phase 5: User Story 3 - Change or clear the resume later (Priority: P2)

**Goal**: set, change or clear the resume in the pencil edit card, protected by the unsaved-changes guard.

**Independent Test**: on an applied job with no resume, choose one in the edit card, save, see it; change it; clear it; closing with an unsaved change asks first.

- [x] T010 [US3] Backend: routes `PUT /jobs/{job_id}/interview/resume` (`{ "resume_file_id": uuid }` → 200 `ResumeChoiceOut`; 404 job unknown or not in the pipeline; 422 unknown or not-offerable file) and `DELETE /jobs/{job_id}/interview/resume` (204) in `search/api/interviews.py`; neither writes the last choice (FR-014); `npm run gen:api`. Tests first in `backend/tests/api/search/test_resume_choice_api.py`: `test_FR006_edit_card_sets_changes_and_clears`, `test_FR014_last_choice_follows_marks_not_edit_card`, `test_edit_card_resume_not_in_pipeline_404`, `test_edit_card_resume_of_a_removed_file_is_refused` (422, field `resume_file_id`).
- [x] T011 [US3] Frontend: the editable `InterviewPanel` (shown in `features/jobs/EditJobDialog.tsx`) gets a Resume section with `ResumeSelect` starting on the job's current choice and its own **Save**, registered with the `unsaved.ts` registry (unsaved = different from the stored choice, or a save in flight or failed). Tests first in `features/jobs/interview/InterviewPanel.test.tsx` and `features/jobs/EditJobDialog.test.tsx`: `US3 AS1 choose a resume and save`, `US3 AS2 change and clear`, `US3 AS3 closing with an unsaved resume change asks first`, `saving a resume removed meanwhile shows a message and the removed note`.
- [x] T011r [US3] Story review: python/FastAPI and React reviewer agents over the US3 diff; fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 6: User Story 4 - Resume files that go away, jobs that merge or are removed (Priority: P3)

**Goal**: removed files leave a clearable note; merge, job removal and Delete all keep the data consistent and private.

**Independent Test**: choose a file on two jobs, remove it in Profile: the dialog says "used on 2 jobs", both jobs show "name (removed)", clearing one leaves a dash; Delete all leaves nothing.

- [ ] T012 [US4] Backend: `DELETE /pipeline/resumes/{file_id}/uses` in `search/api/pipeline.py` (clears the resume on every job pointing at the file and the last choice if it is that file; 204; research R9), with `InterviewsRepo.clear_resume_everywhere(file_id)` and `npm run gen:api`; (`InterviewsRepo.merge_details` carrying the three resume columns as one unit was done in T007r after the reviewers found it; its tests are `test_FR010_merge_keeps_own_resume_else_takes_the_other` and `test_FR010_merge_carries_a_removed_note_too` in `test_resume_choice_repo.py`); confirm job removal drops the details row with the resume; extend the privacy test so a seeded resume name never appears in a recorded model request; extend the delete-all test for `pipeline_settings` and the resume columns. Tests first: `backend/tests/api/search/test_resume_choice_api.py` `test_FR009_clear_all_uses_of_a_file`; `backend/tests/integration/search/test_resume_choice_repo.py` `test_FR010_merge_keeps_own_resume_else_takes_the_other`, `test_FR011_removing_a_job_removes_its_resume`; (`test_FR009_a_removed_note_can_be_cleared` was written in T010); the existing interview privacy test module gains `test_SC005_no_resume_name_in_ai_calls`; the existing delete-all test module gains `test_SC005_delete_all_removes_resume_choices_and_last_choice`.
- [ ] T013 [US4] Frontend: (the removed note with **Clear** in `InterviewPanel` was built in T011;) `features/profile/ResumeFiles.tsx` removal confirmation reads `usePipelineResumes().usage` and, when the count is above 0, adds "Used on N job(s). Their name stays on them as a note you can clear." plus a checkbox **Also clear the name from these jobs** (off by default; when ticked, call `DELETE /pipeline/resumes/{id}/uses` first, then `DELETE /resumes/{id}`, showing an error and stopping if either fails), and invalidates `['pipeline-resumes']`, `['jobs']` and `['job-interview']` after removal. Tests first in `features/jobs/interview/InterviewPanel.test.tsx` and `features/profile/ResumeFiles.test.tsx`: `US4 AS2 a removed note shows with Clear`, `US4 AS1 removal dialog says how many jobs use the file`, `US4 removal dialog says nothing extra when unused`, `US4 AS6 also clear the name clears then removes`, `US4 AS6 the option is off by default`.
- [ ] T013r [US4] Story review: security and database reviewer agents (privacy, cascade and `SET NULL` paths) plus React over the US4 diff; fix the findings; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T014 Playwright: in `frontend/e2e/job-search.spec.ts`, after a search, mark an Explore job applied with a synthetic resume chosen in **Resume used** and check the In pipeline Resume column shows it (synthetic fixture only). Run `prepare.mjs` and the e2e compose stack as in `docs/CONTEXT.md`; all three journeys pass.
- [ ] T015 [P] Docs: describe choosing, changing and clearing the resume, the last-choice start and the removed-file note in `docs/user-guide/job-search.md`; add the new columns, table and the `ResumeLookup` port to `docs/architecture.md`; list 002f in `docs/clarified-requirements.md` §12.
- [ ] T016 Success-criteria map `specs/002f-resume-picker/success-criteria-map.md` (each SC-001…SC-006 to its tests) and gates: backend suite with coverage gate, `ruff`, `ruff format --check`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test`, `npm run build`; dependency licence checks (`backend/scripts/check_licenses.py` and the frontend licence check) and vulnerability checks (as CI runs them), even though no dependency is added; record the counts in `docs/CONTEXT.md`. In the map, note SC-003 (under 30 seconds) as checked by hand with quickstart step 5.
- [ ] T017 Final review: python/FastAPI, database, React and security reviewer agents over the whole branch (`master..HEAD`); fix high and medium findings, list accepted leftovers in `docs/CONTEXT.md`. Then Ravi decides on the PR.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T005)**: T002 and T003 in parallel; T004 needs T003; T005 needs T002 and T004.
- **US1 (T006–T007r)** needs Foundational. **US2 (T008–T009r)** needs Foundational; its backend (T008) can run alongside US1, but showing a value needs US1's writes to test by hand, so do US1 first.
- **US3 (T010–T011r)** needs Foundational and reuses US1's `ResumeSelect` (T007).
- **US4 (T012–T013r)** needs US2's display (removed note) and T004's foreign-key behaviour.
- **Polish (T014–T017)** after the stories.
- Within each task: tests first (red), then code (green), then refactor; one commit per task.

## Parallel Examples

- Foundational: T002 (`search/domain/resume_choice.py`) and T003 (migration and rows) touch different files and can run together.
- US2: T008 (backend) and the US1 frontend task T007 touch different files.
- Polish: T015 (docs) can run alongside T014 (Playwright).

## Implementation Strategy

1. **MVP = US1 + US2** (both P1): record the resume when marking, and see it in the pipeline. Stop and let Ravi try it.
2. **US3**: fix forgotten or wrong choices in the edit card.
3. **US4**: removal notes, merge, privacy and Delete all.
4. Polish: Playwright, docs, success-criteria map, final review, then the PR when Ravi says so.
