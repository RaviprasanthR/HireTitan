# Implementation Plan: Mikasa, the chat assistant

**Branch**: `002m-mikasa-chat` | **Date**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002m-mikasa-chat/spec.md`

## Summary

Mikasa is a chat panel inside the app that answers questions about the person's own data and does what the UI does, through the same rules. Small changes to one item happen at once with an Undo; risky changes wait for a confirm card. She never sends anything, never changes profile facts, never reads outside text raw, and never passes the stored contents of contacts, notes, interview data or the resume picker to the AI.

Approach: the LLM port gains a streaming, tool-calling method `converse` (OpenAI Responses API; scripted in `FakeLlm`). A new package `hiretitan.actions` defines about 60 actions once (kind `read`, `small` or `risky`, a `private` flag, the same application functions the routers call), for Mikasa now and for 007 later. A new module `hiretitan.assistant` runs each turn in the API process as an SSE stream: the versioned prompt `mikasa_chat/v1` (tier `fast`), up to 6 tool rounds, results as bounded structured data blocks, private results as refs the panel fills in. Four tables keep conversations, messages, confirm cards and change records (migration `0026_assistant`). The front end adds a right-hand panel opened from the shell. Decisions: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22).

**Primary Dependencies**: as today (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, procrastinate, `sse-starlette`, OpenAI SDK behind the LLM port, Jinja2 prompts; React 19, TanStack Query, React Router, Tailwind 4, Radix). **Nothing added.**

**Storage**: PostgreSQL 16, schema `app`. New tables `assistant_conversations`, `assistant_messages`, `assistant_cards`, `assistant_changes` ([data-model.md](data-model.md)); migration `0026_assistant` (parent `0025_alert_read_by`). No column changes on existing tables.

**Testing**: pytest + Testcontainers Postgres; the scripted fake LLM with recorded tool-call turns; recorded OpenAI stream fixtures for the adapter contract; a recorded-call privacy test (SC-010); a parity test per change action (FR-006); Vitest + Testing Library; a new Playwright journey with the scripted AI. One eval set, synthetic only. Test names follow [contracts/rest-api.md](contracts/rest-api.md).

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA).

**Performance Goals**: first words within 3 s for 90% of turns on `fast` (SC-002); a turn at most 6 tool rounds and 90 s; read actions under 200 ms on a few thousand jobs; the panel opens in under 100 ms.

**Constraints**:
- Nothing is sent outside the app; `test_no_send.py` scans `actions` and `assistant` (constitution I, FR-017).
- Profile is read-only to Mikasa; drafts only through 002k's checked actions (constitution II, FR-018, R14).
- No raw outside text in the model's context: titles and names are bounded and screened, descriptions only as `job_keywords`, pasted descriptions go straight to the paste use case (constitution III, R4).
- Private 002b, 002e and 002f data reach the model only as refs and labels (FR-022, R5).
- No cost figures or budget; out of credit shows the provider's message (constitution IV).
- No fetching of job links (constitution VII, R12).

**Scale/Scope**: one person, a few conversations a day. 1 migration, 1 prompt, 1 port method, about 60 actions, 11 new endpoints and 1 changed, 1 new event type, 2 new back-end packages, 1 front-end feature folder, 1 eval set.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | No action can send; excluded endpoints are not in the catalogue; `test_no_send.py` scans both new packages. Small changes are only ones the person asked for and can undo in one step; risky ones need a confirm card; AI work that produces drafts goes through 002k's reviewable drafts. Search-rule changes go through the existing proposal and approval. | ✅ | ✅ |
| **II. Truthful profile** | No action writes profile facts (FR-018). Draft and resume text come only from 002k's actions with their fact checks; Mikasa cannot edit draft text (R14). Answers about the person use `get_profile` (confirmed facts only), and any reply in a turn that read the profile goes through 002k's deterministic claim check (numbers, skills, employers, titles, dates) with one repair and a fallback before it is shown (FR-018a, research R9). Eval SC-005 checks no invented values. | ✅ | ✅ |
| **III. Untrusted input is data** | The step with tools receives only structured, bounded, screened data: no descriptions, page text or email text (R4). The description summary comes from 002k's tool-less `extract_job_keywords`. Flagged titles are masked and the signal shown. Only the person's messages can lead to a change (FR-015), checked by `test_FR015_*` and eval SC-004. | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | `converse` is a port method, not an SDK call in the module. Prompt `mikasa_chat/v1` is a versioned file with tier `fast` and an eval set. Tool arguments are validated by Pydantic models, replies by R9's checks; one repair, then a defined refusal. Every round logged. Out of credit pauses the panel with the provider's message. A model without tools degrades to a clear message (R11). No cost shown. | ✅ | ✅ |
| **V. Test-first** | Tests first, named after FR/US/SC/EC ids (matrix); real Postgres; fakes only for the LLM. | ✅ | ✅ |
| **VI. Lean architecture** | No new external boundary: `converse` extends the existing LLM port. Two new packages and the turn running outside LangGraph are justified below. No new dependency. | ✅ | ✅ |
| **VII. Permitted sources only** | Adds no source; links are looked up, never fetched (R12). | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Conversations, cards and changes stay in the local database; per-conversation delete, clear all, and Delete all (truncate) remove them. Private data never leaves the install, not even to the AI provider (R5, SC-010). Eval data is synthetic. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter (new entries below), coverage gate, frontend gates including `npm run build`, Playwright. Reviews: Python/FastAPI, security (prompt injection, privacy), database, React. Eval report before merge (Ravi runs it). | ✅ | ✅ |

**Result**: passes; four items are justified in Complexity Tracking. (Re-checked after `/speckit-analyze` on 2026-11-24: replies about the person now go through 002k's claim check (II); posting-like messages go to the paste flow (III), with the remaining risk recorded in research R4; every story ends with a review (quality gates).)

## Project Structure

### Documentation (this feature)

```text
specs/002m-mikasa-chat/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── actions.md       # Phase 1 (the action catalogue)
│   └── rest-api.md      # Phase 1 (endpoints, stream, test matrix)
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0026_assistant.py
├── .importlinter                         # assistant in layers, pure-domain, contacts-stay-out-of-ai-paths;
│                                         # assistant-boundary (no feature internals; actions only via protocol)
├── src/hiretitan/
│   ├── platform/llm/
│   │   ├── port.py                       # + ConverseRequest, ToolSpec, ChatMessage, TextDelta, ToolCall, TurnEnd, converse()
│   │   ├── openai_adapter.py             # + converse (Responses API streaming, strict function tools)
│   │   ├── fake.py                       # + scripted converse turns by task
│   │   └── models.yaml, models.py        # + capabilities per model
│   ├── platform/runtime/events.py        # + "assistant.changed"
│   ├── actions/                          # composition level, like *_wiring.py (R3)
│   │   ├── spec.py                       # ActionSpec, kinds, PrivateResult, result shapes
│   │   ├── catalogue.py                  # builds the catalogue; excluded list (FR-016)
│   │   ├── jobs.py, search.py, mail.py, companies.py, contacts.py,
│   │   │   interviews.py, drafts.py, profile.py, settings.py   # handlers, undo, targets
│   │   └── refs.py                       # ref parsing, labels from non-private fields
│   ├── assistant/
│   │   ├── domain/
│   │   │   ├── kinds.py                  # card and change state machines
│   │   │   ├── reply_checks.py           # refs, links, length (R9)
│   │   │   ├── fingerprints.py           # stable hashes of target fields (R7)
│   │   │   └── context.py                # last-30 window, data-block wrapping (R4, R10)
│   │   ├── application/
│   │   │   ├── ports.py                  # ActionCatalog, ProfileClaimsChecker (002k checks via wiring), stores
│   │   │   ├── turn.py                   # the loop: converse → validate → read / small / card → stream
│   │   │   ├── cards.py                  # confirm, cancel, expire
│   │   │   ├── changes.py                # undo rules
│   │   │   └── paste.py                  # composer paste → paste use case, change record
│   │   ├── infra/{models.py, repos.py}
│   │   └── api/{conversations.py, turns.py, cards.py, changes.py, status.py}
│   ├── prompts/mikasa_chat/v1/           # system.j2, meta.yaml (tier fast), changelog
│   ├── search/application/paste.py       # link-only mode (R12)
│   ├── search/api/jobs.py, interviews.py # rules moved into application functions where a router held them
│   ├── assistant_wiring.py               # catalogue + stores for the API
│   └── api_main.py                       # include assistant routers
├── evals/mikasa/                         # synthetic world, cases, runner
└── tests/{unit,integration,api,workflow,security,contract,architecture}/(assistant|actions)/

frontend/src/
├── app/Shell.tsx                         # launcher button, Ctrl+/, panel slot
├── api/useEvents.ts                      # + assistant.changed
├── features/assistant/
│   ├── MikasaPanel.tsx                   # aside, header, conversation list, new / clear
│   ├── Conversation.tsx                  # messages, streaming, Stop
│   ├── ReplyText.tsx                     # plain text + ref and link tokens (EC-13)
│   ├── RefCard.tsx                       # job, company, contact, round, draft cards from existing endpoints
│   ├── ConfirmCard.tsx                   # items, editable args, Confirm / Cancel
│   ├── ChangeNotice.tsx                  # summary + Undo
│   ├── Composer.tsx                      # input, 2,000 limit, Paste a job description, privacy note
│   ├── stream.ts                         # fetch + SSE parser for POST
│   └── api.ts
├── features/jobs/PasteJobDialog.tsx      # "I don't have the description" (R12)
└── e2e/mikasa.spec.ts
```

**Structure Decision**: one new feature module `assistant` (api > infra > application > domain; no workflow layer) and one composition-level package `actions` beside the wiring files. Existing modules change at their edges only: the LLM port gains a method, `paste.py` gains link-only mode, a few router rules move into application functions, `events.py` gains one event type.

## Delivery order

1. **Foundation**: `converse` in the port, OpenAI adapter and fake; capabilities; migration; the `actions` spec types and catalogue skeleton with the excluded list.
2. **US1 Ask** (read actions, the turn loop, the panel, streaming, private refs, untrusted handling). Mergeable alone: a read-only Mikasa.
3. **US2 Act** (small changes with Undo, cards, link-only paste, parity tests).
4. **US3 Drafts**, then **US4 Limits** (mostly prompt, catalogue checks and status), then **US5 Conversations**.
5. Eval, docs, final review.

Ravi can stop after step 2 and ship a read-only Mikasa, then continue with US2 on the same spec.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| New feature module `hiretitan.assistant` | Conversations, cards, changes, the turn loop and the prompt are one capability with its own tables and endpoints; import-linter can then keep it out of contacts code. | Putting it in `search` or `drafts` mixes a cross-cutting chat with one feature and weakens the contacts contract. |
| Composition-level package `hiretitan.actions` (imports every module's application and infra, like `*_wiring.py`) | One definition per action for Mikasa now and 007 later (FR-028), calling the same use cases as the routers (FR-006). | Ports per action in `assistant/application`: about 60 single-use interfaces. Calling REST from inside the API: no shared transaction for change records and fingerprints. |
| A second LLM port method `converse` | Tool calls and streamed text are not one validated object, so `generate` cannot carry them. | Encoding a plan in `generate`'s structured output: no streaming and one round per call. |
| Turns run in the API process, not as LangGraph workflows on the worker | A turn is short and interactive; cards and changes are durable rows the person may act on much later, so a graph checkpoint would be a second copy of the same state; tokens through `NOTIFY` would hit its payload limit. | A one-node workflow per turn: still needs token streaming from the worker, and an interrupt per card that may wait for days. |
