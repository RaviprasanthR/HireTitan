# Data model: Mikasa, the chat assistant

**Feature**: `002m-mikasa-chat` · Migration `0026_assistant` (parent `0025_alert_read_by`) · Schema `app`

Four new tables. No existing table changes except the paste rules (R12, a use-case change, no column). Delete all already truncates every table in `app`, so these are covered (FR-027, SC-009). Private values from 002b, 002e and 002f may appear in `assistant_changes.before/after` and in the person's own messages; they stay in the local database and are never read into a model request (R5).

## assistant_conversations

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `title` | text null | first 80 characters of the person's first message, made by HireTitan (not the model) |
| `turn_running` | boolean not null default false | set and cleared under a row lock; one turn at a time (EC-01) |
| `turn_started_at` | timestamptz null | set with `turn_running`; a turn running for more than 120 seconds is treated as ended (a crash or a lost connection), so the conversation never stays stuck |
| `created_at` | timestamptz not null | |
| `last_used_at` | timestamptz not null | index `desc` for the list |

## assistant_messages

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `conversation_id` | uuid FK → conversations, `ON DELETE CASCADE` | |
| `seq` | integer not null | unique per conversation, gap-free |
| `author` | text not null | `person` or `mikasa` (check constraint) |
| `text` | text not null | person: at most 2,000 characters; mikasa: at most 4,000, ref tokens kept as written (R9) |
| `status` | text not null | `complete`, `stopped`, `failed` (check) |
| `refs` | jsonb not null default `[]` | refs the actions returned in this turn (`kind:id`), used to check later replies |
| `tool_trace` | jsonb not null default `[]` | this turn's tool calls and model-facing results (structured, bounded, no private values), kept for debugging and the last-30 window (R10) |
| `signals` | jsonb not null default `[]` | injection signals found in the person's text or in screened titles (R4) |
| `error` | jsonb null | `{reason, provider_message}` when `failed` |
| `created_at` | timestamptz not null | |

Index `(conversation_id, seq)`.

## assistant_cards

A confirm card for one or more risky changes (R7).

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `conversation_id` | uuid FK, `ON DELETE CASCADE` | |
| `message_id` | uuid FK → messages, `ON DELETE CASCADE` | the reply that proposed it |
| `state` | text not null | `proposed`, `applying`, `applied`, `cancelled`, `expired`, `failed` (check) |
| `items` | jsonb not null | list of `{action, args}`, 1 to 25 items, `args` validated by the action's model when written and again on confirm |
| `fingerprints` | jsonb not null | `{"job:<id>": "<sha256>", …}` from each action's `targets` |
| `summary` | text not null | what the card says will happen, made by HireTitan from the items (not the model) |
| `result` | jsonb null | per item: `ok` and the change id, or the error |
| `expires_at` | timestamptz not null | created + 30 minutes |
| `decided_at` | timestamptz null | |
| `created_at` | timestamptz not null | |

**State transitions**

```text
proposed --confirm (fingerprints match)--> applying --commit--> applied
proposed --confirm (fingerprints differ)--> expired
proposed --cancel--> cancelled
proposed --now > expires_at (checked on read and on confirm)--> expired
applying --error, rolled back--> failed
```

Only `proposed → applying` is done with `UPDATE … WHERE state = 'proposed' RETURNING`, so a second confirm finds nothing (EC-03). On page load, a `proposed` card past `expires_at`, or from an earlier session (US5 scenario 4), is shown as expired.

## assistant_changes

A change Mikasa applied, at once (small) or from a card (R6).

| Column | Type | Rules |
|---|---|---|
| `id` | uuid PK | |
| `conversation_id` | uuid FK, `ON DELETE CASCADE` | |
| `message_id` | uuid FK null, `ON DELETE CASCADE` | for small changes |
| `card_id` | uuid FK null, `ON DELETE CASCADE` | for changes from a card |
| `action` | text not null | catalogue name |
| `summary` | text null | what it did, in words, at most 2,000 characters (migration `0027`); the history shows it after a reload |
| `target_kind` | text not null | `job`, `company`, `contact`, `round`, `question`, `interview`, `sender`, … |
| `target_id` | uuid not null | |
| `before` | jsonb not null | touched fields before (empty for an add) |
| `after` | jsonb not null | touched fields after |
| `created_rows` | jsonb not null default `[]` | rows the change created (`kind:id`), removed by the undo of an add |
| `undoable_until` | timestamptz null | created + 24 h when the action has an undo, else null |
| `undone_at` | timestamptz null | |
| `created_at` | timestamptz not null | |

Check: exactly one of `message_id`, `card_id` is set. Index `(target_kind, target_id, created_at desc)` to find "the latest change to this item". Undo is allowed when `undone_at is null`, `now < undoable_until`, it is the latest change to its target, and the target's current fields equal `after` (EC-16).

## Not stored

- No copy of jobs, companies, contacts or rounds: refs point at the existing rows; a deleted target shows as "no longer exists".
- No model summaries of conversations (R10).
- No per-person model choice (R11).

## Existing data the feature changes

- **Jobs (paste rules)**: a pasted job may have an empty description when link, title and company are given (R12). The column already allows it (jobs from alerts have none); only `paste.py`'s checks change, with the same option in the paste dialog.
- **Event types**: `assistant.changed` is added to `EVENT_TYPES` (R8).
