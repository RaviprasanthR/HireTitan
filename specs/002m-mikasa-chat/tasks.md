---
description: "Task list for 002m-mikasa-chat"
---

# Tasks: Mikasa, the chat assistant

**Input**: Design documents from `specs/002m-mikasa-chat/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/actions.md](contracts/actions.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md).

**Tests**: **Mandatory** (constitution V). Every test name carries the FR, SC, US, EC or R id it verifies, as listed in the test matrix of [contracts/rest-api.md](contracts/rest-api.md). Every task is one red → green → refactor cycle and **one commit** (made when Ravi says so, with the commit skill): write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, keep the whole suite green.

**Organization**: Setup, then the Foundational base every story needs (port method, tables, domain rules, action types, prompt). Then US1 (a read-only Mikasa, mergeable alone), US2 (small changes and cards), US3 (drafts), US4 (limits), US5 (conversations), Polish. Implementation pauses for Ravi's review at the end of every phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1–US5 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths: `assistant/…` = `backend/src/hiretitan/assistant/…`; `actions/…` = `backend/src/hiretitan/actions/…`; `llm/…` = `backend/src/hiretitan/platform/llm/…`; `search/…`, `prompts/…` likewise; tests under `backend/tests/…`; frontend paths under `frontend/src/…`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`; never run plain `prettier --write` on existing files.
- After any API change run `npm run gen:api` in `frontend/` (writes `backend/openapi.json` and `frontend/src/api/schema.d.ts`) and commit both with the task. Before pushing frontend work run `npm run build`.
- The no-send scanner bans `.delete()`/`.post()`/`.put()`/`.patch()` method-call names in scanned packages; name repo methods `clear_*`, `set_*`, `remove`, `save`. Router decorators are allowed.
- Prompts follow the existing layout (`system.md`, `user.md.j2` if needed, `schema.py`, `meta.yaml` with `version`, `tier`, `max_output_tokens`, `changelog`).
- Integration tests need Docker Desktop (Testcontainers Postgres 16). Chat paths are tested with the scripted fake LLM (`HIRETITAN_LLM=fake`). All test data is synthetic.
- After each phase rebuild the dev stack on :8000 so Ravi can look at it.

---

## Phase 1: Setup

**Purpose**: a clean starting point.

- [x] T001 Record the baseline on this branch: backend suite (count, skips), `ruff`, `ruff format --check`, `mypy --strict`, `lint-imports`; frontend `tsc`, `eslint`, `npm test`, `npm run build`. Write the counts under a new 002m entry in `docs/CONTEXT.md`. No code change.

**Checkpoint**: baseline known.

---

## Phase 2: Foundational (blocking prerequisites for every story)

**Purpose**: the port method, tables, pure rules, action types, contracts and prompt that every story uses.

- [x] T002 [P] `converse` on the LLM port and the fake (R1). In `llm/port.py` add `ToolSpec(name, description, parameters: dict)`, `ChatMessage(role: "person"|"mikasa"|"tool_call"|"tool_result", text, tool_call_id?, tool_name?, arguments_json?)`, `ConverseRequest(task, prompt: RenderedPrompt, messages, tools, tier, max_output_tokens)`, events `TextDelta(text)`, `ToolCall(id, name, arguments_json)`, `TurnEnd(usage, provider, model, outcome)`, and `converse(req) -> AsyncIterator[...]` on `LlmPort`. In `llm/fake.py` add scripted converse turns by task (each turn a list of events or an exception) and record every request in `calls`. Log each round in `llm_calls` through the existing calls repo (task `mikasa_turn`). Tests first in `backend/tests/unit/platform/llm/test_converse_port.py`: `test_FR023_converse_streams_text_and_tool_calls`, `test_FR024_out_of_credit_raises_ai_unavailable`, `test_FR023_turn_end_carries_usage_for_logging`. **Done 2026-11-24:** `converse` is its own `ConversePort` protocol beside `LlmPort` (the seven test stubs that implement only `generate` stay valid); calls are logged by the caller in this code base (as `drafts/workflow/common.py` does), so `test_FR023_each_round_logged` moves to T012's turn loop.
- [x] T003 [P] OpenAI adapter `converse` (R1, R11). In `llm/openai_adapter.py` stream the Responses API with function tools (non-strict, see R1) built from `ToolSpec`; map deltas, function calls and completion to the port events; same error mapping as `generate` (`key_missing`, `key_rejected`, `out_of_credit` with the provider's message, retryable 429/5xx). Add `capabilities: [tools, streaming]` per model in `llm/models.yaml` and `ModelCatalog.supports(tier, capability)` in `llm/models.py`. Synthetic recorded stream fixtures in `backend/tests/fixtures/llm/converse/`. Tests first in `backend/tests/contract/llm/test_openai_converse.py`: `test_FR023_responses_stream_maps_to_events`, `test_FR024_model_without_tools_reported`, `test_FR024_quota_maps_to_out_of_credit`.
- [x] T004 Migration `backend/alembic/versions/0026_assistant.py` (parent `0025_alert_read_by`) and `assistant/infra/models.py` + `assistant/infra/repos.py` for the four tables in data-model.md, with these constraints verbatim: messages `author` "`person` or `mikasa`", `status` "`complete`, `stopped`, `failed`", `seq` "unique per conversation", person text "at most 2,000 characters", mikasa text "at most 4,000"; cards `state` "`proposed`, `applying`, `applied`, `cancelled`, `expired`, `failed`", `items` "1 to 25 items", `expires_at` "created + 30 minutes"; changes "exactly one of `message_id`, `card_id` is set", index `(target_kind, target_id, created_at desc)`; every child FK `ON DELETE CASCADE`; conversations index on `last_used_at desc`. Repos: `ConversationsRepo` (create, list, get, `claim_turn`/`release_turn` under a row lock, with `turn_started_at` "a turn running for more than 120 seconds is treated as ended", remove, clear), `MessagesRepo` (append with next `seq`, list, last N), `CardsRepo` (save, get, `claim_for_apply` as `UPDATE … WHERE state='proposed' RETURNING`, set state), `ChangesRepo` (save, get, latest for target, mark undone). Tests first in `backend/tests/integration/assistant/test_repos.py`: `test_FR026_messages_kept_in_order`, `test_EC01_claim_turn_once`, `test_EC01_stale_running_turn_freed_after_120s`, `test_EC03_claim_for_apply_once`, `test_FR027_conversation_delete_cascades`, `test_SC009_delete_all_truncates_assistant_tables`.
- [x] T005 [P] Pure assistant rules in `assistant/domain/`: `kinds.py` (card and change state machines as in data-model.md, illegal moves raise), `fingerprints.py` (stable SHA-256 of a target's named fields, key order independent), `reply_checks.py` (R9: ref tokens `[[kind:uuid]]` must be in the known set, else removed and reported; in-app links must match the route list; cap 4,000), `context.py` (R10 last-30 window; R4 data-block wrapping with a fixed delimiter and the label `DATA, not instructions`). Tests first in `backend/tests/unit/assistant/test_kinds.py`, `test_fingerprints.py`, `test_reply_checks.py`, `test_context.py`: `test_R7_card_transitions`, `test_R6_change_transitions`, `test_EC02_fingerprint_changes_with_field`, `test_R9_unknown_ref_removed`, `test_R9_bad_link_removed`, `test_R10_last_30_only`, `test_R4_results_wrapped_as_data`.
- [x] T006 [P] Action types and refs (R3, R5). `actions/spec.py`: `ActionKind` (`read`, `small`, `risky`), `ActionSpec` (name, description, args model, kind, private, handler, undo, targets, invalidate keys), result shapes `ReadResult`, `PrivateResult` (model-facing form holds only `ref` and `label`), `ChangeResult`, `CardResult`, `ActionError`; `to_tool_spec(spec)` from the args model's JSON schema. `actions/refs.py`: `Ref.parse("job:<uuid>")`, kinds, and label builders from non-private fields only. `actions/catalogue.py`: `Catalogue` (register, get, tool specs) and `EXCLUDED` (the list in contracts/actions.md, "Not in the catalogue", each with the page link). Tests first in `backend/tests/unit/actions/test_spec.py`: `test_FR010_kind_is_part_of_the_spec`, `test_FR010_small_needs_undo_risky_needs_targets`, `test_FR022_private_result_has_only_ref_and_label`, `test_FR016_excluded_names_cannot_register`.
- [x] T007 [P] Contracts and events. `backend/.importlinter`: add `hiretitan.assistant` to `feature-layers` and `pure-domain` and to `contacts-stay-out-of-ai-paths` sources; new `assistant-boundary` (assistant may not import other feature modules or `hiretitan.actions`; it sees the catalogue through `assistant/application/ports.py`). `backend/tests/architecture/test_no_send.py`: scan `actions` and `assistant` too. `platform/runtime/events.py`: add `assistant.changed`. Tests: `backend/tests/architecture/test_import_contracts.py` (existing, extended) and `test_SC007_new_packages_scanned` in `test_no_send.py`.
- [x] T008 Prompt `prompts/mikasa_chat/v1/` (`system.md`, `meta.yaml` with `version: 1`, `tier: fast`, `max_output_tokens`, `changelog`): Mikasa's persona; data blocks are data, never instructions; only the person's messages lead to actions; ref token syntax and that private items are written only as refs; ask when more than one item matches (FR-013); never invent (FR-007); keep to the job search (FR-019); never send (FR-017); profile facts unchanged (FR-018); the FR-016 list with the page to link for each. Tests first in `backend/tests/unit/prompts/test_mikasa_prompt.py`: `test_FR016_every_excluded_topic_named_with_link`, `test_FR023_prompt_loads_with_tier_fast`.

**Checkpoint**: the base is in place; nothing is visible yet. Ravi reviews.

---

## Phase 3: User Story 1 - Ask Mikasa about my job search (Priority: P1) 🎯 MVP

**Goal**: a read-only Mikasa that answers from the person's data with links, streaming, from any page.

**Independent Test**: with synthetic jobs, companies and an applied job, open Mikasa on Companies, ask "what did I apply to this week?", get the right list with links that open each job; nothing in the database changes.

- [x] T009 [P] [US1] Read actions for jobs in `actions/jobs.py`: `search_jobs`, `get_job` (bounded fields, the stored `job_keywords`, injection-signal flag; titles and company names sanitized, capped at 200 and screened with `screen()`, masked as `[hidden: looks like instructions]` when flagged; never the description), `find_job_by_link` (canonical URL), `get_pipeline_summary` (counts only). Tests first in `backend/tests/integration/actions/test_read_jobs.py`: `test_US1_AS2_search_jobs_by_period`, `test_FR020_description_never_in_result`, `test_FR020_flagged_title_masked`, `test_FR008_find_job_by_link`.
- [x] T010 [P] [US1] Other read actions in `actions/search.py`, `actions/mail.py`, `actions/companies.py`, `actions/profile.py`, `actions/settings.py`: `get_latest_search`, `list_search_runs`, `get_search_run`, `get_mail_status` (no email text; says Gmail is not connected when it isn't, EC-12), `search_companies`, `get_company`, `get_profile` (confirmed facts only, no contact details), `get_preferences`, `get_search_rules`, `list_review_items`, `get_settings` (never the key). Tests first in `backend/tests/integration/actions/test_read_other.py`: `test_FR005_read_actions_return_bounded_fields`, `test_FR018_profile_read_has_no_contact_details`, `test_FR020_mail_status_has_no_email_text`, `test_EC12_mail_actions_report_not_connected`.
- [x] T011 [P] [US1] Private read actions in `actions/contacts.py` and `actions/interviews.py`: `list_contacts`, `find_contact` (name matching on the server), `get_company_note`, `get_interview`, `list_rounds` (upcoming sorted on the server), `list_resume_files`, all returning `PrivateResult`. Tests first in `backend/tests/integration/actions/test_read_private.py` and `backend/tests/unit/actions/test_private_results.py`: `test_FR022_private_actions_return_refs_and_labels_only`, `test_EC14_find_contact_returns_ref`.
- [x] T012 [US1] The turn loop, read-only, in `assistant/application/turn.py` with `assistant/application/ports.py` (`ActionCatalog`, stores): claim the turn; build the context (system prompt, tool specs, last 30 messages); call `converse`; stream `text`; on a tool call validate the arguments (one repair with the validation error as the tool result, then refuse, FR-025, EC-09); run read actions and wrap results as data blocks; check the reply (R9); store the message with `refs`, `tool_trace`, `signals`; at most 6 rounds and 90 s; on client disconnect save the partial reply as `stopped`; on `AiUnavailable` store `failed` with the reason. **Profile claims (FR-018a, R9)**: when the turn called `get_profile`, buffer the reply (stream a `checking_profile` notice), check it through the `ProfileClaimsChecker` port (implemented in `assistant_wiring.py` over `drafts/domain/checks.py`), repair once with the unbacked terms as the reason, then replace the claim sentences with "I don't see that in your profile" and a Profile link. Small and risky calls are answered with `ActionError("not_yet")` until US2. Tests first in `backend/tests/workflow/assistant/test_turn.py`: `test_US1_AS2_answers_from_read_actions`, `test_US1_AS3_no_data_says_so` (scripted), `test_US1_AS6_read_changes_nothing`, `test_FR025_unknown_tool_repaired_once_then_refused`, `test_R9_unknown_ref_removed`, `test_EC01_second_turn_refused_while_running`, `test_FR002_stop_saves_partial_reply`, `test_FR024_out_of_credit_turn_failed_with_message`, `test_FR023_each_round_logged` (one `llm_calls` row per model round, task `mikasa_turn`), `test_FR018a_unbacked_claim_repaired_then_replaced`, `test_SC005_seeded_unbacked_claims_all_rejected`, `test_SC008_unavailable_or_invalid_ends_with_reason_and_no_change`.
- [x] T013 [US1] API and wiring: `assistant/api/status.py` (`GET /assistant/status` with `key_missing`, `key_rejected`, `out_of_credit` + provider message, `model_lacks_tools`), `assistant/api/conversations.py` (`POST`, `GET /assistant/conversations`, `GET …/{id}/messages`), `assistant/api/turns.py` (`POST …/{id}/turns` as `text/event-stream` with the events in contracts/rest-api.md; `409 turn_running`, `422 too_long` over 2,000, `422 looks_like_posting` for a message over 600 characters with two or more posting headings (research R4), `503 ai_unavailable`); `backend/src/hiretitan/assistant_wiring.py` builds the catalogue and stores; include the routers in `api_main.py`; `npm run gen:api`. Tests first in `backend/tests/api/assistant/test_turns_api.py` and `test_status_api.py`: `test_FR002_stream_events_in_order`, `test_too_long_message_422`, `test_EC01_turn_running_409`, `test_US4_AS2_key_missing_status`, `test_FR021_posting_like_message_refused`; `backend/tests/api/assistant/test_not_exposed.py::test_FR028_actions_not_exposed_outside_app` (no route lists or runs catalogue actions except the assistant endpoints).
- [x] T014 [US1] Security tests over the whole read path in `backend/tests/security/assistant/test_private_never_sent.py` and `test_untrusted.py`: plant distinctive synthetic values in contacts, notes, interview contacts, rounds, questions, answers, feedback and resume file names, run scripted turns that call every private read action, and assert no LLM request contains any of them (`test_SC010_no_private_value_in_any_llm_request`); a scripted request to summarise interview notes ends in a decline with a link and still no private value in any request (`test_FR022a_summary_of_private_content_declined`); assert no request contains a job description, page text or email text (`test_FR020_description_never_in_model_context`).
- [x] T015 [P] [US1] Front-end stream client in `features/assistant/stream.ts` (fetch POST, parse SSE frames, typed events, abort for Stop) and `features/assistant/api.ts` (status, conversations, messages; TanStack Query keys `['assistant', …]`). Tests first in `features/assistant/stream.test.ts`: `FR002_parses_events_in_order`, `FR002_abort_stops`.
- [x] T016 [US1] The panel: `features/assistant/MikasaPanel.tsx` (an `<aside>` beside the page, 420 px, full screen under 768 px, not a modal; title "Mikasa"), `Conversation.tsx` (messages, live text, Stop), `Composer.tsx` (2,000-character limit with count, the privacy note from R13), `ReplyText.tsx` (plain text plus ref and link tokens only, no HTML or Markdown), `RefCard.tsx` (job, company, contact, round, resume file cards filled from the existing endpoints; "no longer exists" for a deleted target), the unavailable message for each status reason with a link to Settings; launcher button and `Ctrl+/` in `app/Shell.tsx`; `assistant.changed` in `api/useEvents.ts`. Tests first in `features/assistant/*.test.tsx`: `US1_AS1_panel_opens_beside_page`, `FR001_panel_on_every_page_keeps_conversation`, `FR021_posting_like_message_offered_to_paste` (on `looks_like_posting` the panel offers to open the paste dialog with the text), `US1_AS5_text_streams_and_stop`, `FR003_ref_links_open_items`, `EC13_text_rendered_plain`, `FR022b_privacy_note_shown`, `FR024_unavailable_message`.
- [x] T017 [US1] Story review: run the Python/FastAPI, security (prompt injection and privacy) and React reviewers on Phase 3; fix what they find with tests; full gates; rebuild the dev stack on :8000.

**Checkpoint**: a read-only Mikasa works end to end and can merge alone. Ravi reviews.

---

## Phase 4: User Story 2 - Tell Mikasa to do it (Priority: P1)

**Goal**: small changes happen at once with Undo; risky changes wait for a confirm card; Ravi's "I applied to <link>" works in one message.

**Independent Test**: "I applied to <link of a known job>" marks it applied today with Undo; a new link with title and company is added once and marked applied, and Undo removes both; "delete the Acme backend job" shows a card and deletes nothing until confirmed.

- [x] T018 [US2] Move the rules that sit in routers into application functions so routers and actions share one path (R3). In `search/api/jobs.py`: `not_skipped` (restore only a skipped job), `not_recheckable` (recheck only a job the AI has not checked), `already_applied` and `not_applied` (applied and its undo), `already_inquired`, `already_applied` on inquire, and `not_inquired`. `search/api/interviews.py` (`not_in_pipeline`, `process_failed`) and `search/api/companies.py` (`no_board`) already map application errors; check that `contacts.py` does the same and move anything that does not. Refactor only: the existing API tests stay green unchanged; add unit tests for each moved rule in the matching `backend/tests/unit/search/` file named after the original FR.
- [x] T019 [P] [US2] Link-only paste (R12): in `search/application/paste.py` allow an empty description when `url`, `title` and `company` are given (other limits unchanged); in `features/jobs/PasteJobDialog.tsx` add "I don't have the description", which makes title and company required. Tests first: `backend/tests/unit/search/test_paste.py::test_R12_link_only_needs_title_and_company`, `backend/tests/api/search/test_paste_api.py::test_R12_link_only_job_added`, `features/jobs/PasteJobDialog.test.tsx::R12_link_only_option`.
- [x] T020 [US2] Change records and Undo in `assistant/application/changes.py`: apply a small action and write its change record (`before`, `after`, `created_rows`, `undoable_until` = created + 24 h) in one transaction; undo only when not undone, within 24 h, the latest change to its target, and the target's current fields equal `after` (else `changed_since`, `not_latest`, `too_late`, `already_undone`, `not_undoable`); undo of an add removes the created rows for good when nothing else points to them. Tests first in `backend/tests/workflow/assistant/test_small_changes.py`: `test_FR014_undo_restores`, `test_EC16_undo_refused_after_newer_change`, `test_EC03_undo_twice_once` (the undo-of-an-add test moved to T021, where `add_job` lives).
- [x] T021 [P] [US2] Small job actions in `actions/jobs.py`: `mark_applied`, `unmark_applied`, `mark_inquired`, `unmark_inquired`, `restore_job` (undo re-hides with the old reason through a new undo-only function in `search/application`), `add_job` (link-only paste), `add_job_and_mark`. Parity tests first in `backend/tests/integration/actions/test_parity.py`: `test_FR006_parity_<action>` for each; plus `test_US2_AS1_mark_applied_at_once_with_undo`, `test_US2_AS2_link_added_once_and_marked`, `test_US2_AS3_blocked_site_not_fetched` (an `add_job` for a LinkedIn or Naukri link makes no outbound request; the scripted turn asks for title and company).
- [x] T022 [P] [US2] Small company, contact and note actions in `actions/companies.py` and `actions/contacts.py`: `add_company`, `edit_company` (including hiding or showing one company), `add_contact`, `edit_contact`, `set_company_note` (private ones return refs). Parity tests `test_FR006_parity_<action>`; `test_EC15_typed_contact_saved_then_private`.
- [x] T023 [P] [US2] Small interview and resume actions in `actions/interviews.py`: `set_interview_contact`, `set_interview_source`, `add_round`, `edit_round`, `add_question`, `edit_question`, `set_resume_used` (all private). Parity tests `test_FR006_parity_<action>`.
- [x] T024 [US2] Confirm cards in `assistant/application/cards.py`: create from risky calls (summary written by HireTitan from the items, fingerprints from each action's `targets`, at most 25 items, else a `bulk_limit` notice with the page link, EC-05); confirm (`claim_for_apply`, re-check fingerprints → `expired` + `409 stale`, validate edited args, apply every item in one transaction and write change records, enqueue worker jobs after commit, publish `assistant.changed`); cancel; expire on read past `expires_at`. Tests first in `backend/tests/workflow/assistant/test_cards.py`: `test_US2_AS4_risky_needs_confirm`, `test_FR011_edited_values_used`, `test_FR012_all_or_nothing`, `test_EC02_stale_card_refused`, `test_EC03_double_confirm_applies_once`, `test_EC05_bulk_limit`, `test_US5_AS4_old_card_expired`.
- [x] T025 [P] [US2] Risky job, search and mail actions in `actions/jobs.py`, `actions/search.py`, `actions/mail.py`: `delete_job`, `recheck_job`, `merge_duplicate`, `dismiss_duplicate`, `mark_applied_many`, `mark_inquired_many`, `restore_jobs`, `start_search` (refused with progress when one runs, EC-11), `stop_search`, `start_mail_check`, `add_mail_sender`, `edit_mail_sender`, `delete_mail_sender`, each with `targets`. Parity tests `test_FR006_parity_<action>`; `test_EC11_search_running_reported`.
- [x] T026 [P] [US2] Risky company, contact, interview and resume actions: `hide_companies` (2 to 25 companies), `delete_company`, `confirm_board`, `reject_board`, `delete_contact`, `delete_round`, `delete_question`, `clear_interview_contact`, `clear_resume_used`. Parity tests `test_FR006_parity_<action>`.
- [x] T027 [P] [US2] Risky profile-side actions in `actions/profile.py` and `actions/settings.py`: `update_preferences` (card shows before and after), `edit_rule_proposal`, `approve_rule_proposal`, `discard_rule_proposal`, `set_display_name`. Parity tests `test_FR006_parity_<action>`; `test_FR018_no_action_writes_profile_facts`.
- [x] T028 [US2] Wire changes into the turn and the API: in `assistant/application/turn.py` run small actions (stream `change`) and turn risky calls into cards (stream `card`); `assistant/application/paste.py` and `POST /assistant/conversations/{id}/paste` (FR-021: the text goes to the paste use case or `PUT /jobs/{id}/description`, a change record is written, nothing reaches the model); `assistant/api/cards.py` (confirm, cancel) and `assistant/api/changes.py` (undo) with the error reasons in contracts/rest-api.md; `npm run gen:api`. Tests first in `backend/tests/workflow/assistant/test_turn_changes.py` and `backend/tests/api/assistant/test_cards_api.py`, `test_changes_api.py`, `test_paste_api.py`: `test_FR015_planted_instruction_leads_to_no_change`, `test_FR013_two_matches_asks_which`, `test_FR021_paste_text_never_sent`, `test_US2_AS7_failed_change_reports_reason`, `test_FR004_assistant_changed_published`, `test_SC010_private_change_actions_never_echo_values` (extend T014's planted-value test to every private small and risky action, including the arguments echoed back).
- [x] T029 [P] [US2] Catalogue completeness in `backend/tests/unit/actions/test_catalogue.py`: `test_FR005_every_ui_endpoint_is_mapped_or_excluded` (walks the app's routes; each is an action's mirrored endpoint or in `EXCLUDED`), `test_FR010_every_change_action_has_a_fixed_kind`, `test_FR010_small_actions_have_undo`, `test_FR016_excluded_endpoints_have_no_action`, `test_US3_AS3_send_has_no_action` (no action name, description or handler sends, posts or submits). Add the route-to-action map to `actions/catalogue.py`.
- [x] T030 [US2] Front end: `features/assistant/ConfirmCard.tsx` (each change, editable fields for `editable` args, Confirm and Cancel, applied, cancelled, expired and stale states), `ChangeNotice.tsx` (summary, Undo until `undo_until`, plain refusal reasons), the composer's **Paste a job description** reusing `PasteJobDialog` against the new endpoint; invalidate each change's query keys. Tests first: `US2_AS4_card_confirm_cancel_edit`, `FR014_undo_notice`, `EC02_stale_card_message`, `FR021_paste_from_composer`.
- [x] T031 [US2] Playwright journey `frontend/e2e/mikasa.spec.ts` with the scripted AI: open the panel, mark a job applied from a link with title and company, see it in In pipeline, Undo, then delete a job through a confirm card. Story review (Python/FastAPI, security, database, React reviewers), fixes with tests, full gates, rebuild the dev stack.

**Checkpoint**: Mikasa acts with Undo and cards. Ravi reviews.

### Phase 4b: Guardrails (amendment 2026-11-24, FR-029 to FR-033, SC-011, research R17)

- [x] T031a [US2] Code guardrails in `assistant/application/turn.py` and `assistant/domain/`: refuse a typed message with a medium or high injection signal before any AI call (FR-032); replace the reply of a turn that called no catalogue action with the fixed refusal (FR-031); history window 10 (FR-033). Tests first in `backend/tests/workflow/assistant/test_guardrails.py`: `test_FR032_injected_message_refused_before_ai`, `test_FR031_reply_without_action_replaced`, `test_FR031_reply_after_a_read_kept`, `test_FR033_last_10_only`.
- [x] T031b [US2] Topic check: prompt `prompts/mikasa_topic/v1/` (tier fast, tool-less, schema `on_topic`, `reason` <= 120) called through `LlmPort.generate` before the main turn; off topic gives the fixed refusal and no converse call; a failed check falls through to FR-031. Tests first: `test_FR030_off_topic_refused_without_main_call`, `test_FR030_on_topic_goes_on`, `test_FR030_check_failure_falls_through`, prompt test in `backend/tests/unit/prompts/test_mikasa_topic_prompt.py`.
- [x] T031c [US2] Suggested questions: `assistant/domain/suggestions.py` (keys, labels, action recipes), `GET /assistant/suggestions`, `POST /assistant/conversations/{id}/suggestions/{key}` running the recipe through the catalogue adapter with no model call, storing both messages and any change or card. Tests first in `backend/tests/api/assistant/test_suggestions_api.py`: `test_FR029_suggestion_makes_no_ai_call`, `test_FR029_applied_this_week`, `test_FR029_run_a_search_makes_a_card`, `test_SC011_suggestions_zero_ai_calls`.
- [x] T031d [US2] Front end: the panel opens with the suggestion chips; **Ask something else** opens the composer; off-topic refusals show the chips again. Tests first: `FR029_chips_first`, `FR029_chip_runs_without_typing`, `FR030_refusal_shows_chips`.
- [x] T031f [US2] Quick actions (Ravi, 2026-11-24, replacing the suggested questions of T031c and T031d): the five quick actions of FR-029 as `assistant/domain/quick.py`, `application/quick.py`, `api/quick.py` (`GET /assistant/quick-actions`, `POST .../quick/status`, `POST .../quick/draft`); the drafts feature gains an email kind (`draft_email` prompt, migration `0028`, workflow branch, eval cases), `GET /drafts/{id}` and a shared `start_draft`; draft ref cards; the panel's forms, `RefCard` draft layout with Copy. Tests: `backend/tests/api/assistant/test_quick_actions_api.py`, `tests/integration/assistant/test_draft_starter.py`, `test_draft_card.py`, email cases in `tests/workflow/drafts/test_outreach.py`, `tests/unit/prompts/test_drafts_prompts.py`, `MikasaPanel.test.tsx`, `RefCard.test.tsx`; e2e journey updated.
- [x] T031g [US2] Post-to-draft flow (Ravi, 2026-11-24, replacing the draft forms of T031f): hidden `staged` job state and `assistant_staged` (migration `0029`), `extract_posting_identity` prompt, `staged_wiring.py` (`StagedFlowImpl`, `draft_starter`), `assistant/api/staged.py`, `StagedFlow.tsx`, composer routing of a link or posting into the flow. Tests: `tests/integration/assistant/test_staged_flow.py`, `tests/api/assistant/test_staged_api.py`, `tests/api/search/test_staged_hidden.py`, migration test, `MikasaPanel.test.tsx` flow tests, e2e step 7.
- [x] T031e [US2] Eval cases: at least 20 off-topic requests and the injected-message set for SC-011 and FR-032, in `backend/evals/mikasa/` (with T036).


---

## Phase 5: User Story 3 - Ask Mikasa for drafts (Priority: P2)

**Goal**: the 002k drafts and tailored resume through chat, with the same checks.

**Independent Test**: with a confirmed profile and a job with a description, ask for a connection request; after the card, the draft (≤ 200 characters, same checks) is on the job's page and linked from the chat.

- [x] T032 [US3] Draft actions in `actions/drafts.py`: `draft_connection_request`, `draft_referral_message` (risky; recipient a contact ref, resolved on the server, or a typed name and role; calls the 002k request use case so placeholders keep the contact out of the AI), `tailor_resume` (risky), `list_drafts` and `get_tailored_resume` (read, refs only, never the draft text), `delete_draft`, `delete_tailored_resume` (risky). No action edits draft or resume text (FR-008a). Tests first in `backend/tests/workflow/assistant/test_drafts.py`: `test_US3_AS1_draft_through_002k_action`, `test_FR009_draft_saved_where_job_page_shows_it`, `test_US3_AS2_tailored_resume_linked`, `test_FR008a_no_action_edits_draft_text`, `test_SC010_contact_recipient_not_sent`; parity tests for the deletes.
- [x] T033 [US3] Front end: draft and tailored-resume `RefCard`s (kind, made at, the text shown from the existing endpoints, links to the job's drafts and `/jobs/:id/resume`); refresh on `draft.ready` and `tailored_resume.ready`. Tests first: `US3_AS1_draft_card_links_to_job`, `US3_AS2_resume_card_links_to_preview`. Story review (Python/FastAPI, security, React reviewers), fixes with tests, full gates, rebuild the dev stack.

**Checkpoint**: drafts through chat. Ravi reviews.

---

## Phase 6: User Story 4 - Mikasa's limits are clear (Priority: P2)

**Goal**: clear declines with links, clear messages when the AI cannot be used.

**Independent Test**: "delete all my data" is declined with a link to Settings; with no key, the panel says a key is needed and the rest of the app works.

- [x] T034 [US4] Limits end to end: `GET /assistant/status` drives the panel for every reason (`key_missing`, `key_rejected`, `out_of_credit` with the provider's message, `model_lacks_tools`), the composer is disabled with the reason and a Settings link, and the rest of the app is unaffected; a scripted decline reply keeps its Settings link through R9's link check. Tests first: `backend/tests/workflow/assistant/test_limits.py::test_US4_AS1_declines_with_link`, `test_US4_AS3_model_lacks_tools`, `test_US4_AS2_out_of_credit_keeps_conversation`; `features/assistant/MikasaPanel.test.tsx::US4_AS2_composer_disabled_with_reason`. Story review (Python/FastAPI, React reviewers), fixes with tests, full gates, rebuild the dev stack.

**Checkpoint**: limits are clear. Ravi reviews.

---

## Phase 7: User Story 5 - My conversations (Priority: P3)

**Goal**: conversations survive reloads; new, delete and clear work; Delete all removes them.

**Independent Test**: talk, reload, reopen: the conversation is there; clear it: gone; Delete all: nothing of Mikasa remains.

- [x] T035 [US5] Conversations: `DELETE /assistant/conversations/{id}` and `DELETE /assistant/conversations` in `assistant/api/conversations.py`; the title from the first 80 characters of the first message, made by HireTitan; the panel's conversation list, **New conversation**, **Clear all** (with an "are you sure"), the open conversation kept across page changes and reloads; old `proposed` cards shown as expired. Tests first: `backend/tests/api/assistant/test_conversations.py::test_US5_AS1_history_kept`, `test_US5_AS2_clear`, `test_SC009_delete_all_removes_assistant_rows`; `features/assistant/MikasaPanel.test.tsx::US5_AS1_history_after_reload`, `US5_AS2_new_and_clear`. Story review (Python/FastAPI, database, React reviewers), fixes with tests, full gates, rebuild the dev stack.

**Checkpoint**: all five stories done. Ravi reviews.

---

## Phase 8: Polish & cross-cutting

- [x] T036 [P] Eval `backend/evals/mikasa/` (synthetic world loaded into a test database, cases, scorer, `runner.py`) and the `mikasa` task in `backend/evals/run.py` (`--models`, `--yes`, stops on `AiUnavailable`, no cost figures): at least 40 action requests across the catalogue (SC-003), 15 planted-instruction jobs and alerts (SC-004), 20 questions with no answer in the data (SC-005), the FR-016 and "send" declines, requests to summarise private notes (FR-022a), short posting excerpts typed as messages with planted instructions (research R4), questions about the person's experience with seeded unbacked claims (FR-018a), and off-topic requests (SC-006), first-words latency p90 (SC-002), tokens per turn. Unit tests with the scripted AI in `backend/tests/unit/evals/test_mikasa_eval.py`.
- [ ] T037 Ravi runs the eval on his key (`PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run mikasa --models fast,strong --yes`); commit the report `backend/evals/reports/mikasa-<date>.md`; SC-002 to SC-006 must pass on `fast` before the PR merges.
- [x] T038 [P] Docs: `docs/architecture.md` (Mikasa: `converse`, the actions layer, turns, cards, changes, privacy refs), `docs/user-guide/` Mikasa page (what she can and cannot do, what is sent to the AI), `specs/002m-mikasa-chat/success-criteria-map.md` (SC-001 to SC-010 → tests), `docs/clarified-requirements.md` §12 (reading single postings from public ATS links as a later idea, R12), `docs/CONTEXT.md`.
- [ ] T039 Final review and gates: reviewers (Python/FastAPI, security, database, React) over the whole branch, fixes with tests; backend suite with the coverage gate, ruff, format, mypy, import contracts; frontend tests, tsc, eslint, build; all Playwright journeys twice; rebuild the dev stack; open the PR.

---

## Dependencies & execution order

- **Setup (T001)** → **Foundational (T002–T008)**: T002, T005, T006, T007 in parallel; T003 after T002; T004 any time; T008 after T006 (it names the excluded list).
- **US1 (T009–T017)** needs all of Foundational. T009, T010, T011 in parallel; T012 after them; T013 after T012; T014 after T013; T015 any time in the phase; T016 after T015 and T013; T017 last.
- **US2 (T018–T031)** needs US1. T018 first (shared rules); T019 in parallel with T018; T020 after T018; T021–T023 after T020, in parallel; T024 after T020; T025–T027 after T024, in parallel; T028 after T021–T027; T029 after T028; T030 after T028; T031 last.
- **US3 (T032–T033)** needs US2's cards (T024, T028).
- **US4 (T034)** needs US1; can run beside US2 or US3.
- **US5 (T035)** needs US1; can run beside US2 to US4.
- **Polish**: T036 after US2 (it needs the full catalogue); T037 after T036 and US3; T038 any time after US2; T039 last.

## Parallel opportunities

- Foundational: T002, T005, T006, T007 (different files).
- US1: T009, T010, T011 (different action files); T015 beside T012–T014.
- US2: T019 beside T018; T021, T022, T023; then T025, T026, T027.
- After US1: US4 and US5 beside US2.

```text
# US2, after T020:
T021 actions/jobs.py small        T022 actions/companies.py + contacts.py small        T023 actions/interviews.py small
# US2, after T024:
T025 jobs/search/mail risky        T026 companies/contacts/interviews risky              T027 profile/settings risky
```

## Implementation strategy

- **MVP**: Phases 1–3 give a read-only Mikasa (ask anything, links, streaming, private refs). It can merge alone if Ravi wants an early PR.
- **Then** Phase 4 (act with Undo and cards), which delivers Ravi's "I applied to <link>" example, then Phases 5–7.
- Each phase ends with Ravi's review and a rebuilt dev stack; commits only when Ravi asks.
