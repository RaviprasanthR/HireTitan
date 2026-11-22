# Research: Gmail job alerts (002c)

Decisions for [plan.md](plan.md). Each: **Decision**, **Rationale**, **Alternatives considered**. Items marked **Verify** are checked in a named task before the code that depends on them is written.

## R1. Connecting to Gmail: direct Gmail API with the person's own OAuth client (not MCP)

**Decision**: HireTitan talks to the Gmail REST API itself, over `httpx`, with an OAuth 2.0 *Web application* client that the person creates in their own Google Cloud project (setup guide). Scope requested: exactly `https://www.googleapis.com/auth/gmail.readonly`. Authorization-code flow with PKCE (S256) and a random `state`; the redirect URI is the install's own callback, `http://localhost:<port>/api/v1/mail/google/callback`, shown in Settings so the person registers the exact value. The token response's `scope` must equal `gmail.readonly` (nothing more); otherwise HireTitan revokes the token at once and refuses (FR-002). The address comes from `users/me/profile`.

**Rationale**: the worker must read mail on a schedule without any AI client open, so the reader belongs to HireTitan, not to an assistant. A direct client lets HireTitan ask for read-only access and nothing else, keeps one network boundary it can allowlist and contract-test, and needs no extra process. Each install uses its own client because Google forbids sharing one client secret across an open-source product's users, and personal apps stay in Google's "testing" mode (no verification; the person adds their own address as a test user). In testing mode Google expires refresh tokens after 7 days, which the reconnect path (FR-005) covers.

**Alternatives considered**: a Gmail MCP server (needs Claude or another MCP client running; typically broader scopes, often including send; an extra process); Google's Python client libraries (`google-api-python-client`, `google-auth-oauthlib`: large, synchronous, and harder to keep inside the outbound allowlist); IMAP with an app password (needs full mailbox access, and the no-send test bans `imaplib`); a *Desktop* OAuth client with a loopback port (works, but a fixed web callback on the app's own port is simpler in Docker).

**Verify and record (T004, Ravi with a throwaway Google account)**: on a throwaway Google account, a Web client with `http://localhost:8000/...` as redirect URI works in testing mode, and the granted `scope` string is exactly `gmail.readonly`.

## R2. Reading only alert mail: Gmail search by sender and time, then one GET per message

**Decision**: a check lists messages with `GET users/me/messages?q=from:(<a> OR <b> ...) after:<epoch>&maxResults=100` (paged, at most 200 ids), where the addresses are the enabled senders and `<epoch>` is the check's start minus 24 hours. Ids already in `mail_read_messages` are skipped. Each remaining message is fetched with `GET users/me/messages/{id}?format=raw`, parsed with the standard library's `email` parser (`policy.default`), and its HTML part (else its text part) is read, then dropped (FR-016). The query string is built from the sender list only, never from free text.

**Rationale**: Gmail applies the sender and date filter on its side, so HireTitan never lists or opens other mail (FR-009, SC-004); a recorded request log in the contract tests shows every request's query. `format=raw` gives one standard MIME parse path. 200 messages per check (FR-012) is about two list pages and 200 small GETs, well under Gmail's per-user quota.

**Alternatives considered**: `format=full` (Gmail's JSON part tree: a second parsing path for the same content); history-based sync (`users/me/history`; needs a stored history id and still has to filter by sender; more state for no gain at this volume); Gmail push notifications (needs a public endpoint; out of scope for a localhost app).

## R3. Built-in sender list

**Decision**: a seed file `backend/seed/mail_senders.yaml` lists each site with its job-alert sender addresses; loaded into `mail_senders` (built-in rows, on by default; the person can switch them off and add their own). Candidate addresses come from the sites' public help pages and common knowledge; they are **not verified**. Per site the reader also matches the *link pattern* (R4), so a wrong or missing address only costs coverage, never wrong data.

| Site | Candidate alert senders (to verify) |
|---|---|
| LinkedIn | `jobalerts-noreply@linkedin.com`, `jobs-listings@linkedin.com` |
| Naukri | `naukrialerts@naukri.com`, `info@naukri.com` |
| Indeed | `alert@indeed.com`, `donotreply@jobalert.indeed.com` |
| foundit | `alerts@foundit.in` |
| Instahyre | `alerts@instahyre.com` |
| Cutshort | `hello@cutshort.io` |

**Verify (T005)**: the maintainer checks each address in their own Gmail (search box, by hand) and corrects the seed; only addresses are recorded, never mail content. Addresses that belong to the sites are public facts, not personal data (constitution VIII).

**Amended 2026-11-22 (Ravi)**: the site's own domain (`SITE_DOMAINS` in `mail/domain/senders.py`) is asked for next to the addresses, for a site that is switched on; the real address may differ from these guesses. The cost is that connection requests, messages and receipts from those domains are also fetched and parsed on this computer: only an email a fixed reader finds jobs in is kept (and recorded as `read`); anything else is recorded as `no_jobs` with reader `domain` (id, sender, time only), never sent to the AI, never shown as unreadable. A message whose real From address is neither a listed address nor at a site's domain is still refused.

**Alternatives considered (first version)**: whole domains (`from:linkedin.com`: would also read messages, connection requests and receipts, against FR-009; accepted later, see above); a label the person sets up with a Gmail filter (extra work for every person; can be added later as a sender kind).

## R4. Fixed readers per site, on the standard-library HTML parser

**Decision**: one pure function per built-in site turns an alert's HTML into `AlertJob` records (title, company, location, link as given, posting id, site). A shared step, built on `html.parser.HTMLParser`, flattens the HTML into an ordered list of blocks: each link with its text and the text lines around it. A site reader keeps the links whose URL matches that site's job-link pattern and takes title, company and location from the link text and the lines that follow it. Posting ids come from the link: LinkedIn `/jobs/view/(\d+)`, Indeed `jk=([0-9a-f]{16})`, Naukri the trailing numeric id of `job-listings-…-(\d+)`, and the others where their link shows one (**Verify** in T005 against the maintainer's own alerts, locally). Readers never follow a link (no request to these sites, FR-015).

**Rationale**: no new dependency; pure functions are fast, deterministic and unit-testable on synthetic emails; a site that changes its template only falls back to the AI (R5). Most alert emails are lists of links, so "link plus nearby lines" covers them.

**Alternatives considered**: BeautifulSoup or selectolax (new dependencies for a narrow need); the AI for every email (cost, and every email would go to the provider; the person chose readers first).

## R5. AI fallback for emails no reader can read

**Decision**: an email from a built-in site that its reader cannot read, or from a sender the person added, goes to a new prompt `read_job_alert` v1 (fast tier). Input: the email's flattened blocks, sanitised (`platform.untrusted.sanitize`), screened (`screen`), capped at 20,000 characters and delimited; links are given as a numbered list. Output schema: `jobs` (at most 30), each `{title ≤ 200, company ≤ 120 or null, location ≤ 120 or null, link_index}`. A job is kept only if its `link_index` exists and its title (and company, when given) appear in the email text, case and spacing ignored (FR-013, nothing invented). No AI key or `AiUnavailable`: the email is stored as `needs_ai` (counted as "could not read") and retried on the next check while it is still inside the 24-hour window. Every call is logged by the LLM port as usual.

**Rationale**: constitution III: raw untrusted text reaches only a tool-less step with a strict, bounded schema; the link comes from the email by index, so the AI cannot invent a URL. The person chose this split.

**Alternatives considered**: free-form AI output with URLs (an injection could plant a link); no fallback (an email in a changed layout silently yields nothing).

## R6. One job, however many alerts: reuse the search's exact keys and candidates

**Decision**: an alert job gets `ats_vendor = <site>` (`linkedin`, `naukri`, …) and `requisition_id = <posting id>` when the link shows one, and `canonical_url` = the site's clean posting URL built from that id (tracking parameters dropped) or, without an id, the link with known tracking parameters removed. The existing `dedup.exact_match` (same canonical link, or same vendor and requisition) then finds repeats across alerts and against searched or pasted jobs; `fuzzy_candidates` proposes possible duplicates; `same_posting_again` keeps a pipeline job from being listed twice (FR-022 to FR-024). Jobs in the state `deleted` and pairs marked "not the same" keep their meaning because the search store already treats them that way (**Verify** in T034 with tests).

**Rationale**: one deduplication rule set for every source, already tested and reviewed.

**Alternatives considered**: a separate alert-only dedup table (two rule sets that drift apart).

## R7. Where the Google secrets live

**Decision**: the OAuth client id and secret and the refresh token are stored in one file, `<HIRETITAN_DATA_DIR>/secrets/gmail.json`, written atomically, with owner-only permissions where the file system has them. The client id and secret may instead come from the environment (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`), which then wins. Access tokens are kept in memory only. The file is never logged, returned by the API (the API returns only "set" or "not set") or passed to the AI; the log redaction filter learns the key names. Disconnect and "Delete all my data" delete the file.

**Rationale**: constitution: secrets only from local configuration (setup wizard or environment), never in logs or prompts; the data directory is the install's local configuration and is already on the person's volume. Keeping secrets out of PostgreSQL keeps them out of database dumps.

**Alternatives considered**: a database column (ends up in every dump); encrypting with a key on the same machine (no real protection; more code); environment only (the refresh token changes at runtime and cannot be written back to `.env`).

## R8. A mail check is a search run with mode `mail_alerts`

**Decision**: a check creates a `search_runs` row with `mode = 'mail_alerts'` (no companies) plus a `mail_checks` row with the mail-specific counts. New jobs, sightings of known jobs, rule decisions and possible duplicates go through the existing `store_batch`, one batch per 20 emails. Rules decide; alert jobs never reach the AI relevance check while they have no description, and are stored with the existing decision `rules_only_fallback`, shown as "not checked by AI" (FR-018). The run therefore appears in Search history, has a summary page (with mail counts instead of company results), lists left-out jobs with Restore, and is covered by the existing "one search at a time" rule.

**Rationale**: the summary, Restore, history, events and concurrency rules exist and are tested; a parallel "mail run" would duplicate all of them.

**Alternatives considered**: a separate mail-check table and screens (duplication); folding mail into the company search's workflow (couples two sources; a failing Gmail would affect company search, against constitution VII "sources isolated").

## R9. When checks run: a periodic worker task, plus the button and Search now

**Decision**: a procrastinate periodic task (`cron="7 * * * *"`, hourly) starts a check when Gmail is connected, no search is running, and the last check started more than 24 hours ago (or never). This also covers "soon after HireTitan starts" (FR-021). "Check job-alert mail" starts one at once. "Search now" starts the company search as today; when that run ends, its workflow enqueues a mail check if Gmail is connected. The window is always the 24 hours before the check starts (FR-011).

**Rationale**: procrastinate 3.10 (already used) has `App.periodic`; the hourly tick needs no new process and makes the daily check robust to restarts.

**Alternatives considered**: a once-a-day cron at a fixed hour (missed when the machine is off at that hour); an in-process asyncio timer in the API (lost on restart, and runs in two places when scaled).

## R10. Network rules and the no-send guarantee

**Decision**: `outbound_allowlist.ALLOWED_HOSTS` gains `gmail.googleapis.com` and `oauth2.googleapis.com`. Two modules may build clients for them, each a named exemption in `test_no_send.py` like the careers fetcher: `mail/infra/gmail_client.py` (GET only, to exactly `users/me/profile`, `users/me/messages` and `users/me/messages/{id}`) and `mail/infra/google_oauth.py` (POST only to `/token` and `/revoke`). Contract tests intercept every request (respx) and fail on any other method or path, in particular `send`, `drafts`, `modify`, `trash`, `delete`, `batchModify` and `labels` (FR-007, SC-007). The browser, not the server, opens `accounts.google.com`.

**Rationale**: constitution I requires that no adapter can send; listing the only allowed requests and testing them is stronger than banning names.

**Alternatives considered**: banning only `send` (misses `drafts.create` and changes to mail).

## R11. Untrusted mail and stored data

**Decision**: the email body is processed in memory and discarded; stored per message: Gmail id, sender, received time, outcome (`read`, `no_jobs`, `unreadable`, `needs_ai`), jobs found, injection signals. Per job: the fields of FR-013 plus an *alert sighting* (site, link as given, alert date). Injection signals from `screen()` over the flattened text are stored on the message and copied to the jobs it yielded (FR-014; shown with the 002k wording adapted: "This email contains text that looks like instructions to an AI. HireTitan ignored it.").

**Rationale**: FR-016 (no bodies kept), constitution III and VIII.

## R12. Testing without anyone's mail

**Decision**: synthetic `.eml` fixtures per site under `backend/tests/fixtures/mail/` (made-up companies and people, the sites' layouts imitated), at least 10 per built-in site for SC-002; Gmail API and OAuth contract fixtures are **recorded** from a throwaway Google account in T004 (profile, a message list, a raw message, token and revoke answers; tokens, addresses and ids replaced with synthetic values; no personal data), served with respx, as constitution V requires for each external adapter. The reader eval `mail_alerts` scores SC-002 on the fixtures without any AI; the AI-fallback part needs the person's key and runs with the deferred evals. A small helper, `backend/scripts/check_my_alerts.py` (committed; it holds no mail), lets anyone with a connected install run the readers over their own last 24 hours and print only counts per sender and reader; its output is never committed (T005).

**Rationale**: constitution V and VIII: real Postgres, fakes only at external boundaries, no personal data in the repository.

## R13. Limits

**Decision**: at most 200 messages per check (FR-012), 20 per batch; a message larger than 2 MB raw is skipped as `unreadable` (alert emails are far smaller); at most 60 jobs taken from one email; Gmail errors 429 and 5xx are retried twice with back-off, then the check ends with "Gmail did not answer"; a 401 after one refresh attempt ends with "access ended" and sets the connection to `needs_reconnect`.
