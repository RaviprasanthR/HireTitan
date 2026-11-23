# Tasks: Gmail job alerts

**Input**: Design documents from `specs/002c-gmail-job-alerts/`
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md), [quickstart.md](quickstart.md)

**Tests**: required (constitution V, test-first). Each story's tests are written first, named after the FR, US or SC id they verify, and seen failing before the code. Real PostgreSQL (Testcontainers); fakes only for Gmail and Google OAuth (respx, hand-built fixtures of the documented shapes), the LLM and the clock.

**Organization**: by user story; pause for Ravi's review after every phase (a `…r` review task ends each story).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US5 from spec.md
- Paths: `backend/src/hiretitan/…` is shortened to `hiretitan/…`; tests live under `backend/tests/`; frontend paths start at `frontend/src/`.

---

## Phase 1: Setup

**Purpose**: a branch on the merged code, fixtures and the facts the readers depend on.

- [ ] T001 Rebase `002c-gmail-job-alerts` onto `master` once PR #18 (002k) is merged; run the baseline gates (backend suite with coverage, ruff, `mypy --strict`, `lint-imports`, licence gate; frontend tests, tsc, eslint, `npm run build`) and record the numbers under a new 002c entry in `docs/CONTEXT.md`.
- [x] T002 [P] Synthetic alert fixtures in `backend/tests/fixtures/mail/`: at least 10 `.eml` files per built-in site (`linkedin`, `naukri`, `indeed`, `foundit`, `instahyre`, `cutshort`) imitating each site's alert layout with made-up companies and people, plus 3 "unknown layout" emails and 2 with planted AI instructions; a `README.md` stating they are synthetic; an `expected.yaml` listing the jobs each email holds (for the reader tests and the SC-002 eval).
- [x] T003 [P] Seed `backend/seed/mail_senders.yaml` (site → addresses, research R3 table) with pure parsing in `hiretitan/mail/domain/senders.py::parse_seed` and the fail-fast file loader `hiretitan/mail/infra/seed.py::load_seed` (addresses lower-cased, "3 to 320 characters, one `@`", sites in `linkedin, naukri, indeed, foundit, instahyre, cutshort, other`); tests first in `tests/unit/mail/test_senders.py` (`test_FR010_builtin_sites_present`, `test_FR010_bad_seed_fails_fast`).
- [ ] T004 **Verify and record (Ravi, with a throwaway Google account; Claude records)**: create a throwaway Google account and follow the draft `docs/gmail-setup.md`; a *Web application* OAuth client in Google's testing mode must accept the redirect `http://localhost:8000/api/v1/mail/google/callback`, and the token response's `scope` must be exactly `https://www.googleapis.com/auth/gmail.readonly`. While connected, send three made-up test emails to that account by hand, then capture the real answers of `users/me/profile`, one `users/me/messages?q=…` list, one `messages/{id}?format=raw`, and the token, refresh and revoke responses. Replace tokens, addresses and ids with synthetic values and save them under `backend/tests/fixtures/gmail/` as the **recorded** contract fixtures (constitution V); no personal data. Record the result and any change to the flow in research R1.
- [ ] T005 **Verify (Ravi, by hand in Gmail)**: check each candidate sender address of research R3 against real alerts in the search box, and note each site's job-link shape (only the URL pattern, e.g. `…/jobs/view/<digits>`). Correct `backend/seed/mail_senders.yaml` and research R3/R4. Only addresses and URL patterns are written down; no mail content.

---

## Phase 2: Foundational

**Purpose**: storage, secrets, the network rules and the boundaries every story needs.

**⚠️ No user story starts before this phase is done.**

- [x] T006 Tests first in `tests/integration/mail/test_mail_storage.py`: migration `0023_mail_alerts` (parent `0022`) up and down; CHECKs reject bad values: `mail_connection.state` not in `connected, needs_reconnect`; a second `mail_connection` row (unique `provider`); `mail_senders.address` not "3 to 320 characters" or duplicate; `mail_senders.site` not in the site list; `mail_read_messages.outcome` not in `read, no_jobs, unreadable, needs_ai`; `jobs_found` outside "≥ 0, ≤ 60"; `injection_signals` not an array; `mail_checks.trigger` not in `daily, button, search_now`; `mail_checks.ended` not in `finished, stopped, access_ended, gmail_unavailable`; the finished-count rule `emails_listed = emails_skipped + emails_read + emails_unreadable`; `alert_sightings.link` over 2000; `job_sources.kind = 'email_alert'` and `search_runs.mode = 'mail_alerts'` accepted. Cascades: deleting a job removes its sightings; deleting a search run removes its `mail_checks` row. Then write `backend/alembic/versions/0023_mail_alerts.py`, `hiretitan/mail/infra/models.py` and the `alert_sightings` model in `hiretitan/search/infra/models.py` (SOURCE_KINDS + `email_alert`, RUN_MODES + `mail_alerts`), and register the models in `hiretitan/platform/db/models.py`.
- [x] T007 Repos in `hiretitan/mail/infra/repos.py` (`ConnectionRepo`, `SendersRepo` (seed merge keeps `enabled`), `ReadMessagesRepo` (`already_read(ids)` excluding `needs_ai`, `record`), `MailChecksRepo`), tests first in `tests/integration/mail/test_mail_repos.py` (`test_FR011_read_once`, `test_FR010_seed_merge_keeps_switches`, `test_US3_AS6_needs_ai_is_read_again`, `test_FR010_seed_loaded_at_api_start`); `hiretitan/api_main.py` loads `mail_senders.yaml` into `mail_senders` at start-up (merge, keep switches), like the company list.
- [x] T008 [P] Secrets file `hiretitan/mail/infra/secrets_file.py` (`<data_dir>/secrets/gmail.json`, atomic write, owner-only permissions where supported, environment `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` win, delete), tests first in `tests/unit/mail/test_secrets_file.py` (`test_FR003_round_trip_and_atomic`, `test_FR003_env_wins`, `test_FR003_never_in_repr_or_logs`); add the key names to the log redaction filter in `hiretitan/platform/security/`.
- [x] T009 [P] Network rules, tests first in `tests/architecture/test_no_send.py` and `tests/architecture/test_import_contracts.py`: `ALLOWED_HOSTS` gains `gmail.googleapis.com` and `oauth2.googleapis.com` (`hiretitan/platform/security/outbound_allowlist.py`); two named exemptions `mail/infra/gmail_client.py` (no mutating verb) and `mail/infra/google_oauth.py` (POST only); planted-source checks that a client elsewhere in `mail` fails; `test_SC007_mail_package_scanned`, `test_FR015_no_job_site_host_allowlisted` (only the two Google hosts are allowlisted for mail), `test_FR006_connection_and_reading_code_has_nothing_alert_specific` (the connection use cases import no reader; `mail_senders.purpose` accepts a second value in a test). Import-linter in `backend/.importlinter`: `mail-boundary` (`hiretitan.mail` imports no `search`, `profile`, `drafts`, `preferences`; `search` does not import `mail`), `mail.domain` added to the pure-domain contract, `mail` added to the layers contract.
- [x] T010 [P] Ports `hiretitan/mail/application/ports.py` (`MailReader`: `profile()`, `list_ids(query, page_token)`, `get_raw(id)`; `SecretsStore`; `AlertJobsSink`: `store(check_id, jobs) -> SinkCounts`), the `AlertJob` dataclass (title, company or None, location or None, link, posting_id or None, site, alert_date, posted_at or None, injection_signals), and settings in `hiretitan/platform/config/settings.py` (`HIRETITAN_MAIL` = `gmail` or `fake`, `HIRETITAN_FAKE_GMAIL_DIR`, the two Google variables as `SecretStr`); test `tests/unit/mail/test_settings.py`.
- [x] T010a Install the redacting logger at start-up (found while building T008: `configure_logging` existed but the app never called it, so secrets were kept out of logs only by never logging them): `hiretitan/api_main.py` and `hiretitan/worker_main.py` `main()` call `configure_logging(settings.secrets())` (uvicorn `log_config=None`), `Settings.secrets()` lists every secret, and the formatter also scrubs the one-time `code`, `state` and token values in web addresses (uvicorn's access log would otherwise print the Google callback's authorization code); tests in `tests/unit/platform/test_log_redaction.py` (`test_FR003_the_sign_in_callback_address_is_logged_without_its_code`, `test_FR003_settings_list_every_secret_for_the_logger`).
- [x] T011 `hiretitan/mail/infra/fake_gmail.py` (a `MailReader` over a folder of synthetic answers: `profile.json`, `messages/*.eml`, honouring the query's senders and `after:`), test `tests/unit/mail/test_fake_gmail.py`; wiring stub `hiretitan/mail_wiring.py` that picks the real or fake reader.
- [x] T011r Review: database reviewer over T006–T007, security reviewer over T008–T009; fix the findings; note them in `docs/CONTEXT.md`. Rebuild the dev stack.

**Checkpoint**: storage, secrets and network rules ready.

---

## Phase 3: User Story 1 - Connect my Gmail, read-only (Priority: P1) 🎯 MVP

**Goal**: the person connects their own Gmail with read-only access, sees "Connected as …", and can disconnect or reconnect.

**Independent Test**: with the fake Google answers, save credentials, connect, see the connected address, disconnect (revoke called, secrets gone); with a real throwaway account, quickstart §2.

### Tests for User Story 1 ⚠️ (write first, see them fail)

- [x] T012 [P] [US1] (fixtures PROVISIONAL until T004) Contract tests `tests/contract/gmail/test_google_oauth.py` with respx, the recorded fixtures of T004 and a request log: `test_FR002_authorize_url_asks_only_readonly` (scope, `access_type=offline`, `prompt=consent`, PKCE S256, `state`), `test_US1_AS2_code_exchange`, `test_FR005_refresh_invalid_grant_needs_reconnect`, `test_FR002_wider_scope_is_revoked_and_refused`, `test_FR004_revoke`, `test_SC007_oauth_only_posts_token_and_revoke`.
- [x] T013 [P] [US1] (fixtures PROVISIONAL until T004) Contract tests `tests/contract/gmail/test_gmail_profile.py` (recorded fixtures of T004): `test_US1_AS2_profile_gives_address`, `test_FR005_401_after_refresh_ends_access`, `test_SC007_only_get_on_allowed_paths` (a respx check that fails on **any non-GET** to the Gmail host, and on any request outside `users/me/profile`, `users/me/messages`, `users/me/messages/{id}` fails the test).
- [x] T014 [P] [US1] API tests `tests/api/mail/test_connection_api.py`: `test_US1_AS1_not_connected_state`, `test_US1_AS5_connect_without_credentials_409`, `test_US1_AS2_callback_connects_and_redirects`, `test_US1_callback_bad_state_redirects_with_error`, `test_FR002_callback_wrong_scope_revokes`, `test_US1_AS3_disconnect_revokes_and_deletes_keeps_jobs`, `test_FR004_disconnect_stops_a_running_check_and_deletes_read_email_and_check_records`, `test_FR001_no_shipped_credentials_connect_needs_the_persons_own`, `test_US1_AS4_needs_reconnect_shown`, `test_FR003_no_secret_in_any_response`, `test_credentials_from_environment_409`.

### Implementation for User Story 1

- [x] T015 [US1] `hiretitan/mail/infra/google_oauth.py` (authorize URL, PKCE helpers, code exchange, refresh, revoke; `httpx.AsyncClient(base_url=allowed_base_url("oauth2.googleapis.com", ""))`; the granted scope must equal `gmail.readonly`) until T012 passes.
- [x] T016 [US1] `hiretitan/mail/infra/gmail_client.py` profile call with token refresh on 401 once, until T013 passes (list and get come in US2).
- [x] T017 [US1] Use cases `hiretitan/mail/application/connection.py` (save credentials, start consent with a one-time `state` kept 10 minutes, finish callback, disconnect, mark `needs_reconnect`) and router `hiretitan/mail/api/connection.py` (`GET /mail/connection`, `PUT /mail/credentials`, `POST /mail/connect`, `GET /mail/google/callback`, `DELETE /mail/connection`, contract §Connection); event `mail.connection_changed` in `hiretitan/platform/runtime/events.py`; mount in `hiretitan/api_main.py` until T014 passes. Regenerate `backend/openapi.json` and `frontend/src/api/schema.d.ts` (`openapi-typescript` only, no Prettier).
- [x] T018 [P] [US1] Frontend tests first `frontend/src/features/settings/GmailSection.test.tsx` (`US1 AS1 explains read-only and links the guide`, `US1 AS5 asks for the two values`, `US1 AS2 connected as`, `US1 AS3 disconnect asks then shows not connected`, `US1 AS4 reconnect notice`), then `GmailSection.tsx` in `SettingsPage.tsx`; the page reads `?gmail=connected|error` after Google's redirect.
- [x] T019 [P] [US1] Setup guide `docs/gmail-setup.md` (FR-008: project, Gmail API, consent screen External + Testing, test user, Web client, redirect URI from Settings, the 7-day reconnect in testing mode, how to disconnect in the Google account), linked from Settings and the README.
- [ ] T019r [US1] Review: security reviewer (OAuth, state, PKCE, secrets, redirect handling), python/FastAPI reviewer, React reviewer; fix; note in `docs/CONTEXT.md`. Rebuild the dev stack; Ravi connects his own Gmail (quickstart §2, SC-001 timed), then disconnects and checks that his Google account's third-party access page no longer lists the app (SC-006).

**Checkpoint**: Gmail connects and disconnects; nothing is read yet.

---

## Phase 4: User Story 2 - Jobs from my alert emails appear in Explore (Priority: P1)

**Goal**: a check reads the last 24 hours of alert mail from enabled senders, once each, and adds the jobs to Explore through the rules.

**Independent Test**: with the fake Gmail holding the T002 fixtures, press "Check job-alert mail"; every expected job appears once with its site, link and alert date; left-out jobs are on the summary with Restore.

### Tests for User Story 2 ⚠️

- [x] T020 [P] [US2] Unit tests `tests/unit/mail/test_mime.py`: `test_FR013_html_part_flattened_to_links_and_lines`, `test_FR013_text_part_when_no_html`, `test_R13_oversized_message_unreadable`, `test_FR014_invisible_text_and_controls_stripped`.
- [x] T021 [P] [US2] Unit tests `tests/unit/mail/test_links.py`: per site `test_FR022_posting_id_from_link` and `test_FR022_clean_link_drops_tracking`, `test_edge_redirect_link_kept_as_given_never_followed`.
- [x] T022 [P] [US2] Unit tests `tests/unit/mail/readers/test_<site>.py` for each of the six sites over the T002 fixtures against `expected.yaml`: `test_US2_AS3_every_job_in_the_email`, `test_FR013_nothing_invented` (missing company or location stays empty), `test_edge_unknown_layout_returns_nothing`.
- [x] T023 [P] [US2] Unit tests `tests/unit/mail/test_query.py`: `test_FR009_query_only_enabled_senders`, `test_FR011_after_is_start_minus_24h`, `test_FR009_no_free_text_in_query`.
- [x] T024 [P] [US2] (fixtures PROVISIONAL until T004) Contract tests `tests/contract/gmail/test_gmail_messages.py` (recorded fixtures of T004): `test_FR009_list_uses_query_and_pages_to_200`, `test_FR012_more_remaining_flag`, `test_R13_429_retried_then_gmail_unavailable`, `test_SC004_request_log_shows_only_sender_queries`.
- [x] T025 [P] [US2] Workflow tests `tests/workflow/mail/test_check.py` (fake Gmail, real Postgres): `test_US2_AS1_jobs_added_with_site_link_date`, `test_US2_AS2_second_check_reads_nothing_new`, `test_US2_AS4_rules_leave_out_with_reason_restorable`, `test_FR018_not_sent_to_relevance_ai_marked_not_checked`, `test_FR018a_unlisted_company_shown_and_not_created`, `test_US2_AS6_instructions_ignored_signal_shown`, `test_US2_AS7_stop_keeps_jobs_read`, `test_FR016_no_body_stored`, `test_FR017_unreadable_email_counted_not_failed` (a built-in sender's email in an unknown layout, before the AI fallback exists), `test_FR005_access_ended_mid_check`, `test_edge_disconnect_during_check_stops`.
- [x] T026 [P] [US2] API tests `tests/api/mail/test_checks_api.py` and additions to `tests/api/search/test_runs_api.py`, `test_jobs_api.py`: `test_FR021_post_check_202`, `test_check_not_connected_409`, `test_check_while_search_running_409`, `test_runs_include_mail_member`, `test_FR019_source_filter_email_alert`, `test_FR019_job_sources_show_site_and_date`, `test_FR020_may_have_closed_after_30_days`.

### Implementation for User Story 2

- [x] T027 [US2] `hiretitan/mail/domain/mime.py` (stdlib `email` with `policy.default`, `html.parser` flattening, sanitise, 2 MB cap) until T020 passes.
- [x] T028 [US2] `hiretitan/mail/domain/links.py` (posting ids and clean links per site, from research R4 and T005) until T021 passes.
- [x] T029 [US2] Readers `hiretitan/mail/domain/readers/{linkedin,naukri,indeed,foundit,instahyre,cutshort}.py` and the dispatcher `readers/__init__.py` (site → function; at most 60 jobs per email) until T022 passes. [P] across sites once T027–T028 are done.
- [x] T030 [US2] `hiretitan/mail/domain/senders.py::build_query` and `gmail_client.list_ids` / `get_raw` (GET only, retries per R13) until T023–T024 pass.
- [x] T031 [US2] `hiretitan/search/application/alerts.py` + store additions in `hiretitan/search/infra/search_store.py`: `AlertJob` → `normalize_job` → rules (`decided_by = 'rules_only_fallback'` for jobs that pass, reason "Not checked by AI: no description yet") → `NewJob`/`SeenJob` with `source_kind = 'email_alert'`, `ats_vendor = site`, `requisition_id = posting id` → `store_batch`; company id only by lookup, never created; write `alert_sightings` (unique `(job_id, read_message_id)`). The sink is wired in `hiretitan/mail_wiring.py`.
- [x] T032 [US2] Workflow `hiretitan/mail/workflow/check.py` (`mail_check`: create the `mail_alerts` search run and `mail_checks` row → list ids → skip read ones → read in batches of 20 (stop checked between batches) → sink → finish with the summary counts and `ended`), registered in `hiretitan/worker_main.py`; use case and router `hiretitan/mail/api/checks.py` (`POST /mail/checks`); `mail` member on `GET /search/runs*` in `hiretitan/search/api/runs.py`; `email_alert` filter, sources with site and alert date, `may_have_closed` in `hiretitan/search/api/jobs.py`; until T025–T026 pass. Regenerate OpenAPI and the TS schema.
- [x] T033 [P] [US2] Frontend, tests first: `SearchPanel.test.tsx` (`US2 check job-alert mail button`, `US2 AS7 progress and stop`), `RunSummaryPage.test.tsx` (`US2 mail run shows emails read → jobs found → rules → new jobs and could-not-read list`), `ExplorePage.test.tsx` (`FR019 Email alerts filter`, `FR020 may have closed tag`), `JobDetailPage.test.tsx` (`FR019 Email alert · LinkedIn, date`, `US2 AS5 description not known yet, add it`, `US2 AS6 email instruction notice`); then `features/explore/SearchPanel.tsx`, `RunSummaryPage.tsx`, `SearchFlow.tsx` (a mail flow), `ExplorePage.tsx`, `features/jobs/JobDetails.tsx`.
- [x] T033r [US2] (Ravi's own-mail check, quickstart §3, still to do) Review: python/FastAPI, database and security reviewers over T020–T032 (untrusted mail path, no bodies stored, request log, batch transactions), React reviewer over T033; fix; note in `docs/CONTEXT.md`. Rebuild the dev stack; Ravi checks his own mail once (quickstart §3).

**Checkpoint**: alert jobs reach Explore.

---

## Phase 5: User Story 3 - No repeats (Priority: P1)

**Goal**: one job per posting, however many alerts and sources mention it.

**Independent Test**: fixtures with one posting in four emails (two sites, two dates, one link with tracking) plus the same job on a searched board: one job, every sighting listed, a near match from another site in Possible duplicates.

### Tests for User Story 3 ⚠️

- [x] T034 [P] [US3] Workflow tests `tests/workflow/mail/test_dedup.py`: `test_US3_AS1_same_link_in_several_alerts_one_job_all_sightings`, `test_US3_AS2_alert_matches_searched_job_adds_source`, `test_US3_AS3_near_match_other_site_is_candidate_not_merged`, `test_US3_AS4_pipeline_job_not_listed_again_summary_says_which`, `test_US3_AS5_deleted_job_stays_deleted`, `test_US3_AS5_not_the_same_pair_not_proposed_again`, `test_US3_AS6_email_never_read_twice`, `test_SC003_shared_link_or_posting_id_always_one_job`.

### Implementation for User Story 3

- [x] T035 [US3] Make T034 pass in `hiretitan/search/application/alerts.py` and `search_store.py` (exact match by canonical link or `(site, posting id)`, `fuzzy_candidates`, `same_posting_again`, respect `deleted` and "not the same"); the summary's "already in pipeline as <title>" list in the `mail` member.
- [x] T035r [US3] Review: python reviewer over T034–T035; fix; note in `docs/CONTEXT.md`.

**Checkpoint**: the MVP (US1–US3) is complete; Ravi can use it daily with the button.

---

## Phase 6: User Story 4 - Choose which senders count (Priority: P2)

**Goal**: the person sees the built-in senders, switches sites off and adds their own.

**Independent Test**: switch LinkedIn off, add a custom sender, check: LinkedIn not read, the custom sender read, nothing else listed (request log).

- [x] T036 [P] [US4] API tests `tests/api/mail/test_senders_api.py`: `test_US4_AS1_builtin_listed_all_on`, `test_US4_AS2_add_sender_201`, `test_add_duplicate_409`, `test_US4_AS3_switch_off`, `test_delete_builtin_409`, `test_delete_added_204`; workflow tests `test_US4_AS3_switched_off_site_not_queried`, `test_US4_AS2_no_jobs_from_added_sender_counted`.
- [x] T037 [US4] Router `hiretitan/mail/api/senders.py` (`GET/POST /mail/senders`, `PATCH/DELETE /mail/senders/{id}`, contract §Senders) and use cases until T036 passes.
- [x] T038 [P] [US4] Frontend tests first `features/settings/MailSenders.test.tsx` (`US4 AS1 list by site with switches`, `US4 AS2 add a sender`, `built-in cannot be removed`), then `MailSenders.tsx` inside the Gmail section.
- [x] T038r [US4] Review: React and python reviewers; fix; note.

---

## Phase 7: User Story 5 - The last 24 hours, and what a check found (Priority: P3)

**Goal**: checks run daily on their own and after Search now; every summary adds up; Settings says what the window is.

**Independent Test**: with the clock faked, the hourly tick starts a check once 24 hours have passed and not before; Search now queues a mail check after the company run; summary counts add up.

- [x] T039 [P] [US5] Tests `tests/workflow/mail/test_schedule.py`: `test_US5_AS1_daily_tick_checks_after_24h`, `test_FR021_tick_skips_when_search_running`, `test_FR021_tick_checks_soon_after_start_when_overdue`, `test_FR021_search_now_queues_mail_check_when_connected`, `test_FR021_not_connected_never_checks`; `tests/unit/mail/test_summary.py`: `test_SC008_counts_add_up` (jobs found = new + already known + left out + already in pipeline), `test_FR012_200_cap_reported`; `tests/workflow/mail/test_speed.py::test_SC005_fifty_emails_under_two_minutes` (50 fixture emails on the fake Gmail, real Postgres; a generous bound for CI).
- [x] T040 [US5] Periodic task (`cron="7 * * * *"`) in `hiretitan/platform/runtime/procrastinate.py` calling a mail-wiring hook; Search now chaining at the end of the company search workflow (`hiretitan/search/workflow/graph.py` end node enqueues through a callback set in `search_wiring.py`, so `search` still does not import `mail`); until T039 passes.
- [x] T041 [P] [US5] Frontend: Gmail section shows "Each check reads job-alert emails from the last 24 hours" and the last check time (`US5 AS4`); the mail summary shows the 200-cap message (`FR012`); tests first in `GmailSection.test.tsx`, `RunSummaryPage.test.tsx`.
- [x] T041r [US5] Review: python reviewer (scheduling, concurrency with company searches), React reviewer; fix; note.

---

## Phase 8: AI fallback (part of US2, built last)

**Goal**: an email no reader can read goes to the AI with a strict schema; nothing invented; no key means "could not read" and a retry later.

- [x] T042 [P] [US2] Prompt `hiretitan/prompts/read_job_alert/v1/` (`system.md`, `user.md.j2`, `schema.py` with `jobs` ≤ 30, `title ≤ 200`, `company ≤ 120 or null`, `location ≤ 120 or null`, `link_index`; `checks.py`; `meta.yaml` tier `fast`), tests first in `tests/unit/prompts/test_read_job_alert.py` (`test_R5_schema_limits`, `test_FR014_email_only_inside_data_block`).
- [x] T043 [P] [US2] `hiretitan/mail/domain/alert_checks.py`, tests first in `tests/unit/mail/test_alert_checks.py`: `test_FR013a_link_by_index_only`, `test_FR013a_title_and_company_must_appear_in_email`, `test_FR013a_invented_value_dropped`.
- [x] T044 [US2] Fallback step in `hiretitan/mail/workflow/check.py` (built-in reader returns nothing, or sender site `other` → AI; `AiUnavailable` → outcome `needs_ai`, retried while inside 24 hours), tests first in `tests/workflow/mail/test_ai_fallback.py` (`test_FR013a_unknown_layout_read_by_ai`, `test_FR013a_no_key_counts_could_not_read_then_retried`, `test_FR014_planted_instructions_have_no_effect`, `test_SC002_builtin_emails_read_without_ai`).
- [x] T044r Review: security reviewer (prompt injection through mail, link-by-index), python reviewer; fix; note.

---

## Phase 9: Polish & cross-cutting

- [x] T045 [P] Delete all: `hiretitan/setup_wiring.py` also deletes `<data_dir>/secrets/gmail.json`; tests `tests/api/setup/test_delete_all_api.py::test_FR027_removes_gmail_connection_secrets_and_mail_records`.
- [x] T046 [P] Reader eval `backend/evals/mail_alerts/` and task `mail_alerts` in `backend/evals/run.py` (no AI): per-site recall of title, company and link against `expected.yaml`, invented values, share read without AI; tests first in `tests/unit/evals/test_mail_alerts_eval.py`; run it and commit the report under `backend/evals/reports/` (SC-002, readers part). The AI-fallback measurement joins the deferred evals (needs Ravi's key).
- [x] T047 [P] `backend/scripts/check_my_alerts.py`: with a connected install, read the last 24 hours and print only counts per sender and reader (no titles, no companies, no links); test that its output holds no job field (`tests/unit/mail/test_check_my_alerts.py`).
- [ ] T048 Playwright: `.e2e/fake_gmail/` prepared by `frontend/e2e/prepare.mjs` from synthetic fixtures; `docker-compose.e2e.yml` sets `HIRETITAN_MAIL=fake`; journey `frontend/e2e/gmail-alerts.spec.ts` (connect, check, alert jobs with site, a repeat shown once, restore a left-out job, disconnect).
- [ ] T049 Docs: `docs/architecture.md` (the mail module, the two exemptions, the data flow), `docs/clarified-requirements.md` §12 (002c done, Gmail part), README (Gmail setup link), `docs/CONTEXT.md`; success-criteria map `specs/002c-gmail-job-alerts/success-criteria-map.md` (SC-001 to SC-008).
### Settings organised, AI key on the page (US6, added 2026-11-23; folded in at Ravi's request)

- [x] T051 [P] [US6] `hiretitan/platform/llm/key_store.py` (`KeyStore`: `<data_dir>/secrets/llm.json`, atomic write, owner-only, `current() -> (key, source)` with `env` winning, re-read on file change, `save`, `remove`, `secrets()`), tests first in `tests/unit/platform/llm/test_key_store.py` (`test_FR029_round_trip_and_atomic`, `test_FR029_env_wins`, `test_FR029_never_in_repr`, `test_FR030_a_new_key_is_seen_without_restart`).
- [x] T052 [US6] Key provider in the OpenAI adapter and `build_llm` (one SDK client per key, asked on each request), `has_key` from the store, the redaction filter's callable secret source, `after_key_works` re-queues runs paused for `key_missing` / `key_rejected`; tests first: `tests/unit/platform/llm/test_openai_key_provider.py` (`test_FR030_the_adapter_uses_the_current_key`), `tests/unit/platform/test_log_redaction.py::test_SC010_a_key_saved_later_is_redacted`, `tests/workflow/platform/test_key_resume.py::test_FR030_paused_runs_continue_after_a_saved_key_works`.
- [x] T053 [US6] `PUT/DELETE /settings/ai-key` and `ai.key_source` on `GET /status` (contracts §AI key) in `hiretitan/setup/api/`; delete-all removes `llm.json`; tests first in `tests/api/setup/test_ai_key_api.py` (`test_US6_AS2_save_checks_the_key_202`, `test_US6_AS3_key_never_returned`, `test_US6_AS4_env_key_409`, `test_FR029_bad_shape_422`, `test_remove_204`, `test_FR033_delete_all_removes_saved_key`, `test_SC010_key_in_no_response_or_log`). Regenerate OpenAPI and the TS schema.
- [x] T054 [P] [US6] Frontend `features/settings/gmailSteps.ts` (pure: connection, senders and last check → steps with `done` / `current` / `waiting` and the reason a step waits), tests first in `gmailSteps.test.ts` (each state of US6 AS5).
- [x] T055 [US6] Frontend: `SettingsPage` with an index and three parts (`AiSection`, `GmailSetup`, `DataSection`); `AiSection` key form (password field, Save / Replace / Remove, source, status, Check again; the key cleared from the page after saving); `GmailSetup` step list (current open, done reopenable, waiting says why) holding the existing credential form, connect, `MailSenders` (by site, with the site's domain) and the check button; tests first in `SettingsPage.test.tsx`, `AiSection.test.tsx`, `GmailSetup.test.tsx` (US6 AS1 to AS7, keyboard and phone width).
- [x] T056 [US6] Docs: ADR-09 amended in `docs/architecture.md` (key on the page in a secrets file; `.env` still wins), `docs/user-guide/getting-started.md` (key in Settings), `docs/gmail-setup.md` (the steps match the page), README.
- [x] T057 [US6] Review: security reviewer (key storage, redaction, no echo), React reviewer (layout, accessibility, step logic); fix; note in `docs/CONTEXT.md`; rebuild the dev stack for Ravi to look at.

- [ ] T050 Final review (python/FastAPI, database, security, React reviewers over the whole branch); fix; then full gates: backend suite with the coverage gate, ruff, `ruff format --check`, `mypy --strict`, `lint-imports`, licence gate; frontend tests, tsc, eslint, `npm run build`; all Playwright journeys. Push and open the PR to `master` only when Ravi asks.

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (T001–T005) → Foundational (T006–T011r) → US1 (T012–T019r) → US2 (T020–T033r) → US3 (T034–T035r) → US4, US5 (either order) → AI fallback (T042–T044r) → Polish (T045–T050).
- T004 must be done before T015; T005 before T028–T029 are finished (link patterns), but the readers can start on the synthetic fixtures.

### User story dependencies

- **US1** needs only the foundation.
- **US2** needs US1 (a connection to read with; the fake Gmail lets its tests run without Google).
- **US3** needs US2's write path.
- **US4** needs US2's query builder; **US5** needs US2's check workflow.
- The AI fallback needs the readers (US2).

### Within each story

Tests first and failing → domain (pure) → infra → use cases → API → frontend → review.

### Parallel opportunities

- T002, T003 (fixtures, seed) in parallel; T008, T009, T010 in parallel after T006.
- In US1: T012, T013, T014 tests together; T018 and T019 alongside T015–T017.
- In US2: T020–T026 tests together; the six readers of T029 together after T027–T028.
- US4 and US5 in parallel after US3.

## Parallel Example: User Story 2

```text
Tests together: T020 (mime), T021 (links), T022 (six reader test files), T023 (query), T024 (gmail contract), T025 (workflow), T026 (API)
Readers together after T027–T028: linkedin.py, naukri.py, indeed.py, foundit.py, instahyre.py, cutshort.py
```

## Implementation Strategy

### MVP first

US1 + US2 + US3: connect, read a day's alerts with the button, no repeats. Stop and let Ravi use it on his own mail before US4, US5 and the AI fallback.

### Incremental delivery

1. Setup + foundation.
2. US1 → review → Ravi connects.
3. US2 → review → Ravi reads his alerts.
4. US3 → review: MVP.
5. US4, US5 → review.
6. AI fallback → review.
7. Polish → final review → gates → PR when Ravi asks.

## Notes

- Commit only when Ravi asks; one commit per task, format from the `commit` skill.
- Nothing personal in the repository: fixtures are synthetic; T004 and T005 record only flow facts, addresses and URL patterns.
- After each phase: rebuild the dev stack on :8000 and pause for Ravi's review.
- Deferred, not in this feature: application-update mail (next feature), Gmail drafts (needs a constitution amendment), the AI-fallback eval with a real key (with the 002k evals).
