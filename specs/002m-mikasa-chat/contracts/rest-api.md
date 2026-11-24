# REST API, stream and test matrix: Mikasa

**Feature**: `002m-mikasa-chat` · Prefix `/api/v1` · Errors are RFC 9457 problem+json with a `reason`, as elsewhere.

## Endpoints

| Method and path | Purpose | Success | Errors (`reason`) |
|---|---|---|---|
| `GET /assistant/status` | Can Mikasa be used now | `200 {available, reason?, provider_message?}`; `reason` ∈ `key_missing`, `key_rejected`, `out_of_credit`, `model_lacks_tools` | |
| `GET /assistant/conversations` | List, newest first | `200 [{id, title, last_used_at}]` | |
| `POST /assistant/conversations` | Start a new conversation | `201 {id}` | |
| `DELETE /assistant/conversations/{id}` | Remove one | `204` | `404 not_found` |
| `DELETE /assistant/conversations` | Clear all | `204` | |
| `GET /assistant/conversations/{id}/messages` | Full history with cards and changes | `200 [{id, seq, author, text, status, signals, cards: [...], changes: [...]}]` | `404` |
| `POST /assistant/conversations/{id}/turns` | Send a message, stream the reply | `200 text/event-stream` (below) | `409 turn_running`, `422 too_long` (over 2,000), `422 looks_like_posting` (FR-021), `503 ai_unavailable` with the status reason |
| `POST /assistant/conversations/{id}/paste` | The composer's **Paste a job description** (link, title, company, location, description; or `job` ref plus description) | `201 {change}` | the paste use case's `422` field errors; `409 deleted_before` |
| `POST /assistant/cards/{id}/confirm` | Apply a card, optionally with edited values `{items: [{index, args}]}` | `200 {card, changes}` | `409 not_proposed` (already decided), `409 stale` (targets changed, card now expired), `409 expired`, `422` argument errors |
| `POST /assistant/cards/{id}/cancel` | Cancel | `200 {card}` | `409 not_proposed` |
| `POST /assistant/changes/{id}/undo` | Undo a change | `200 {change}` | `409 changed_since`, `409 not_latest`, `409 too_late`, `409 already_undone`, `409 not_undoable` |
| `POST /jobs/paste` *(changed)* | Link-only mode: `description` may be empty when `url`, `title` and `company` are given (R12) | as today | as today |

Cross-site writes are refused by the existing middleware; the API stays on localhost.

## Turn stream (`text/event-stream`)

| Event | Data | When |
|---|---|---|
| `text` | `{delta}` | each piece of reply text |
| `ref` | `{ref}` | a ref token was written into the reply |
| `change` | `{change_id, action, summary, undo_until, invalidate: [query keys]}` | a small change was applied |
| `card` | `{card_id, summary, items: [{action, args, editable: [field]}], expires_at}` | a risky change was proposed |
| `notice` | `{kind: "injection_signal" \| "limit" \| "bulk_limit" \| "checking_profile", text}` | something the person should see |
| `error` | `{reason, message, provider_message?}` | the turn failed (`ai_unavailable`, `refused`, `timeout`, `internal`) |
| `done` | `{message_id, status: "complete" \| "stopped" \| "failed"}` | always last |

Closing the request stops the turn; the stored message is `stopped` (FR-002).

## Server event (existing `/events` stream)

`assistant.changed` `{keys: [query keys]}` after any change or card applied, so other open tabs refresh (FR-004).

## Test matrix

Tests are named after the requirement or scenario they check. `fake` = scripted `FakeLlm` (`HIRETITAN_LLM=fake`), `pg` = Testcontainers Postgres.

| Area | Test (file → names) | Kind |
|---|---|---|
| Port | `tests/unit/platform/llm/test_converse_port.py` → `test_FR023_converse_streams_text_and_tool_calls`, `test_FR024_out_of_credit_raises_ai_unavailable`, `test_FR023_each_round_logged` | unit (fake, recorded OpenAI stream fixtures) |
| OpenAI adapter | `tests/contract/llm/test_openai_converse.py` → `test_FR023_responses_stream_maps_to_events`, `test_FR024_model_without_tools_reported` | contract (recorded fixtures) |
| Catalogue | `tests/unit/actions/test_catalogue.py` → `test_FR010_every_change_action_has_a_fixed_kind`, `test_FR010_small_actions_have_undo`, `test_FR016_excluded_endpoints_have_no_action`, `test_FR005_every_ui_endpoint_is_mapped_or_excluded`; `tests/api/assistant/test_not_exposed.py` → `test_FR028_actions_not_exposed_outside_app` | unit; api |
| Parity | `tests/integration/actions/test_parity.py` → `test_FR006_parity_<action>` (one per change action) | pg |
| Private | `tests/unit/actions/test_private_results.py` → `test_FR022_private_actions_return_refs_and_labels_only`; `tests/security/assistant/test_private_never_sent.py` → `test_SC010_no_private_value_in_any_llm_request`, `test_SC010_private_change_actions_never_echo_values`, `test_FR022a_summary_of_private_content_declined` | unit; pg + fake |
| Untrusted | `tests/security/assistant/test_untrusted.py` → `test_FR020_description_never_in_model_context`, `test_FR020_flagged_title_masked`, `test_FR015_planted_instruction_leads_to_no_change`, `test_FR021_paste_text_never_sent`, `test_FR021_posting_like_message_refused` | pg + fake |
| Turn loop | `tests/workflow/assistant/test_turn.py` → `test_US1_AS2_answers_from_read_actions`, `test_US1_AS6_read_changes_nothing`, `test_FR025_unknown_tool_repaired_once_then_refused`, `test_R9_unknown_ref_removed`, `test_EC01_second_turn_refused_while_running`, `test_EC01_stale_running_turn_freed_after_120s`, `test_FR002_stop_saves_partial_reply`, `test_FR018a_unbacked_claim_repaired_then_replaced`, `test_SC008_unavailable_or_invalid_ends_with_reason_and_no_change` | pg + fake |
| Small changes | `tests/workflow/assistant/test_small_changes.py` → `test_US2_AS1_mark_applied_at_once_with_undo`, `test_US2_AS2_link_added_once_and_marked`, `test_US2_AS3_blocked_site_not_fetched` (no outbound request is made for any link), `test_FR014_undo_restores`, `test_EC16_undo_refused_after_newer_change`, `test_R6_undo_of_add_allows_readding` | pg + fake |
| Cards | `tests/workflow/assistant/test_cards.py` → `test_US2_AS4_risky_needs_confirm`, `test_FR011_edited_values_used`, `test_FR012_all_or_nothing`, `test_EC02_stale_card_refused`, `test_EC03_double_confirm_applies_once`, `test_EC05_bulk_limit`, `test_US5_AS4_old_card_expired` | pg + fake |
| Ambiguity | `test_FR013_two_matches_asks_which` | pg + fake |
| Drafts | `tests/workflow/assistant/test_drafts.py` → `test_US3_AS1_draft_through_002k_action`, `test_FR009_draft_saved_where_job_page_shows_it`; `tests/unit/actions/test_catalogue.py` → `test_US3_AS3_send_has_no_action` (the decline itself is an eval case) | pg + fake; unit |
| Limits | `tests/workflow/assistant/test_limits.py` → `test_US4_AS1_declines_with_link`, `test_US4_AS2_key_missing_status`, `test_US4_AS3_model_lacks_tools`, `test_FR018_no_profile_change_action` | pg + fake |
| Conversations | `tests/api/assistant/test_conversations.py` → `test_US5_AS1_history_kept`, `test_US5_AS2_clear`, `test_SC009_delete_all_removes_assistant_rows` | pg |
| API | `tests/api/assistant/test_turns_api.py` → `test_FR002_stream_events_in_order`, `test_too_long_message_422`; `test_cards_api.py`, `test_changes_api.py`, `test_paste_api.py` | pg + fake |
| Paste rule | `tests/unit/search/test_paste.py` → `test_R12_link_only_needs_title_and_company` | unit |
| Architecture | `tests/architecture/test_no_send.py` (scans `actions`, `assistant`) → `test_SC007_*`; import-linter contracts | static |
| Mail off | `tests/integration/actions/test_read_other.py` → `test_EC12_mail_actions_report_not_connected` | pg |
| Front end | `features/assistant/*.test.tsx` → `US1_AS1_panel_opens_beside_page`, `FR001_panel_on_every_page_keeps_conversation`, `FR021_posting_like_message_offered_to_paste`, `FR002_stop_button`, `FR003_ref_links_open_items`, `EC13_text_rendered_plain`, `US2_AS4_card_confirm_cancel_edit`, `FR014_undo_notice`, `FR022b_privacy_note_shown`, `FR024_unavailable_message`, `US5_AS1_history_after_reload`; `features/jobs/PasteJobDialog.test.tsx` → `R12_link_only_option` | Vitest |
| Journey | `frontend/e2e/mikasa.spec.ts` → "mark applied from a link, undo, delete with confirm" (scripted AI) | Playwright |
| Eval | `evals/mikasa/` → SC-002, SC-003, SC-004, SC-005, SC-006 | real model (Ravi) |
