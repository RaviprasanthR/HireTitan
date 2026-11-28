# Success criteria map (002m-mikasa-chat)

| SC | What proves it |
|---|---|
| SC-001 | `tests/api/assistant/test_staged_api.py`, `tests/integration/assistant/test_staged_flow.py`; `frontend/e2e/mikasa.spec.ts` (paste a link, one message) |
| SC-002 | Eval `mikasa`: first words p90 (Ravi's run, T037) |
| SC-003 | Eval `mikasa`: 43 action requests, right action and values on the first try; risky changes only ever reach a card (`tests/api/assistant/test_changes_api.py`, `tests/workflow/assistant/test_cards.py`); Undo on every small change (`test_changes_api.py::test_US2_AS1_*`) |
| SC-004 | Eval `mikasa`: 15 planted titles; `tests/workflow/assistant/test_guardrails.py::test_FR015_*` |
| SC-005 | Eval `mikasa`: 20 questions with no stored answer; `tests/workflow/assistant/test_turn.py::test_SC005_seeded_unbacked_claims_all_rejected` |
| SC-006 | Eval `mikasa`: 14 declines (FR-016 and sending; a plain decline passes); `tests/workflow/assistant/test_limits.py::test_US4_AS1_declines_with_link` |
| SC-007 | `tests/architecture/test_no_send.py` (includes `test_SC007_planted_sender_in_mikasa_is_caught`) |
| SC-008 | `tests/workflow/assistant/test_turn.py::test_SC008_*`, `test_limits.py` (every status reason), `MikasaPanel.test.tsx::US4_AS2_composer_disabled_with_reason` |
| SC-009 | `tests/integration/assistant/test_repos.py::test_SC009_delete_all_truncates_assistant_tables`; `tests/api/assistant/test_conversations.py::test_US5_AS2_clear` |
| SC-010 | `tests/api/assistant/test_changes_api.py::test_SC010_private_change_actions_never_echo_values`; `tests/integration/actions/test_drafts_actions.py::test_SC010_contact_recipient_not_sent` |
| SC-011 | Eval `mikasa`: 21 off-topic requests, 6 typed injections stopped before the AI; `tests/workflow/assistant/test_guardrails.py`, `test_topic_checker.py` |

The eval (`backend/evals/mikasa/`) runs the real turn loop and tool catalogue over a synthetic
world in memory, so no database is touched. The harness itself is tested with a scripted AI in
`tests/unit/evals/test_mikasa_eval.py`; the real-model run is Ravi's (T037).
