# Data model: Setup and search polish

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Research**: [research.md](research.md)

One migration, `0020_first_rules` (parent `0019_resume_picker`). Everything else is a change to JSON content, in-memory types or reviewed seed files.

## 1. `app.search_rule_sets` (changed)

| Column | Type | Change | Rule |
|---|---|---|---|
| `approved_by` | `text`, nullable | **new** | `CHECK (approved_by IN ('person', 'auto'))`; `NULL` while the row is a proposal or discarded |
| `rules` | `jsonb` | content gains `areas` | see §2 |

- Upgrade: add the column and the check; backfill `approved_by = 'person'` on every row whose `approved_at` is not null (every approval before this feature was the person's).
- Downgrade: drop the check and the column (the `areas` key in `rules` is ignored by older code, which reads known keys only; verified by a serialization test).
- Existing invariants kept: unique `version`; at most one row with `status = 'approved'` (`uq_search_rule_sets_one_approved`).
- New invariant (application, R2): an automatic approval is written only when no row has `approved_at` set, under `pg_advisory_xact_lock`.
- Delete all already truncates this table (tested in 002); after it, the next Finish setup approves again.

**Read model additions**: `RuleSetOut.approved_by` (`'person' | 'auto' | null`). The page shows FR-020's line when the current approved set has `approved_by = 'auto'`.

## 2. `SearchRules` (domain, changed)

| Field | Type | Change | Validation |
|---|---|---|---|
| `areas` | `tuple[str, ...]` | **new**, default `()` | each in `AREAS = {back_end, front_end, full_stack, mobile, data, qa, devops, other}`; at most 4; no duplicates; field error `areas` |
| `title_avoid` | `tuple[RuleItem, ...]` | proposer now fills it from the area table (origin `area:<name>`) | unchanged limits |

- Serialization (`rules_serialization.py`): `areas` written as a list; a stored set with no `areas` reads as `()`.
- Origins stay stored (history and tests use them) but are no longer returned for display decisions; the API keeps returning them for compatibility.

## 3. Seed files (new, reviewed, no personal data)

- `backend/seed/work_areas.yaml`: per area, `signals` (words in roles, titles and skills used to guess it) and `avoid_in_titles` (words added to `title_avoid` for a person **not** in that area), plus `compatible` (areas that do not exclude each other, for example `full_stack` with `back_end` and `front_end`). Loaded and checked at start like `title_synonyms.yaml` (unknown area names or empty lists fail fast).
- `backend/seed/tech_names.yaml`: list of `{name, aliases, kind: language | framework}`. Loaded and checked the same way (duplicate aliases fail fast).

## 4. In-memory job during a search (changed)

`NewJob` (workflow, not stored as such) gains `description_status: 'read' | 'unreadable' | 'none'`.

- `none`: the job never needed a description read (rules left it out, or rules-only mode).
- `read`: the description reader returned text; `description`, `skills_found`, `years_found` are refreshed before the AI check and stored with the job (existing columns, no schema change).
- `unreadable`: a read was tried and failed; the job keeps an empty description.

The status is passed to the AI card and is not stored; the decision reason says when a job was kept without a description (FR-034).

## 5. AI cards (changed)

`ProfileCard` (`search/domain/cards.py`):

| Field | Source | Limit |
|---|---|---|
| `target_roles` | preferences | as today |
| `areas` | approved rules `areas` | ≤ 4 |
| `main_skills` | profile skills ∪ preference key skills, languages and frameworks first (`tech_names.yaml`) | ≤ 30 (`KEY_SKILLS_MAX`) |
| `years_experience` | preferences | as today |
| `seniority` | preferences | as today |
| `recent_titles` | confirmed profile experience, newest first | ≤ 3, each ≤ 80 characters |
| `preferred_locations`, `work_modes` | preferences | as today |

`JobCardInput` gains `description_status`.

Both cards are length-bounded and built from cleaned text; job text stays inside the untrusted data block (constitution III).

## 6. Not changed

- `app.jobs` (the `description`, `skills_found`, `years_found` columns already exist).
- `app.preferences` (no new field; FR-022).
- `app.settings` (`setup_completed_at` already exists).
- `search_runs` (the panel uses the existing counters).
