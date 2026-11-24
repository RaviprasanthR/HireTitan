# REST contract: Gmail job alerts (002c)

Base `/api/v1`. JSON in and out; errors are `application/problem+json` (RFC 9457) as elsewhere, with a `reason` member where the UI needs one. Secrets never appear in any response.

## Connection (`hiretitan.mail`, router prefix `/mail`)

### GET /mail/connection

```json
{
  "state": "not_connected | connected | needs_reconnect",
  "address": "person@example.invalid | null",
  "credentials_set": true,
  "credentials_from_environment": false,
  "redirect_uri": "http://localhost:8000/api/v1/mail/google/callback",
  "last_check_started_at": "2026-11-18T09:07:00Z | null",
  "last_error": "string | null",
  "window_hours": 24
}
```

### PUT /mail/credentials

Body `{"client_id": "…", "client_secret": "…"}` (each 10 to 300 characters, no spaces). Saves them to the secrets file (research R7). `409 reason=credentials_from_environment` when they come from the environment. Response: `GET /mail/connection`'s body.

### Errors on the connection endpoints

`503 reason=secrets_unreadable` when the secrets file is damaged or busy (`PUT /mail/credentials`, `POST /mail/connect`); the callback never answers anything but `302`.

### POST /mail/connect

Starts the Google consent. Response `200 {"authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?…"}`; the page navigates there. The URL carries `scope=https://www.googleapis.com/auth/gmail.readonly`, `access_type=offline`, `prompt=consent`, PKCE `code_challenge` (S256) and a one-time `state` (kept 10 minutes). `409 reason=no_credentials` when the client id or secret is missing (US1 AS5).

### GET /mail/google/callback?code=…&state=…

Google redirects here. Checks `state`, exchanges the code (POST to Google's token endpoint), checks that the granted scope is exactly `gmail.readonly`, reads the address, stores the refresh token, creates or updates `mail_connection`. Always answers `302` to the app: `/settings?gmail=connected`, or `/settings?gmail=error&reason=<denied|wrong_scope|state|exchange_failed>`. A wrong scope is revoked before redirecting.

### DELETE /mail/connection

If a mail check is running it is asked to stop first and Disconnect waits for it to end. Then revokes the refresh token with Google (best effort; a failed revoke is reported, the local data is removed anyway) and deletes the secrets file's token, the `mail_connection` row and the records of emails read and of mail checks. `200 {"revoked": true|false}`: `false` means Google could not be reached, so the person is told to remove the app at myaccount.google.com/permissions. Works even when the secrets file is damaged (it is removed). Jobs, their sources and the search runs stay.

## Senders

### GET /mail/senders

`{"items": [{"id", "address", "site", "built_in", "enabled"}]}`, built-in first, by site.

### POST /mail/senders

Body `{"address": "digest@board.example"}`. Lower-cased; must be a valid address. `201` with the item (`site: "other"`, `built_in: false`). `409 reason=sender_exists`.

### PATCH /mail/senders/{id}

Body `{"enabled": false}`. `200` with the item.

### DELETE /mail/senders/{id}

Only for senders the person added; `409 reason=built_in` otherwise. `204`.

## Checks

### POST /mail/checks

Starts a check now (`trigger = button`). `202 {"search_run_id": "…"}`. `409 reason=not_connected`, `409 reason=search_running` (one search at a time), `409 reason=needs_reconnect`, `409 reason=rules_not_approved`. A check that hits an unexpected error ends as `failed` (`mail.ended = failed`); a message whose `From` display name is itself an address is never trusted (no jobs are read from it).

Optional body *(added 2026-11-24, FR-013e)*: `{"reread_last_day": true}` forgets which emails of the last 24 hours were read, in the same transaction that creates the check (only once no other check or search runs; a `409` forgets nothing), so they are read again. No body, or `false`, is a plain check.

Stopping uses the existing `POST /search/runs/{id}/stop`.

### Existing endpoints, extended

- `GET /search/runs/{id}` and `GET /search/runs`: `mode` may be `mail_alerts`; a new member `mail` is `null` for company runs and for mail runs is
  ```json
  {"trigger": "daily", "window_start": "…", "emails_listed": 12, "emails_skipped": 3,
   "emails_read": 8, "emails_unreadable": 1, "more_remaining": false,
   "ended": "finished", "unreadable": [{"sender": "…", "received_at": "…", "why": "no_jobs"}]}
  ```
- `GET /search/latest`: unchanged shape; may return a mail run.
- `POST /search/runs` (Search now): unchanged; when the company run ends and Gmail is connected, a mail check (`trigger = search_now`) is queued.
- `GET /jobs` filter `source`: new value `email_alert`.
- Job cards and `GET /jobs/{id}`: `sources[]` items may have `kind: "email_alert"`, with `site` and `alert_date`; a new boolean `may_have_closed` (FR-020); `injection_flags` include mail signals with `location: "email"`.

## AI key (`hiretitan.setup`, router prefix `/settings`) *(added 2026-11-23, US6)*

### PUT /settings/ai-key

Body `{"key": "sk-..."}`. The key must be 20 to 300 characters with no spaces (`422` with `errors=[{"field": "key", "message": ...}]`). `409 reason=key_from_environment` when `OPENAI_API_KEY` is set. Saves it to `<data_dir>/secrets/llm.json` and defers a key check; `202 {"key_source": "page", "status": "unknown"}`. The key is never echoed.

### DELETE /settings/ai-key

Removes a key saved on the page. `204`; `409 reason=key_from_environment` when the key comes from the environment. AI tasks then pause as for a missing key.

### GET /status (existing, extended)

`ai` gains `key_source`: `env`, `page` or `none`.

## Events (server-sent, existing stream)

`search.batch_done` and `search.finished` as for company runs (a mail run's batch event carries `emails_read`, `emails_listed` and `added`); new `mail.connection_changed` (state only) so Settings refreshes.

## Outbound requests (the only ones; contract tests enforce them)

| Module | Method | URL |
|---|---|---|
| `mail/infra/google_oauth.py` | POST | `https://oauth2.googleapis.com/token` |
| `mail/infra/google_oauth.py` | POST | `https://oauth2.googleapis.com/revoke` |
| `mail/infra/gmail_client.py` | GET | `https://gmail.googleapis.com/gmail/v1/users/me/profile` |
| `mail/infra/gmail_client.py` | GET | `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=…&maxResults=…&pageToken=…` |
| `mail/infra/gmail_client.py` | GET | `https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}?format=raw` |
