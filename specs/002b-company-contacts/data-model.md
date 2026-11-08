# Data Model: Company contacts, notes and open roles (002b)

Both tables live in the `app` schema and follow 001's conventions: UUIDv7 primary keys, `created_at` and `updated_at`, named constraints (`ck_…`, `uq_…`, `fk_…`, `ix_…`), SQLAlchemy models in `search/infra/models.py`. They are owned by the existing **`search`** module. Migration: `0015_company_contacts` (parent `0014_job_role_short` from feature 002). No change to `companies` or `jobs`.

## Entities

### Contact (`company_contacts`)

| Field | Type | Rules |
|---|---|---|
| id | uuid | PK |
| company_id | uuid | FK → `companies.id` **ON DELETE CASCADE**, not null |
| name | text | 1–120 chars, as the person wrote it |
| name_key | text | derived: lower-case, NFKD, punctuation and spaces removed; 1–120 chars. Written by the application, checked non-empty by a constraint |
| role | text, nullable | ≤ 120 |
| linkedin_url | text, nullable | `http`/`https` URL with a host, ≤ 500 |
| link_key | text, nullable | derived from `linkedin_url`: host (no `www.`) + path, lower-case, no query, fragment or trailing slash. Null when there is no link |
| email | text, nullable | plausible `local@domain.tld`, ≤ 254 |
| phone | text, nullable | 5–30 characters of digits, spaces, `+ - ( )` |
| confidence | text, nullable | `high` \| `medium` \| `low` |
| note | text, nullable | ≤ 2,000 |
| source | text | `import` \| `typed` (where the row was created; an edit by hand does not change it) |

Constraints and indexes:
- `uq_company_contacts_company_name (company_id, name_key)`: the identity rule of research R4, and what makes re-imports idempotent.
- `ix_company_contacts_company_link (company_id, link_key) WHERE link_key IS NOT NULL`: finds a renamed person by link. Not unique: two names may share a link on a company page by mistake, and the first match wins.
- `ck_company_contacts_confidence`, `ck_company_contacts_name_key_not_empty`, length checks on the text columns.

### Company note (`company_notes`)

| Field | Type | Rules |
|---|---|---|
| company_id | uuid | PK and FK → `companies.id` **ON DELETE CASCADE**; one note per company |
| body | text | 1–5,000 chars. Saving an empty note deletes the row |
| source | text | `import` \| `typed`. An import sets `import`; any edit by hand sets `typed` (research R5) |

### Open-role count (derived, not stored)

Per company, from `jobs` where `company_id` matches, `state = 'explore'` and `listed = true`: the number of jobs whose title falls in each area (`areas_of(title)`, research R6). `null` for the whole value when `companies.last_checked_at IS NULL`. A job can count in more than one area (full stack: front end and back end); a job in no area counts nowhere.

### Import result (not stored)

Returned by the preview and by confirm; held in memory for 30 minutes by 002's `ImportPreviews` holder (generalised to hold either kind of plan), never written to the database.

```text
SheetPreview = {
  token, columns: {used: [...], ignored: [...]},
  companies: {matched, to_add},
  contacts:  {to_add, to_update},
  notes:     {to_set, to_change, kept_yours},
  rows: [{line, company, action: matched|add|skip, contacts_add, contacts_update, notes: set|changed|kept|none, shortened?: bool}],
  skipped: [{line, reason}], shortened: [{line, reason}]
}
SheetResult  = {matched, companies_added, contacts_added, contacts_updated, notes_set, notes_changed, notes_kept, skipped: [...], shortened: [...]}
```

## Pure domain types (`search/domain/`)

- `ParsedContact {name, role, confidence, linkedin_url, email, phone, note}` and `ParsedCell {contacts: tuple[ParsedContact], leftover: tuple[str]}` returned by `contacts_cell.parse`, rendered back by `contacts_cell.render`.
- `SheetRow {line, name, city, website, careers_url, contacts_cell, notes_cell}` and `SheetLayout {header_line, used, ignored}` from `sheet.read`.
- `MatchResult = Matched(company_id) | NoMatch | Ambiguous(names)` from `company_match.match`.
- `Area = Literal["frontend", "backend", "qa"]` and `areas_of(title) -> frozenset[Area]`.

## State and lifecycle

```text
(typed or imported) ──▶ contact ──edit──▶ contact (updated_at)
                                 ──delete (confirmed)──▶ gone
company deleted (own companies only) ──▶ its contacts and note gone (cascade)
Delete all my data ──▶ every app table truncated (incl. both tables)
shipped list updated ──▶ built-in company rows updated in place, same id ──▶ contacts stay attached
```

## Changes to feature 001 and 002 tables and types

| Where | Change |
|---|---|
| `setup_wiring.py` (wipe store) | none: it truncates every `app` table. A test proves the new tables are emptied |
| `search/application/companies.py` | `CompanyView` gains `contact_count`, `has_note`, `openings` (null or `{frontend, backend, qa}`) |
| `search/application/companies_csv.py` | `export_csv(rows, contacts=None)`: with contacts adds the `contacts` and `notes` columns |
| `ImportPreviews` (api/companies.py) | holds any plan object, not only a list of `ImportRow` |
| `search/application/discovery.py` | new `add_company_from_import`: like 002's `add_company` but the careers link is optional (a sheet row can have only a name) |
| `GET /jobs` | gains `company_id` and `area` filters (the contract in 002 already lists `company_id` among the filters) |

## Validation summary (from the requirements)

- A contact needs a name (FR-009); a typed link, email or phone that fails its check is refused with field errors (US2 AS6, FR-012).
- A second contact with the same `name_key` on a company is refused with `409` when typed; an import updates the existing one (FR-006).
- A company has at most one note, 5,000 chars (edge case); a contacts cell yields at most 20 people (edge case).
- The sheet import: CSV only, at most 1 MB and 2,000 rows (FR-001, edge case); control characters stripped from every cell.
- An import never deletes a contact or a note.
