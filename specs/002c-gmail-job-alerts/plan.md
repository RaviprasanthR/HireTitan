# Implementation Plan: Gmail job alerts

**Branch**: `002c-gmail-job-alerts` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002c-gmail-job-alerts/spec.md`

## Summary

The person connects their own Gmail with read-only access, using an OAuth client they create in their own Google Cloud project. Once a day while HireTitan runs (and on "Check job-alert mail" or after "Search now"), HireTitan asks Gmail only for messages from the enabled job-alert senders received in the last 24 hours, reads each new one once, and turns the jobs it lists into Explore entries. Each entry is marked "Email alert · <site>", filtered by the approved rules and deduplicated with the rules every other source uses.

Approach: a new module `hiretitan.mail` holds the connection (OAuth, secrets file), the sender list, the read-once registry, the Gmail client (GET only, three paths), and the alert readers. The readers are fixed per site, built on the standard library's HTML parser, with an AI fallback that has a strict schema. A mail check is a search run with `mode = 'mail_alerts'`, so the existing batch writer, summary page, Restore, history, events and "one search at a time" rule all apply ([research R8](research.md#r8-a-mail-check-is-a-search-run-with-mode-mail_alerts)). The module is reusable: the next feature (application-update mail) adds a sender purpose and its own reader on the same connection.

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22).

**Primary Dependencies**: as today (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, procrastinate (now also its periodic tasks), LangGraph, `httpx`, rapidfuzz, Jinja2 prompts; React 19, TanStack Query, Tailwind 4). **No new dependency**: OAuth and Gmail over `httpx`, MIME with the standard library's `email`, HTML with `html.parser` (research R1, R2, R4). `respx` (dev) for contract tests.

**Storage**: PostgreSQL 16, schema `app`. New tables `mail_connection`, `mail_senders`, `mail_read_messages`, `mail_checks`, `alert_sightings`; CHECKs widened on `job_sources.kind` and `search_runs.mode` ([data-model.md](data-model.md)); migration `0023_mail_alerts` (parent `0022`). Secrets in `<data_dir>/secrets/gmail.json`, not in the database (R7). Seed file `backend/seed/mail_senders.yaml`.

**Testing**: pytest + Testcontainers Postgres (repos, CHECKs, cascades, delete-all, API, workflow); pure unit tests for the MIME flattening, each site reader, posting-id and clean-link rules, the query builder, the AI-output checks; contract tests with respx, against recorded fixtures, for every Google request, with a log of every request (SC-004, SC-007); the scripted fake LLM for the fallback; a fake Gmail (`HIRETITAN_MAIL=fake`, synthetic answers from a folder) for the e2e stack; the reader eval `mail_alerts` (no AI) for SC-002. Vitest for the Settings and Explore pieces; one Playwright journey.

**Target Platform**: unchanged (`docker compose up`, browser on `localhost`). The OAuth callback needs the browser to reach the API at the redirect URI shown in Settings.

**Project Type**: web application (api + worker + SPA).

**Performance Goals**: a day's alerts (≤ 50 emails) in under 2 minutes (SC-005); a fixed reader takes under 50 ms per email; at most one AI call per unreadable email.

**Constraints**:
- Read-only: the only Google requests are those in [contracts/rest-api.md](contracts/rest-api.md#outbound-requests-the-only-ones-contract-tests-enforce-them); no send, draft, modify, trash or delete (constitution I; `test_no_send.py` exemptions plus contract tests, R10).
- Only mail from enabled senders inside the 24-hour window is listed or opened (FR-009); bodies are not stored (FR-016).
- Alert text is untrusted: sanitised, screened, delimited; only the tool-less fallback step with a bounded schema sees it, and links are chosen by index (constitution III, R5).
- No posting page of LinkedIn, Naukri, Indeed and the others is ever fetched (constitution VII, FR-015).
- Secrets never in logs, API answers or prompts (constitution VIII, R7).
- `hiretitan.mail` imports no other feature module; `search` does not import `mail`; the composition root (`mail_wiring.py`) joins them through a port (`AlertJobsSink`).
- Gmail failures end only the mail check; company searches and everything else keep working (constitution VII, isolated sources).

**Scale/Scope**: one person, tens of alert emails a day. 1 migration, 1 prompt, 10 endpoints + 4 extended, 2 events, 1 new back-end module, 1 periodic task, 1 seed file, 2 new UI areas (Settings → Gmail with senders; the check button and mail summary on Explore), setup guide in `docs/gmail-setup.md`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | Read-only scope, checked on the token response (a wider grant is revoked). The Gmail client may only GET three paths; the OAuth module may only POST to Google's token and revoke endpoints; contract tests fail on anything else, including send, drafts and modify (R10). No message is ever sent or changed. | ✅ | ✅ |
| **II. Truthful profile** | Not touched: no candidate facts are read or written. | ✅ | ✅ |
| **III. Untrusted input is data** | Mail is sanitised, screened (signals stored and shown on the job) and delimited. Fixed readers are deterministic code. Only the fallback prompt sees raw text; its output is a bounded schema, links by index, and titles and companies must appear in the email (R5). Alert jobs never reach the relevance AI without a description. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | One versioned prompt `read_job_alert` v1 (fast tier) through the LLM port; schema, then checks; no repair loop (a failed read is "could not read"); every call logged. No cost shown. | ✅ | ✅ |
| **V. Test-first** | Tests first, named after FR/US/SC ids; real Postgres; fakes only for Gmail and Google OAuth (external boundary, contract-tested against fixtures recorded from a throwaway account in T004), the LLM and the clock. | ✅ | ✅ |
| **VI. Lean architecture** | One new port at a real boundary: the mail provider (`MailReader`: profile, list, get) is a job source. `AlertJobsSink` joins `mail` and `search` at the composition root; justified below. Readers are plain functions; no reader registry framework. | ✅ | ✅ |
| **VII. Permitted sources only** | "The user's own email inbox (read-only)" is a permitted source. Nothing is scraped; alert links are shown, never fetched. Mail failures stay inside the mail check. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Each install uses its own Google client; tokens stay in the person's data folder; no mail bodies stored; Disconnect revokes with Google; Delete all removes the connection, secrets and every mail record (tested). Fixtures are synthetic; the built-in sender addresses are the sites' public addresses. `docker compose up` still works without Gmail set up. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter (new `mail-boundary` contract; `mail` added to the layers contract), coverage gate, licence gate (no new packages), no-send test (two named exemptions), frontend gates with `npm run build`, Playwright with a fake Gmail. | ✅ | ✅ |

**Result**: passes. Three items are justified in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002c-gmail-job-alerts/
├── spec.md
├── plan.md              # this file
├── research.md          # R1–R13
├── data-model.md
├── quickstart.md
├── contracts/
│   └── rest-api.md
├── checklists/
│   └── requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0023_mail_alerts.py
├── seed/mail_senders.yaml
├── scripts/check_my_alerts.py               # counts only; output never committed
├── evals/mail_alerts/                       # reader eval (SC-002), synthetic emails
├── src/hiretitan/
│   ├── mail/                                # NEW: reusable mail reading
│   │   ├── domain/                          # pure
│   │   │   ├── senders.py                   # address rules, site values, query builder
│   │   │   ├── mime.py                      # raw message → flattened blocks (links + lines)
│   │   │   ├── links.py                     # per-site posting id, clean link, tracking params
│   │   │   ├── readers/                     # linkedin.py, naukri.py, indeed.py, foundit.py,
│   │   │   │                                # instahyre.py, cutshort.py (one function each)
│   │   │   └── alert_checks.py              # AI output checks (text must appear, link by index)
│   │   ├── application/ports.py             # MailReader, SecretsStore, AlertJobsSink
│   │   ├── infra/
│   │   │   ├── models.py, repos.py          # mail_* tables
│   │   │   ├── secrets_file.py              # <data_dir>/secrets/gmail.json
│   │   │   ├── google_oauth.py              # POST token, revoke only (exemption)
│   │   │   ├── gmail_client.py              # GET profile, list, get only (exemption)
│   │   │   └── fake_gmail.py                # HIRETITAN_MAIL=fake for e2e
│   │   ├── workflow/check.py                # mail_check workflow (list → read batches → finish)
│   │   └── api/{connection,senders,checks}.py
│   ├── prompts/read_job_alert/v1/           # system, user, schema, checks, meta (fast)
│   ├── search/
│   │   ├── infra/models.py                  # alert_sightings; widened CHECKs
│   │   ├── application/alerts.py            # AlertJob → rules → dedup → store_batch
│   │   └── api/{runs,jobs}.py               # mail member, email_alert source, may_have_closed
│   ├── mail_wiring.py                       # composition: mail ⇄ search
│   ├── platform/security/outbound_allowlist.py  # + gmail.googleapis.com, oauth2.googleapis.com
│   ├── platform/runtime/procrastinate.py    # periodic mail tick
│   └── api_main.py, worker_main.py, setup_wiring.py (delete-all removes the secrets file)
└── tests/
    ├── unit/mail/, contract/gmail/, integration/mail/, api/mail/, workflow/mail/
    ├── fixtures/mail/                       # synthetic .eml per site, Gmail API answers
    └── architecture/                        # no-send exemptions, import contracts

frontend/src/
├── features/settings/GmailSection.tsx       # credentials, connect, status, disconnect
├── features/settings/MailSenders.tsx        # list, switch, add, remove
├── features/explore/SearchPanel.tsx         # "Check job-alert mail"; mail run summary
├── features/explore/RunSummaryPage.tsx      # mail flow chart: emails read → jobs → rules → new
├── features/explore/ExplorePage.tsx         # source filter "Email alerts", "may have closed"
└── features/jobs/JobDetails.tsx             # "Email alert · LinkedIn, 18 Nov" sources

docs/gmail-setup.md                          # the setup guide (FR-008), linked from Settings
frontend/e2e/gmail-alerts.spec.ts            # fake Gmail journey
```

**Structure Decision**: web application layout as before; one new back-end module beside `search`, `profile` and `drafts`.

## Delivery order

1. **Setup and verification**: rebase on `master` after PR #18; T004 (OAuth in testing mode on a throwaway account) and T005 (the maintainer checks the sender addresses and link patterns against their own alerts, locally, counts only).
2. **Foundation**: migration, models, repos, secrets file, allowlist and no-send exemptions, import contracts.
3. **US1 connect** (P1): credentials, consent, callback, scope check, disconnect, reconnect state, Settings section, setup guide. Review.
4. **US2 + US3 read and deduplicate** (P1): MIME flattening, readers, links and ids, the check workflow, `search/application/alerts.py` through `store_batch`, sightings, Explore and the summary page. Review.
5. **US4 senders** (P2), **US5 window and summary** (P3), the periodic tick and Search now chaining. Review.
6. **AI fallback** (part of US2, last because it depends on the readers' failures): prompt, checks, `needs_ai` retry.
7. **Polish**: delete-all, events, Playwright, eval report, docs, gates.

Pause for the person's review after every phase.

## Amendment 2026-11-23: Settings organised, AI key on the page (US6, FR-028 to FR-033)

Folded into Phase 9 at Ravi's request. Constitution check: no new dependency; secrets stay out of the database and the repo (VIII); the key is never logged or returned (III); TDD as usual.

**AI key store (`hiretitan.platform.llm.key_store`).** `KeyStore` keeps an OpenAI key in `<data_dir>/secrets/llm.json` (`{"openai_api_key": "..."}`), written atomically with owner-only permissions where supported, like `gmail.json`. `current()` answers `(key, source)` with source `env` (the `OPENAI_API_KEY` setting, which wins), `page` (the file) or `none`; the file is read again only when its modification time changes. Platform code, because both the API and the worker read it, and `mail` must not be imported by `platform`.

**No restart (FR-030).** The OpenAI adapter takes a key *provider* instead of a key: on each request it asks the store for the current key and keeps one SDK client per key. `ProviderStatusService.has_key` already accepts a callable. Saving a key in the API defers the existing `check_provider_key` task; when the worker finds the key working it re-queues the runs paused for `key_missing` / `key_rejected` (the existing `after_key_works` hook, widened from `out_of_credit` to those reasons).

**Redaction (SC-010).** The log redaction filter gains a callable source of secrets, so a key saved after start-up is scrubbed too; `configure_logging` passes `KeyStore.secrets`.

**API (`hiretitan.setup`, contracts/rest-api.md §AI key).** `PUT /settings/ai-key` (save or replace; 422 shape check; 409 `key_from_environment`; 202 and a key check deferred), `DELETE /settings/ai-key` (204; 409 `key_from_environment`), and `GET /status` gains `ai.key_source`. Delete all my data removes `llm.json` (FR-033).

**Frontend (`features/settings/`).** `SettingsPage` becomes three parts with an index of anchor links: `AiSection` (status, source, a password field with Save / Replace / Remove, Check again), `GmailSetup` (an ordered step list built from `GET /mail/connection`, `GET /mail/senders` and the last check: Google client, Connect, Senders, First check; each `done` / `current` / `waiting`, current open, done reopenable; the existing credential form, connect button, `MailSenders` and check button move into the steps), and `DataSection` (the existing Delete all my data). Pure step logic in `gmailSteps.ts` with its own tests. Styles follow the theme tokens; no new UI library.

## Amendment 2026-11-24: the AI reads alerts first (FR-013b to FR-013e, SC-011)

Ravi's first real LinkedIn alert showed the guessed fixed layouts missing the company. Constitution check: no new dependency or prompt (the existing `read_job_alert` v1 and its `accept` checks are reused, so "AI never invents" holds: a value not in the email is dropped); the email's sanitised text was already allowed to reach the provider for the fallback, now for every alert when a key is set (said in the spec, the Settings Gmail part and the user guide); no-send rule unchanged; TDD as usual; the eval gate (SC-011) must pass before the PR merges.

**Check step (`mail/workflow/check.py`).** `_read_one` runs the fixed readers as now (they also decide whether domain-only mail is an alert), then asks the AI when `deps.ai` is set and the email came from an enabled sender address, or came through a site's domain and a fixed reader found jobs. `_ask_ai` becomes "AI first": an answer with accepted jobs is merged with the fixed reader's jobs by clean link (the AI's fields win; fixed-reader jobs whose link the AI did not return are added); an AI that cannot be asked, an unusable or empty answer, or the cap leave the fixed reader's result as it was (an email the fixed readers could not read keeps today's `needs_ai`/`unreadable` handling). `AI_EMAILS_MAX` goes from 30 to 50; `reader` is `ai`, or `ai+<site>` when both contributed.

**Footer guard (`mail/domain/alert_checks.py`).** A pure `is_boilerplate(text)` over a short phrase list (case-insensitive, start of line) used by `accept` and by the fixed readers' common output step: such a value becomes empty (a title that is boilerplate drops the job).

**Fixing stored jobs (`search/application/alerts.py`, `search/infra/search_store.py`).** `AlertPosting` gains `read_by: "ai" | "fixed"`; for an exact match whose sources are all `email_alert` and whose state is not applied/inquired, the store updates `company_name`/`location_text` (and `company_id` by name lookup) following FR-013d. The job remembers who gave its company in `jobs.alert_read_by` (nullable text, migration).

**Read the last day again (FR-013e).** `POST /mail/checks` takes `{"reread_last_day": true}`; under the existing one-check lock the API deletes `mail_read_messages` rows received in the last 24 hours (sightings keep their job; their `read_message_id` goes null as now on delete) and starts the check. Contract in `contracts/rest-api.md`. Frontend: a secondary button in the Gmail part's First check step and after a check's summary, with a one-line note that it reads the last 24 hours again with the AI.

**Eval (`backend/evals/read_job_alert/`).** Runner over `tests/fixtures/mail` (all 62 + the 3 unknown layouts + the planted-instruction emails) with `expected.yaml`, scoring SC-011; `python -m evals.run read_job_alert --models fast --yes`, prints a cost estimate first, stops on `AiUnavailable`. Report in `evals/reports/`.

**E2E.** The Gmail journey runs the scripted AI: add scripted `read_job_alert` replies for its fixture alerts so it covers the AI-first path; a no-key journey is not needed (unit and workflow tests cover the fallback).

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Port `MailReader` (`gmail_client` and `fake_gmail`) | Gmail is an external job source: constitution VI allows a port there, and the e2e stack needs a scripted mailbox. | Calling `httpx` from the workflow directly: no fake for e2e, and contract tests could not pin the adapter's only requests. |
| `AlertJobsSink` at the composition root | `mail` must stay reusable by the next feature and must not import `search` (import-linter); `search` must not depend on Gmail. The sink is one function: hand over a batch of alert jobs and get the counts back. | `mail` importing `search` directly: the application-update feature would then pull in the whole search module, and the boundary contract would be gone. |
| Two named exemptions in `test_no_send.py` | Reading Gmail needs a client on Google's hosts, and the token and revoke calls are POSTs. Each exemption lists its exact allowed requests, enforced by contract tests. | Allowing `httpx` clients in `mail` generally: the no-send guarantee would rest on review alone. |
