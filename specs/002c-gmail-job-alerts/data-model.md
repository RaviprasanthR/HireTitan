# Data model: Gmail job alerts (002c)

PostgreSQL 16, schema `app`. Migration `0023_mail_alerts` (parent `0022`, from 002k; this branch is rebased on `master` after PR #18 merges). New module `hiretitan.mail` owns the `mail_*` tables; `hiretitan.search` owns `alert_sightings` and the two widened CHECKs. Secrets are not in the database ([research R7](research.md#r7-where-the-google-secrets-live)).

## mail_connection (one row at most)

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| provider | text | `'gmail'` (CHECK) |
| address | text | 3 to 320 characters; the account's address from `users/me/profile` |
| state | text | `connected`, `needs_reconnect` (CHECK) |
| connected_at | timestamptz | |
| last_check_started_at | timestamptz null | set when a check starts; the hourly tick compares it with now − 24 h |
| last_error | text null | ≤ 300 characters, shown in Settings ("Gmail access has ended …") |
| created_at, updated_at | timestamptz | |

A unique index on `(provider)` keeps one row. "Not connected" = no row. Disconnect deletes the row and the secrets file.

## mail_senders

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| address | text | lower-cased, 3 to 320 characters, one `@`, UNIQUE |
| site | text | `linkedin`, `naukri`, `indeed`, `foundit`, `instahyre`, `cutshort`, `other` (CHECK) |
| purpose | text | `job_alert` (CHECK; the next feature adds `application_update`) |
| built_in | boolean | built-in rows come from `seed/mail_senders.yaml`; they can be switched off, not deleted |
| enabled | boolean | default true |
| created_at, updated_at | timestamptz | |

Seeding inserts missing built-in addresses and never changes `enabled` on existing rows (like the company list).

## mail_read_messages

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| provider_message_id | text | Gmail's message id, ≤ 64 characters, UNIQUE |
| sender | text | ≤ 320 |
| received_at | timestamptz | Gmail's `internalDate` |
| purpose | text | `job_alert` |
| outcome | text | `read`, `no_jobs`, `unreadable`, `needs_ai` (CHECK) |
| reader | text null | `linkedin`, …, `ai`; which reader produced the jobs |
| jobs_found | integer | ≥ 0, ≤ 60 |
| injection_signals | jsonb | array (`jsonb_typeof = 'array'`), default `[]` |
| mail_check_id | uuid FK → mail_checks(id) ON DELETE SET NULL | |
| read_at | timestamptz | |

No subject, no body, no snippet. A `needs_ai` row is read again by a later check inside its 24-hour window (its outcome then changes); every other outcome is final.

## mail_checks

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| search_run_id | uuid FK → search_runs(id) ON DELETE CASCADE, UNIQUE | the run that carries jobs, decisions and the summary |
| trigger | text | `daily`, `button`, `search_now` (CHECK) |
| window_start | timestamptz | check start − 24 h |
| emails_listed | integer | ids Gmail returned for the query (≤ 200) |
| emails_skipped | integer | already read in an earlier check |
| emails_read | integer | |
| emails_unreadable | integer | `unreadable` + `needs_ai` + `no_jobs` |
| more_remaining | boolean | more than 200 matched |
| ended | text null | `finished`, `stopped`, `access_ended`, `gmail_unavailable` (CHECK) |
| created_at, updated_at | timestamptz | |

Counts satisfy `emails_listed = emails_skipped + emails_read + emails_unreadable` when `ended = 'finished'` (CHECK with `ended`).

## alert_sightings (search module)

| Column | Type | Rules |
|---|---|---|
| id | uuid PK | |
| job_id | uuid FK → jobs(id) ON DELETE CASCADE | |
| read_message_id | uuid FK → mail_read_messages(id) ON DELETE SET NULL | |
| site | text | same values as `mail_senders.site` |
| link | text | as given in the email, ≤ 2000 |
| alert_date | timestamptz | the email's received time |
| posted_at | timestamptz null | only when the alert states a posting date (drives "may have closed", FR-020) |
| created_at | timestamptz | |

UNIQUE `(job_id, read_message_id)`. Index on `job_id`; partial index on `read_message_id IS NOT NULL`.

## Changes to existing tables

- `job_sources.kind`: CHECK widened with `email_alert`. A job found in alerts has one `email_alert` source per distinct clean link (the existing UNIQUE `(job_id, kind, url)`); the per-email detail is in `alert_sightings`.
- `search_runs.mode`: CHECK widened with `mail_alerts`. Such a run has an empty `company_order`; its counts (`jobs_found`, `skipped_by_rules`, `added`, `merged`, `not_checked_by_ai`) are filled by `store_batch` as for company runs.
- `jobs`: no new column. Alert jobs use `ats_vendor = <site>`, `requisition_id = <posting id>` and `canonical_url` for deduplication (research R6); `description = ''`, description status `none`; `company_id` only when the name matches a listed company (no company is created, FR-018a).
- `relevance_decisions`: alert jobs that pass the rules get `decided_by = 'rules_only_fallback'` with the reason "Not checked by AI: no description yet" (FR-018).

## Relationships

```
mail_connection (0..1)
mail_senders 1 ─── n (by address) mail_read_messages
mail_checks 1 ─── 1 search_runs
mail_checks 1 ─── n mail_read_messages
mail_read_messages 1 ─── n alert_sightings n ─── 1 jobs
```

## State: the connection

```
(none) ──connect ok──▶ connected ──401 after refresh / invalid_grant──▶ needs_reconnect
   ▲                       │                                              │
   └──────disconnect───────┴──────────────disconnect──────────────────────┘
needs_reconnect ──reconnect ok──▶ connected
```

## Disconnect

Disconnect deletes `mail_connection`, the secrets file's token, `mail_read_messages` and `mail_checks` (the check's search run, jobs and sources stay; `alert_sightings.read_message_id` becomes NULL). If the person reconnects, alerts of the last 24 hours are read again and deduplication keeps them from repeating.

## Delete all my data

The existing wipe truncates every table in `app` (the new ones included) and must also delete `<data_dir>/secrets/gmail.json`; a new clean-up step in `setup_wiring` does it (tested).
