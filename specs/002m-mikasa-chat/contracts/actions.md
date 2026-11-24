# Action catalogue: what Mikasa can call

**Feature**: `002m-mikasa-chat` · Package `hiretitan.actions` (shared later with 007 `mcp-access`, FR-028)

Each action matches something the UI does today, and calls the same application function as the endpoint named (FR-006). **Kind** is fixed here, never chosen by the model (FR-010):

- **read**: changes nothing, no card.
- **small**: one item, applied at once, change record and Undo (R6).
- **risky**: confirm card first (R7).

**Private** actions return only refs and labels to the model (R5). The parity test for each action compares it with its endpoint (test `test_FR006_parity_<action>`).

Common argument rules: ids are refs the model got from an earlier action in the conversation (`job:<uuid>`), never typed ids. Free-text arguments are capped (titles 200, names 120, notes 2,000). Dates are ISO dates in the person's time zone. A bulk form takes 1 to 25 refs.

## Jobs and search results

| Action | Kind | Private | Endpoint it mirrors | Notes |
|---|---|---|---|---|
| `search_jobs` | read | | `GET /jobs` | filters: tab (explore, pipeline), bucket (match, maybe, hidden), state (applied, inquired), company text, title text, posted or marked between, limit ≤ 50; returns refs, title, company, city, bucket and reason, state, dates |
| `get_job` | read | | `GET /jobs/{id}` | fields above, source, link, injection-signal flag, and the stored `job_keywords` (skills, seniority, years); never the description (R4) |
| `find_job_by_link` | read | | `POST /jobs/paste` dedup lookup | canonical-URL match; returns a ref or "not in HireTitan" |
| `get_pipeline_summary` | read | | `GET /pipeline/summary` | counts by state and latest round state (counts only; round contents stay private) |
| `mark_applied` | small | | `POST /jobs/{id}/applied` | optional date (not in the future); undo = `DELETE /jobs/{id}/applied` |
| `unmark_applied` | small | | `DELETE /jobs/{id}/applied` | undo = mark again with the old date |
| `mark_inquired` | small | | `POST /jobs/{id}/inquired` | as above |
| `unmark_inquired` | small | | `DELETE /jobs/{id}/inquired` | |
| `restore_job` | small | | `POST /jobs/{id}/restore` | a hidden (skipped) job back to Explore; undo hides it again with its old reason (spec FR-014) |
| `add_job` | small | | `POST /jobs/paste` (link-only mode, R12) | link, title, company required, location optional, no description (that comes only through the composer's paste button); undo removes the job for good if nothing points to it |
| `add_job_and_mark` | small | | `POST /jobs/paste` + `POST /jobs/{id}/applied` or `/inquired` | Ravi's example as one change, one Undo |
| `mark_applied_many` / `mark_inquired_many` / `restore_jobs` | risky | | as the single forms | 1 to 25 refs, one card |
| `delete_job` | risky | | `DELETE /jobs/{id}` | |
| `recheck_job` | risky | | `POST /jobs/{id}/recheck` | AI work |
| `merge_duplicate` / `dismiss_duplicate` | risky | | `POST /jobs/duplicates/{id}/merge`, `/dismiss` | |

The composer's **Paste a job description** button (not a model tool) calls `POST /assistant/conversations/{id}/paste`, which runs the full paste use case (or, for a job already in HireTitan, `PUT /jobs/{id}/description`) and records a small change with Undo; the text never reaches the model (FR-021).

## Searches and mail

| Action | Kind | Private | Endpoint | Notes |
|---|---|---|---|---|
| `get_latest_search` | read | | `GET /search/latest` | counts by bucket, sources, finished at, running or not |
| `list_search_runs` / `get_search_run` | read | | `GET /search/runs`, `/runs/{id}` | |
| `start_search` | risky | | `POST /search/runs` | refused with progress if one is running (EC-11) |
| `stop_search` | risky | | `POST /search/runs/{id}/stop` | |
| `get_mail_status` | read | | `GET /mail/connection`, senders, last check | connected or not, last check, counts; no email text |
| `start_mail_check` | risky | | `POST /mail/checks` | "read the last day again" included as an option; answers `not_connected` with a link to Settings → Gmail when Gmail is not connected (EC-12) |
| `add_mail_sender` / `edit_mail_sender` / `delete_mail_sender` | risky | | `/mail/senders` | |

## Companies and contacts

| Action | Kind | Private | Endpoint | Notes |
|---|---|---|---|---|
| `search_companies` / `get_company` | read | | `GET /companies` | name, city, website, careers link, board, hidden, applied flag |
| `add_company` | small | | `POST /companies` | careers page optional (002c change); undo removes it if nothing points to it |
| `edit_company` | small | | `PATCH /companies/{id}` | named fields only, including hiding or showing one company; undo restores them |
| `hide_companies` / `delete_company` | risky | | `PATCH` (2 to 25 companies), `DELETE /companies/{id}` | |
| `confirm_board` / `reject_board` | risky | | `/companies/{id}/discovery/confirm`, `/reject` | |
| `list_contacts` / `find_contact` | read | yes | `GET /companies/{id}/contacts` | refs and labels only; name matching on the server |
| `add_contact` / `edit_contact` | small | yes | `POST`, `PATCH /companies/{id}/contacts` | values come from the person's message (FR-022b); result is a ref |
| `delete_contact` | risky | yes | `DELETE …/contacts/{id}` | |
| `get_company_note` | read | yes | (note on the company) | ref only, the panel shows it |
| `set_company_note` | small | yes | `PUT /companies/{id}/note` | |

## Interviews and the resume used

| Action | Kind | Private | Endpoint | Notes |
|---|---|---|---|---|
| `get_interview` / `list_rounds` | read | yes | `GET /jobs/{id}/interview` | refs and labels only; `list_rounds(upcoming)` is sorted on the server so the panel shows dates |
| `set_interview_contact` / `set_interview_source` | small | yes | `PUT /jobs/{id}/interview/contact`, `/source` | |
| `add_round` / `edit_round` | small | yes | `POST /jobs/{id}/interview/rounds`, `PATCH /interview/rounds/{id}` | type, date and time, interviewers, state, feedback |
| `add_question` / `edit_question` | small | yes | `POST …/questions`, `PATCH /interview/questions/{id}` | |
| `delete_round` / `delete_question` / `clear_interview_contact` | risky | yes | the matching `DELETE`s | |
| `list_resume_files` | read | yes | `GET /pipeline/resumes` | refs only (002f FR-013) |
| `set_resume_used` | small | yes | `PUT /jobs/{id}/interview/resume` | |
| `clear_resume_used` | risky | yes | `DELETE /jobs/{id}/interview/resume` | |

## Drafts and tailored resumes

| Action | Kind | Private | Endpoint | Notes |
|---|---|---|---|---|
| `list_drafts` / `get_tailored_resume` | read | | `GET /jobs/{id}/drafts`, `/tailored-resume` | refs, kind, made at; the panel shows the text (draft text is not sent back to the model) |
| `draft_connection_request` / `draft_referral_message` | risky | | `POST /jobs/{id}/drafts` | recipient is a contact ref or a typed name and role (002k placeholders keep the contact out of the AI) |
| `tailor_resume` | risky | | `POST /jobs/{id}/tailored-resume` | |
| `delete_draft` / `delete_tailored_resume` | risky | | the matching `DELETE`s | |

Draft text is not editable by Mikasa (R14).

## Profile, preferences, rules, review, settings

| Action | Kind | Private | Endpoint | Notes |
|---|---|---|---|---|
| `get_profile` | read | | `GET /profile` | confirmed facts only (skills, titles, employers, dates, education); the person's own contact details are left out, as in 002k |
| `get_preferences` | read | | `GET /preferences` | |
| `update_preferences` | risky | | `PUT /preferences` | named fields; the card shows before and after |
| `get_search_rules` | read | | `GET /search/rules` | |
| `edit_rule_proposal` | risky | | `POST /search/rules/proposal/from-approved` + `PUT /proposal` | the person approves it on the Search rules page or on the card, as the UI does |
| `approve_rule_proposal` / `discard_rule_proposal` | risky | | `POST /proposal/approve`, `DELETE /proposal` | |
| `list_review_items` | read | | `GET /status/review-items` | |
| `get_settings` | read | | `GET /status`, `/onboarding` | non-secret values only; whether a key is set, never the key |
| `set_display_name` | risky | | `PUT /onboarding/name` | |

## Not in the catalogue (FR-016, R14)

`POST /data/delete-all`, `PUT`/`DELETE /settings/ai-key`, `POST /status/ai/check`, `/mail/connect`, `/mail/credentials`, `DELETE /mail/connection`, `/profile/reviews/{id}/confirm`, `/discard`, `PUT /profile/reviews/{id}/draft`, `POST /profile/resumes` (upload), `POST /profile/versions`, `POST /onboarding/complete`, `POST /contacts/linkedin-import` (a file upload), `PUT /drafts/{id}` (draft text), `PUT /jobs/{id}/tailored-resume` (resume text). Mikasa declines and links to the page: Settings, Settings → Gmail, Profile review, Profile, the job's drafts.

## Model-facing result shapes

```text
ReadResult    { items: [ { ref, ...bounded fields } ], total, truncated }
PrivateResult { items: [ { ref, label } ], total }            # never field values
ChangeResult  { change_id, summary, refs }                     # small change applied
CardResult    { card_id, summary }                             # risky change proposed
ActionError   { reason, message }                              # e.g. not_found, already_applied
```

All of them are wrapped in a data block before they reach the model (R4).
