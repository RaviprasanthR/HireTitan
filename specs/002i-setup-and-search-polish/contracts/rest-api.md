# REST contract: Setup and search polish

**Feature**: [../spec.md](../spec.md) · **Data model**: [../data-model.md](../data-model.md)

Base path `/api/v1`. Errors use the existing problem format (`type`, `title`, `status`, `detail`, `errors[{field, message}]`).

## New endpoints

### `GET /search/rules/suggested`

The rules the proposer suggests from the current confirmed profile and saved preferences. Writes nothing.

- `200` → `SearchRulesModel` (with `areas`).
- `409` `rules_unavailable` (`no_confirmed_profile` or `no_preferences`), as `POST /search/rules/proposal` today.

### `PUT /search/rules/approved`

Save the person's edited rules as the rules searches use.

- Body: `SearchRulesModel`.
- `200` → `RuleSetOut` of the new approved version (`approved_by: "person"`); the previous approved set is superseded and any open proposal is discarded, in one transaction.
- `422` field errors from `SearchRules.validate` (`title_words`, `title_avoid`, `areas`, `max_age_days`, …).

## Changed endpoints

### `POST /onboarding/complete`

Unchanged request and `200` body. After setup is recorded, the composition root's `on_completed` callback runs `approve_first_rules` in its own transaction. Its failure never changes the response (FR-004); `GET /status` then shows `rules_approved: false` and Explore links to Search rules.

### `GET /search/rules`

`RulesStateOut.approved` and `.proposal` (`RuleSetOut`) gain `approved_by: "person" | "auto" | null`. `SearchRulesModel` gains `areas: string[]`.

### `GET /jobs/{id}`, job cards

No shape change. After a search with the AI check on, `description`, `skills_found` and `years_found` are filled for jobs whose description was read.

### `POST /jobs/{id}/recheck`

Unchanged contract (202 `{run_id}`). The `recheck_job` workflow now reads the description first when the job has none.

## Start-up behaviour

`api_main` lifespan, after migrations and the company seed: if setup is complete and no rule set was ever approved, run `approve_first_rules` (logged; failure does not stop the API).

## Test matrix

| Test (name prefix) | Covers |
|---|---|
| `test_FR001_finish_setup_approves_first_rules` | US1 AS1, FR-001, FR-005 |
| `test_FR002_existing_approval_is_never_replaced` | US1 AS3, FR-002, SC-006 |
| `test_FR002_double_finish_approves_once` | edge case (concurrency), SC-006 |
| `test_FR003_startup_approves_for_finished_setup` | US1 AS4, FR-003 |
| `test_FR004_invalid_proposal_leaves_setup_finished` | US1 AS5, FR-004 |
| `test_FR007_first_approval_makes_no_llm_call` | FR-007 |
| `test_FR015_put_approved_saves_new_version` | US3 AS3, FR-015 |
| `test_FR016_put_approved_rejects_invalid_rules` | US3 AS5, FR-016 |
| `test_FR017_suggested_writes_nothing` | US3 AS6/AS7, FR-017, FR-018 |
| `test_FR029_descriptions_read_for_kept_jobs_only` | US6 AS3, FR-029 |
| `test_FR029_description_requests_stay_on_allowlist` | FR-029 (contract, recorded fixtures per vendor) |
| `test_FR029_description_text_is_screened` | FR-029, constitution III |
| `test_FR030_proposer_guesses_areas` / `test_FR031_avoid_words_for_other_areas` | US6 AS5 |
| `test_FR032_title_stack_rule` | US6 AS2, AS6, FR-032 |
| `test_FR033_profile_card_has_profile_skills_and_areas` | FR-033 (the empty-skills bug) |
| `test_FR034_unreadable_description_is_told_to_the_ai` | US6 AS4, FR-034 |
| `test_FR036_area_and_stack_skips_are_restorable` | FR-036 |
| `test_0020_migration_*` | data model §1 |
