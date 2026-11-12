---
description: "Task list for 002e-interview-tracking"
---

# Tasks: Interview tracking

**Input**: Design documents from `specs/002e-interview-tracking/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md).

**Tests**: **Mandatory** (constitution V). Every task is one red → green → refactor cycle and **one commit**: write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, and keep the whole suite green.

**Organization**: grouped by user story in priority order: US1 and US2 (P1), then US3 and US4 (P2), then Polish. Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US4 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `backend/src/hiretitan/…` (shortened to the module below), `backend/tests/…`, `frontend/src/…`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`.
- After any API change run `npm run gen:api` in `frontend/` (writes `backend/openapi.json` and `frontend/src/api/schema.d.ts`) and commit both with the task.

---

## Phase 1: Setup

**Purpose**: a known-green baseline.

- [x] T001 Before anything else, once 002d's PR has merged: rebase `002e-interview-tracking` onto `master` (constitution: each feature branch is cut from `master`) and check `0018_interview_tracking`'s parent is still `0017_no_cost`. Then record the baseline: backend suite, `ruff`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test`. Write the counts under a 002e entry in `docs/CONTEXT.md`. No code change.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the rules, the tables, the repo and the read endpoint every story uses.

- [x] T002 [P] Pure rules in `search/domain/interviews.py`: `ROUND_KINDS = ("screening","technical","hr","managerial","other")`, `ROUND_STATES = ("scheduled","cleared","failed")`, `SOURCES = ("direct","hiring_firm")`; limits "name, role, firm 120; interviewers 300; question 2,000; answer and feedback 10,000"; `check_contact(...)` reusing `search/domain/contacts.py` `clean()` and its email, phone and LinkedIn checks (returns `FieldIssue`s); `check_source(kind, firm_name)` ("a hiring firm needs a name"; Direct or none drops the firm); `next_round_number(numbers) = max(numbers, default=0) + 1`; `can_add_round(states) = "failed" not in states`; `status_summary(job_state, rounds) -> (state, round | None)`: any failed → `("failed", highest failed number)`, else rounds → `(state of the highest number, that number)`, else `(job_state, None)`. Tests first in `backend/tests/unit/search/test_interviews.py`: `test_FR004_next_round_number`, `test_FR006_failed_blocks_new_rounds`, `test_FR007_status_summary_no_rounds`, `test_FR007_status_summary_latest_round`, `test_FR007_status_summary_failed_wins`, `test_FR003_hiring_firm_needs_a_name`, `test_FR002_contact_checks`, `test_FR014_line_breaks_kept` (pins that `clean()` keeps `\n`).
- [x] T003 [P] Migration `backend/alembic/versions/0018_interview_tracking.py` (parent `0017_no_cost`) and rows in `search/infra/models.py`: `PipelineDetailsRow` (`job_pipeline_details`: `job_id` PK FK `jobs.id` ON DELETE CASCADE, `contact_name/role/email/phone/linkedin`, `source`, `firm_name`, timestamps; checks `source_values`, `firm_iff_hiring_firm` = "`(source IS NOT DISTINCT FROM 'hiring_firm') = (firm_name IS NOT NULL)`", `contact_has_name`), `InterviewRoundRow` (`interview_rounds`: `id`, `job_id` FK CASCADE indexed, `number` ≥ 1 unique with `job_id`, `kind`, `scheduled_at timestamptz NULL`, `interviewers`, `state` default `scheduled`, `feedback`, timestamps; checks `kind_values`, `state_values`, `number_positive`), `InterviewQuestionRow` (`interview_questions`: `id`, `round_id` FK CASCADE indexed, `position` ≥ 1, `question` NOT NULL, `answer`, timestamps). Downgrade drops the three tables. Tests first in `backend/tests/integration/platform/test_migrations.py`: `test_0018_interview_tracking_up_down`; in `backend/tests/integration/search/test_interviews_repo.py`: `test_FR009_checks_reject_bad_values`, `test_FR003_firm_iff_hiring_firm`, `test_FR004_unique_round_number`; the model/migration drift test stays green.
- [ ] T004 `InterviewsRepo` in `search/infra/repos.py`: `details(job_id)` (contact, source, rounds with questions ordered by `number` and `position`), `upsert_contact`, `clear_contact`, `set_source`, `add_round` (numbers with `next_round_number`), `update_round`, `delete_round`, `add_question` (position = max + 1), `update_question`, `delete_question`, `delete_for_job(job_id)`, `summaries(job_ids) -> {job_id: (state, round)}` (one query), `rounds_matching(kind=None, state=None, source=None)`. Tests first in `backend/tests/integration/search/test_interviews_repo.py`: `test_US2_AS6_delete_keeps_other_numbers`, `test_US3_AS1_questions_in_order`, `test_SC005_rounds_matching_by_field`, `test_summaries_in_one_query`.
- [ ] T005 Read endpoint: `search/application/interviews.py` `read(job_id)` (adds `can_edit` = job applied or inquired, `can_add_round`, `status`), `search/api/interviews.py` `GET /jobs/{job_id}/interview` with the response shape in contracts/rest-api.md, router wired in `api_main.py`; `npm run gen:api`. Tests first in `backend/tests/api/search/test_interviews_api.py`: `test_read_empty_details`, `test_read_unknown_job_404`, `test_can_edit_false_outside_the_pipeline`.

**Checkpoint**: the data and its rules exist; nothing visible changes yet. Ravi reviews.

---

## Phase 3: User Story 1 - Record who I deal with and how the job came (Priority: P1) 🎯 MVP

**Goal**: contact and source per pipeline job, in an expandable In pipeline row and on the job page.

**Independent Test**: expand an applied job's row, save a contact with only a name and a hiring firm with a name, reload, see both; switch to Direct and the firm is gone; a bad email is refused on that field only.

- [ ] T006 [US1] Backend: use cases `save_contact`, `clear_contact`, `save_source` in `search/application/interviews.py` (409 `not_in_pipeline` when the job is not applied or inquired, research R6); routes `PUT/DELETE /jobs/{job_id}/interview/contact`, `PUT /jobs/{job_id}/interview/source` returning the full shape; `npm run gen:api`. Tests first in `backend/tests/api/search/test_interviews_api.py`: `test_US1_AS2_contact_with_only_a_name`, `test_US1_AS3_bad_email_refused`, `test_US1_AS3_bad_linkedin_refused`, `test_US1_AS4_hiring_firm_needs_a_name`, `test_US1_switch_to_direct_clears_the_firm`, `test_R6_not_in_pipeline_refused`.
- [ ] T007 [US1] Frontend: `features/jobs/interview/interviewApi.ts` (query `['job-interview', id]`; mutations invalidate it and `['jobs']`), `features/jobs/interview/InterviewPanel.tsx` with the Contact section (name required; role, email, phone, LinkedIn optional; inputs carry `maxLength` "name, role, firm 120" and email 254 so the limit shows before saving, FR-014; field errors from the 422; email and phone shown as plain text, LinkedIn as a link with `rel="noopener noreferrer"`) and the Source section (Direct, Through a hiring firm with a firm name, Not set), each with its own **Save** and a saved or error message; `features/explore/PipelinePage.tsx` rows expand to show the panel (`aria-expanded`). Tests first in `features/jobs/interview/InterviewPanel.test.tsx` and `features/explore/PipelinePage.test.tsx`: `US1 AS1 row expands to the detail panel`, `US1 AS2 contact with only a name saves`, `US1 AS3 a field error shows on that field`, `US1 AS4 hiring firm needs a name`.
- [ ] T008 [US1] Frontend: `features/jobs/JobDetailPage.tsx` shows the same `InterviewPanel` under the pipeline control when the job is applied or inquired, and read-only (with a note) when details exist but the job left the pipeline (US4 AS4). Tests first in `features/jobs/JobDetailPage.test.tsx`: `US1 AS5 job page shows the same panel`, `US4 AS4 the panel is read-only outside the pipeline`.
- [ ] T008r [US1] Story review (constitution, Quality Gates): run the python/FastAPI, security, database and React reviewer agents over the US1 diff (T002–T008); fix the findings before US1 is marked done; note them under the 002e entry in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 4: User Story 2 - Track interview rounds and see where I stand (Priority: P1)

**Goal**: rounds per job; the Status column shows the latest round.

**Independent Test**: add Round 1 → "Round 1 scheduled"; clear it, add Round 2 → "Round 2 scheduled"; fail Round 2 → "Failed in round 2" and Add round is disabled; set it back → Add round works; delete Round 2 → "Round 1 cleared".

- [ ] T009 [US2] Backend: use cases `add_round` (409 `process_failed` when any round is failed; `not_in_pipeline`), `update_round` (any state change allowed, US2 AS5), `delete_round`; routes `POST /jobs/{job_id}/interview/rounds`, `PATCH/DELETE /interview/rounds/{round_id}`; `scheduled_at` accepts an ISO date-time with offset, past allowed (US2 AS8); `npm run gen:api`. Tests first in `backend/tests/api/search/test_interviews_api.py`: `test_US2_AS1_first_round_is_round_1_scheduled`, `test_US2_AS2_next_round_is_numbered_after`, `test_US2_AS3_can_add_while_one_is_scheduled`, `test_US2_AS4_failed_blocks_new_rounds`, `test_US2_AS5_unfailing_allows_rounds_again`, `test_US2_AS6_deleting_the_latest_round`, `test_US2_AS7_inquired_job_can_have_rounds`, `test_US2_AS8_past_date_on_scheduled_round`, `test_unknown_kind_refused`, `test_R6_round_refused_outside_the_pipeline`.
- [ ] T010 [US2] Backend: `JobCardOut.interview: {state, round} | null` in `search/api/models.py`; `GET /jobs?list=pipeline` fills it from `InterviewsRepo.summaries` for the page's jobs (one query per page); other lists return null; `npm run gen:api`. Tests first in `backend/tests/api/search/test_pipeline_api.py`: `test_SC002_pipeline_status_column` (applied without rounds, inquired without rounds, round 2 scheduled, round 1 cleared, failed in round 3 with a later scheduled round 4), `test_explore_list_has_no_interview`.
- [ ] T011 [US2] Frontend: `features/jobs/interview/RoundCard.tsx` (type, date and time via `datetime-local` converted to an instant and shown in local time, "date not set" when empty, interviewers with `maxLength` 300, state Scheduled/Cleared/Failed, **Save**, **Delete round** with a confirm); **Add round** in `InterviewPanel.tsx`, disabled with "A round failed, so no new round can be added" when `can_add_round` is false; `PipelinePage.tsx` Status column shows "Round N scheduled", "Round N cleared", "Failed in round N", or the Applied or Inquired pill; each has its own colour, and `frontend/src/theme/contrast.test.ts` covers the new pairs. Tests first in `features/jobs/interview/RoundCard.test.tsx`, `InterviewPanel.test.tsx` and `features/explore/PipelinePage.test.tsx`: `US2 AS1 status reads Round 1 scheduled`, `US2 AS4 failed disables Add round with the reason`, `US2 AS6 deleting a round asks first`, `US2 AS8 time shown in local time`, `FR007 status colours meet contrast`.
- [ ] T011r [US2] Story review: python/FastAPI, database and React reviewer agents over the US2 diff (T009–T011); fix findings before US2 is marked done; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 5: User Story 3 - Keep the questions, answers and feedback from each round (Priority: P2)

**Goal**: ordered Q&A pairs and a feedback note per round.

**Independent Test**: add three pairs (one with no answer) and a multi-paragraph feedback note; reload; order and line breaks kept; edit one, delete one; the rest unchanged.

- [ ] T012 [US3] Backend: use cases and routes `POST /interview/rounds/{round_id}/questions`, `PATCH/DELETE /interview/questions/{question_id}`; `feedback` through `PATCH /interview/rounds/{round_id}`; limits "question 2,000; answer and feedback 10,000"; `npm run gen:api`. Tests first in `backend/tests/api/search/test_interviews_api.py`: `test_US3_AS1_question_without_answer_kept_in_order`, `test_US3_AS2_edit_or_delete_one_leaves_the_rest`, `test_US3_AS3_feedback_note_kept`, `test_US3_AS4_long_text_and_line_breaks_kept`, `test_FR014_too_long_refused_with_the_limit`.
- [ ] T013 [US3] Frontend: `features/jobs/interview/QuestionList.tsx` inside each `RoundCard` (add a pair, answer optional, edit inline with **Save**, delete; text areas keep line breaks; a character counter appears near the limit, FR-014) and a Feedback text area on the round. Tests first in `features/jobs/interview/QuestionList.test.tsx`: `US3 AS1 question kept in order`, `US3 AS2 delete one leaves the rest`, `US3 AS4 line breaks shown`, `FR014 counter near the limit`.
- [ ] T014 [US3] Frontend: unsaved-edit guard (FR-013): collapsing a pipeline row with unsaved edits in any section asks first; leaving the page asks first (`useBlocker`). Tests first in `features/explore/PipelinePage.test.tsx` and `features/jobs/JobDetailPage.test.tsx`: `FR013 collapse with unsaved edits asks first`, `FR013 leaving the page with unsaved edits asks first`, `FR013 no question when nothing changed`.
- [ ] T014r [US3] Story review: python/FastAPI and React reviewer agents over the US3 diff (T012–T014); fix findings before US3 is marked done; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 6: User Story 4 - The data stays mine and can be queried later (Priority: P2)

**Goal**: privacy guards and lifecycle rules for the new data.

**Independent Test**: record everything on a job; Delete all my data leaves none; a search with interview data present sends none of it to the AI; undo and re-mark loses nothing; deleting the job removes its details.

- [ ] T015 [P] [US4] Lifecycle: `delete_job` in `search/api/jobs.py` calls `InterviewsRepo.delete_for_job` in the same transaction; the duplicate merge in `search/api/duplicates.py` moves the loser's contact and source only into empty winner fields and its rounds (renumbered 1..n with their questions) only when the winner has none, then deletes the rest of the loser's details (research R7); undo applied or inquired leaves details untouched. Tests first in `backend/tests/api/search/test_interviews_lifecycle.py`: `test_FR011_undo_keeps_details` (SC-006), `test_FR011_delete_job_removes_details`, `test_FR012_merge_keeps_winner_fills_gaps`, `test_FR012_merge_moves_rounds_only_when_winner_has_none`.
- [ ] T016 [P] [US4] Privacy: add `hiretitan.search.domain.interviews` and `hiretitan.search.application.interviews` to the `contacts-stay-out-of-ai-paths` contract in `backend/.importlinter`; in `backend/tests/security/test_contacts_privacy.py` add `test_SC003_no_interview_text_in_ai_calls` (a search run with the scripted fake LLM while a pipeline job has a contact, a firm, rounds, questions and feedback; no recorded call contains any of that text) and extend the no-HTTP-client check to the interview modules; in `backend/tests/api/setup/test_delete_all_api.py` add `test_SC004_delete_all_removes_interview_data`.
- [ ] T016r [US4] Story review: security and database reviewer agents over the US4 diff (T015–T016), with the privacy guard and the merge as the focus; fix findings before US4 is marked done; note them in `docs/CONTEXT.md`.

**Checkpoint**: Ravi reviews.

---

## Phase 7: Polish & cross-cutting

- [ ] T017 [P] Playwright: in `frontend/e2e/job-search.spec.ts` after step 5, mark a job applied, expand its In pipeline row, save a contact and a hiring firm, add Round 1 (cleared) and Round 2, add one question; In pipeline shows "Round 2 scheduled"; assert no cost wording on the panel (FR-015).
- [ ] T018 [P] Docs: `docs/user-guide/job-search.md` (a section on interview tracking: contact, source, rounds, status, questions, what stays private), `docs/architecture.md` (§8 tables for 002e, the privacy contract), `README.md` feature list if it lists features.
- [ ] T019 Success-criteria map `specs/002e-interview-tracking/success-criteria-map.md` (SC-001 to SC-006 → tests; SC-001's one-minute target checked by hand with the quickstart); full gates: backend suite with the coverage gate, `ruff`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test -- --coverage`; all Playwright journeys against the e2e stack.
- [ ] T020 Final reviewer pass (the per-story reviews T008r, T011r, T014r, T016r come first) over the whole branch diff (python/FastAPI, database, React, security); fix findings; record them in `docs/CONTEXT.md`.
- [ ] T021 Update `docs/CONTEXT.md` (history, next steps) and `docs/clarified-requirements.md` §12 (add 002e); after 002d merges, rebase onto `master`; push and open the PR to `master` only when Ravi says so.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002–T005)**: T002 and T003 can run in parallel; T004 needs T003; T005 needs T002 and T004.
- **US1 (T006–T008)** needs Foundational. T007 needs T006; T008 needs T007 (it reuses the panel).
- **US2 (T009–T011)** needs Foundational and T007 (the panel it extends). T010 follows T009 (both regenerate `backend/openapi.json` and `schema.d.ts`).
- **US3 (T012–T014)** needs US2 (questions live on rounds). T014 needs T007 and T011.
- **US4 (T015–T016)** needs Foundational; it could run any time after T004, but is placed last so the guards cover every table and route.
- **Polish (T017–T021)** after all stories.

### Parallel opportunities

- T002 ∥ T003 (domain file vs migration and rows).
- T015 ∥ T016 (lifecycle vs privacy guards).
- T017 ∥ T018 (e2e vs docs).

## Implementation Strategy

- **MVP**: Phases 1–3 (contact and source in the expandable row and on the job page).
- **Then**: US2 (rounds and the Status column), the part asked for most; US3 (Q&A and feedback); US4 (lifecycle and privacy guards).
- Stop for Ravi's review at the end of every phase; one commit per task, message format `[002e-interview-tracking - Tnnn …] - If applied this commit will …`.
