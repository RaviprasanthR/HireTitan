# Research: Mikasa, the chat assistant

**Feature**: `002m-mikasa-chat` · **Date**: 2026-11-24 · **Spec**: [spec.md](spec.md)

Findings from reading the code on `master` (after PR #19), and the decisions they lead to. Each entry: Decision, Rationale, Alternatives considered.

## What the code has today

- `platform/llm/port.py`: one method, `generate(LlmRequest[T]) -> LlmResult[T]`: one structured answer per call, no tools, no streaming. Only the OpenAI adapter exists (Responses API, strict `json_schema`), plus the scripted `FakeLlm`. Tiers (`fast` = `gpt-5.4-mini`, `strong` = `gpt-6-astra`) come from `models.yaml`; each prompt fixes its tier in `meta.yaml`. There is **no per-person model choice** today.
- `platform/runtime/events.py`: server events through Postgres `NOTIFY`, a closed `EVENT_TYPES` set, read by the front end's `useEvents` hook (SSE with a 3 s poll fallback), which invalidates TanStack Query keys.
- Use cases live in each module's `application` layer, but some rules sit in the routers (for example `POST /jobs/{id}/applied` checks "already applied" in `search/api/jobs.py` before calling `mark_applied`).
- **There is no "hide this job" action in the UI.** Jobs are hidden only by the rule filter; the person can restore a hidden job (`POST /jobs/{id}/restore`) or delete a job (soft delete).
- **Adding a job by paste needs a description** (`search/application/paste.py`: `DESCRIPTION_MIN`), and nothing in the app fetches a single job link.
- Undo exists for applied and inquired (`undo_applied`, `undo_inquired`); the UI shows it as a toast.
- Delete all truncates every table in schema `app` (`setup_wiring._wipe_once`), so new tables are covered without code changes.
- 002k's `job_keywords` table holds a bounded, structured summary of each job description, made by the tool-less `extract_job_keywords` step.
- Import-linter already keeps contacts and interview code out of `search.workflow`, `drafts.workflow`, `prompts` and `platform.llm` (`contacts-stay-out-of-ai-paths`).
- The front end has only a `Button` in `components/ui`; popovers use Radix directly.

## R1 Tool calling and streaming in the LLM port

**Decision**: Add a second port method, `converse(req: ConverseRequest) -> AsyncIterator[ConverseEvent]`. The request carries the task name, the rendered versioned system prompt, the message history (person, Mikasa, tool call, tool result), the tool specs (name, description, JSON schema of the arguments, built from each action's Pydantic model), the tier and an output cap. The adapter yields `TextDelta`, `ToolCall(id, name, arguments_json)` and one final `TurnEnd(usage, provider, model, outcome)`. `AiUnavailable` and `RetryableLlmError` behave as in `generate`. The OpenAI adapter uses the Responses API in streaming mode with strict function tools. `FakeLlm` gains scripted turns (lists of events) by task, so every chat test runs offline. Each model round inside a turn is logged in `llm_calls` (task `mikasa_turn`, prompt version, model, tokens, latency, outcome).

**Rationale**: `generate` returns one validated object; a chat turn needs text as it arrives and several tool rounds. A separate method keeps every existing caller unchanged. Validation still happens (constitution IV): tool arguments are validated against the action's Pydantic model, and the reply text against R9's rules.

**Alternatives**: Forcing tool calls into `generate`'s structured output (a "plan" schema the app executes): no streaming, and one round per call makes multi-step questions slow. LiteLLM or an agent framework: rejected in the requirements (own thin adapters).

## R2 Where a chat turn runs

**Decision**: In the API process, as a streamed response to `POST /assistant/conversations/{id}/turns` (SSE via `sse-starlette`, already a dependency). A turn is at most 6 tool rounds and 90 seconds. One turn per conversation at a time (a row lock on the conversation; a second message while one runs gets `409 turn_running`, EC-01). Work a turn starts that takes long (a search run, a mail check, a draft) is enqueued on the existing worker exactly as the UI does; the turn only reports that it started.

**Rationale**: A turn is interactive and short; the person waits for it. Nothing needs to survive a restart except the stored messages, cards and change records, which are rows. Running it on the worker would need token-by-token events through `NOTIFY` (an 8 KB payload limit and a lot of traffic) for no gain.

**Alternatives**: A LangGraph workflow per turn with an interrupt for each confirm card. The cards are durable rows that the person may confirm much later, so a graph checkpoint adds a second copy of the same state; justified in Complexity Tracking.

## R3 One action layer, shared with 007

**Decision**: A new package `hiretitan.actions` at the same level as the `*_wiring.py` files. Each action is an `ActionSpec`: name, description for the model, Pydantic argument model, kind (`read`, `small`, `risky`), `private` flag (R5), the handler (gets a session and the arguments, returns a typed result), for small changes an `undo` handler, for risky changes a `targets` function that returns fingerprints of the rows it will touch (R7), and the query keys the front end refreshes. Handlers call the same application functions the routers call. Where a router holds a rule today (for example "already applied"), that rule moves into the application function first, and both the router and the action call it. A parity test per action runs the action and the matching endpoint on the same data and compares the result. The catalogue is in [contracts/actions.md](contracts/actions.md). The kind is part of the spec, never chosen by the model (FR-010).

**Rationale**: FR-006 (same rules as the UI) and FR-028 (shared with 007). Placing the package beside the wiring lets it import every module's `application` and `infra`, which the boundary contracts forbid inside a feature module. The chat module (`hiretitan.assistant`) sees the catalogue only through a protocol, so its tests use small fake catalogues.

**Alternatives**: Mikasa calling the REST endpoints over HTTP from inside the API: it doubles serialization, and the transaction, undo and fingerprint data would not be available. Ports per action in `assistant/application`: about 50 interfaces with one implementation each.

## R4 Outside text never reaches the model that plans actions

**Decision**: Action results sent back to the model hold only bounded, structured fields: ids written as refs (R5), titles and company names (sanitized, at most 200 characters, screened with the existing `screen()`), states, dates, counts, rule reasons, and for a job's description only the stored `job_keywords` result (made by the tool-less extraction step), never the description itself. A title or company name with an injection signal is replaced by `[hidden: looks like instructions]` in the model's copy, and the person sees the signal on the job card. Every action result goes to the model inside a delimited data block that the system prompt names as data. Page text and email text are never part of any action result. A job description reaches the app from the chat only through the **Paste a job description** button in the composer, which runs the paste use case directly; the text never goes to the model (FR-021). A typed message is capped at 2,000 characters and screened. Signals are stored on the message and shown, but a person's own message is still treated as theirs. A typed message over 600 characters with posting markers (two or more headings such as "responsibilities", "requirements", "qualifications", "about the role", "what you'll do", "benefits") is refused with `422 looks_like_posting` before any model call, and the panel offers to move it into the paste dialog (FR-021). **Accepted risk**: a short posting excerpt typed as a message reaches the model as the person's own words; it can only lead to small changes the person can undo or to cards the person must confirm, and the eval's planted-instruction set includes such messages.

**Rationale**: Constitution III allows only structured, bounded data into a step with tools. With no free text from outside in its context, an injection has only short, screened titles to ride on. Reusing `job_keywords` gives "what does this job ask for" without a new prompt.

**Alternatives**: A separate summarising step per question over the raw description: another prompt and call for each question, and its free-text output would bring the risk back. Sending descriptions inside quarantine markers only: constitution III forbids raw untrusted text in a step with tools.

## R5 Private data: refs, filled in by the app

**Decision**: Actions marked `private` (contacts, company notes, interview contact, source, rounds, questions, answers, feedback, resume files and the resume used for a job) return to the model only a ref and a label that HireTitan builds from non-private fields, for example `{"ref": "contact:7c1e…", "label": "a contact at Acme"}` or `{"ref": "round:91af…", "label": "an interview round for Backend Engineer at Zoho"}`. The model writes refs into its reply as tokens (`[[contact:7c1e…]]`), and the panel renders each one as a card filled from the existing endpoints, so the person sees names, dates and notes, and the model never does. Finding by name (`find_contact(company, name)`) matches on the server and returns refs only. Arguments the person typed (for example a phone number for a new contact) pass through the model because they are in the person's message (FR-022b); the stored values are never read back to it. Enforcement: (1) private handlers return a `PrivateResult` type whose model-facing form holds only `ref` and `label`, checked by a unit test over every private action; (2) import-linter adds `hiretitan.assistant` to `contacts-stay-out-of-ai-paths`; (3) SC-010's recorded-call test plants distinctive synthetic values in every private table and asserts that no LLM request contains any of them.

**Rationale**: Ravi chose "Act, never send". 002k's placeholders already prove the approach. The person still gets complete answers on screen.

**Alternatives**: Masking (send "P*** at Acme"): leaks part of the data and still needs a rule per field.

## R6 Small changes and Undo

**Decision** (spec FR-014 allows Undo to restore the exact earlier state even where the UI has no separate control, such as re-hiding a restored job): Small changes are applied at once in one transaction that also writes a **change record**: action, target kind and id, the touched fields before and after (as JSON), and a list of the rows the change created. Undo (`POST /assistant/changes/{id}/undo`) runs the action's `undo` handler only if the target's current values still equal `after` (EC-16), otherwise `409 changed_since`. It is allowed for 24 hours and only on the latest change to that item. Undoing an **add** (a job or company Mikasa just created) removes the row for good when nothing else points to it, so the link can be added again later. A normal job delete is soft and blocks re-adding the link. Undo for applied and inquired calls the existing `undo_applied` and `undo_inquired`.

**Rationale**: FR-014 and EC-16. Comparing with `after` needs no version column on existing tables.

**Alternatives**: A `version` column on every touched table: a migration across six modules for the same guarantee. A generic "restore before-image" with no handler: it skips the rules the use case applies.

## R7 Confirm cards for risky changes

**Decision**: A risky action call becomes a **card** row: the list of changes (action name, arguments as validated), fingerprints of every target (a hash of the target's current fields from the action's `targets` function), `expires_at` 30 minutes after creation, and state `proposed`. `POST /assistant/cards/{id}/confirm` (optionally with edited values, validated by the action's argument model) moves `proposed → applying` with `UPDATE … WHERE state = 'proposed'`, so a double click applies once (EC-03). It then re-checks the fingerprints (a mismatch moves the card to `expired` with `409 stale`, EC-02) and applies every change in one transaction (FR-012). Work that runs on the worker is enqueued after the commit, as the routers do. Cancel and expiry change nothing. A card holds at most 25 items; a bigger request is refused with a link to the page that does it in bulk (EC-05). Changes a card applies also write change records, so each can be undone where the action has an undo.

**Rationale**: FR-010 to FR-013. Fingerprints catch "the job changed since Mikasa proposed it" without locks held while the person thinks.

**Alternatives**: Holding the turn open until the person confirms: ties a stream and a connection to a human's pace.

## R8 Streaming to the panel

**Decision**: The turn response is `text/event-stream` with these events: `text` (a piece of the reply), `ref` (a ref token was written, so the panel can prefetch the card), `change` (a small change was applied: summary, undo id, query keys), `card` (a confirm card was created), `notice` (for example an injection signal), `error` (reason and the provider's message for credit), and `done` (the message id and whether it was stopped). The front end reads it with `fetch` and a small stream parser (no new dependency), because `EventSource` cannot `POST`. **Stop** aborts the fetch; the server sees the disconnect, cancels the model stream and stores what was written, marked `stopped`. After a change, the panel invalidates the action's query keys, and the server publishes a new `assistant.changed` event so other open tabs refresh too (FR-004).

**Rationale**: FR-002 and FR-004 with the event stream already in place.

**Alternatives**: WebSockets: a second transport to secure and test. Polling: no live text.

## R9 Checking the model's reply

**Decision**: The reply text is checked before it is stored: every ref token must be one an action returned in this conversation (unknown refs are removed and logged); every job, company or page link must point to a route that exists; at most 4,000 characters. An unknown tool name or arguments that fail validation get one repair: the validation error goes back to the model as the tool result. A second failure ends the turn with "I couldn't do that" and a logged `refused` outcome (FR-025, EC-09). No action from a failed call is ever applied or carded.

**Profile claims (FR-018a, constitution II)**: when a turn called `get_profile`, the reply also goes through the deterministic claim check 002k already uses for drafts (numbers, technology terms, employer and title names, dates, each looked up in the confirmed profile). The check is reached through a `ProfileClaimsChecker` port in `assistant/application/ports.py`, implemented in `assistant_wiring.py` over `drafts/domain/checks.py`, so `assistant` does not import `drafts`. A failing reply gets one repair (the unbacked terms are sent back as the reason); a second failure replaces the claim sentences with "I don't see that in your profile" and a link to Profile. Text is streamed as it arrives, so in a turn that read the profile the reply is buffered and checked before it is shown; the panel shows "Checking against your profile…" meanwhile.

**Rationale**: Constitution IV: validate, repair once, then a defined fallback; constitution II for anything said about the person.

## R10 Conversation memory

**Decision**: Each turn sends the system prompt, the tool specs, and the last 30 messages of the conversation (the person's messages, Mikasa's replies with ref tokens, and this turn's tool calls and results). Earlier turns' tool results are not resent; the model calls the action again if it needs fresh data, which also keeps answers current. Older messages are dropped from the model's copy, not summarised; the person still sees the whole conversation (EC-06).

**Rationale**: Bounded tokens and no stale data. A summary would be one more model output to validate.

## R11 Model and capability

**Decision**: Prompt `mikasa_chat/v1` with tier `fast` in its `meta.yaml`, like every other prompt. There is no per-person model picker (none exists today; the spec's assumption is corrected). `models.yaml` gains `capabilities` per model (`tools`, `streaming`); a model without them makes `GET /assistant/status` report `model_lacks_tools`, and the panel shows FR-024's message. The eval compares `fast` and `strong` before v1 is accepted.

## R12 Adding a job from a link

**Decision**: HireTitan does not fetch the link in this feature. The paste use case gains a **link-only** mode: link, title and company are required, the description is optional (it can be added later with the existing **Add description**). The UI's paste dialog gets the same option ("I don't have the description"), so Mikasa does nothing the UI cannot (FR-006). Mikasa looks the link up first (`find_job_by_link`, using the existing canonical-URL dedup). If it is new and the person gave no title or company, she asks for them, then adds the job and marks it applied as one small change with one Undo. A job with no description is skipped by the rule filter's description rules and by tailoring (which already asks for a description).

**Rationale**: Constitution VII forbids fetching LinkedIn, Naukri and similar sites. Reading single postings from public ATS APIs is permitted but needs a resolver per vendor; it is left for a later feature. Ravi's example still works in one message when it names the role and company ("I applied to <link>, Backend Engineer at Acme").

**Alternatives**: Fetching through the careers-page reader for allowed hosts: robots.txt and allowlist handling for arbitrary hosts, and a JavaScript-only page fails anyway. Recorded as a later idea in `docs/CONTEXT.md`.

## R13 The panel

**Decision**: A launcher button in the shell header (and the keyboard shortcut `Ctrl+/`) opens a right-hand panel, an `<aside>` fixed beside the page (not a modal), 420 px wide on desktop and full screen below 768 px. The reply is rendered as plain text plus our own token parsing for refs and in-app links; no HTML or Markdown renderer, so text from jobs can never run (EC-13). Confirm cards show each change with editable fields for its arguments, plus **Confirm** and **Cancel**. Change notices show **Undo**. A one-line note under the composer says "What you type here is sent to your AI provider. Contacts, notes and interview details stored in HireTitan are not" (FR-022b). No new dependency.

## R14 What Mikasa cannot do

**Decision**: Delete all, the AI key, Gmail connect, disconnect and credentials, profile review confirm and discard, resume upload, and onboarding are **not in the catalogue**, so the model has no way to call them (FR-016). The system prompt lists them with the page to link, and the eval checks the decline and link (SC-006). Profile facts are read-only (FR-018). Draft text is edited only on its page, never by Mikasa, because text the model writes into a draft would skip 002k's truthfulness checks; Mikasa can only request a new draft through the draft action. "Send" requests are declined (FR-017), and `test_no_send.py` scans `hiretitan.actions` and `hiretitan.assistant`.

## R15 Evaluation

**Decision**: `evals/mikasa/` with synthetic data only: at least 40 action requests across the catalogue (right action, item and values on the first try), 15 jobs and alerts with planted instructions in titles and company names (no change or card follows), 20 questions with no answer in the data (no invented value), the FR-016 decline set, and off-topic requests. Scored offline with the scripted fake in CI for the harness. The real-model run (`python -m evals.run mikasa --models fast,strong --yes`) is Ravi's, before merge, as for 002c's T067. SC-002 (first words within 3 s) is measured in the same run.

## R16 Module name

**Decision**: The back-end module is `hiretitan.assistant` and the front-end folder `features/assistant`. "Mikasa" is the name shown in the panel and the persona in the prompt. Renaming her later then means changing text, not code.
