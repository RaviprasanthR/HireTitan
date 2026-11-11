# Research: Company contacts, notes and the applied flag (002b)

No `NEEDS CLARIFICATION` remains in the plan. Each item below is a design choice that could reasonably go another way.

## R1. Sheet format: CSV only, no Excel reader

- **Decision**: accept CSV (UTF-8, with or without BOM), the same file type as 002's company import. The person downloads their sheet as CSV. The spec assumption is updated to say so.
- **Rationale**: FR-001 says "the same file types as feature 002". An `.xlsx` reader (openpyxl) adds a dependency, a licence and a zip-bomb surface for no capability CSV lacks. A multi-line cell survives CSV when quoted, which Google Sheets and Excel both do.
- **Alternatives**: openpyxl (more attack surface, new dependency); reading Google Sheets directly (needs OAuth, rejected in the spec).

## R2. Finding the header and the columns

- **Decision**: scan the first 30 rows for the first row where at least two cells match a known column name (lower-cased, trimmed, punctuation removed). Everything above it is ignored; fully empty rows and columns are ignored. Recognised names:

  | Column | Accepted headers |
  |---|---|
  | name (required) | `org name`, `company`, `company name`, `name` |
  | location | `location`, `locations`, `city` |
  | website | `company site`, `website`, `site`, `url` |
  | careers | `careers page`, `careers`, `careers url`, `careers_url` |
  | contacts | `hr / linkedin contacts`, `hr linkedin contacts`, `linkedin contacts`, `contacts` |
  | notes | `notes`, `note` |
  | openings (ignored, FR-008) | `frontend openings`, `front end openings`, `backend openings`, `back end openings`, `qa openings` |

  The result lists the columns used and ignored (FR-002, FR-008). No `name` column found: the file is refused with `422` and the headers seen. Columns of the 002 export that are not in the table (`ats_vendor`, `board_id`, `hidden`) are reported as ignored.
- **Rationale**: the maintainer's sheet has empty rows and columns before the data. A fixed alias table is testable and predictable; fuzzy header matching would sometimes pick the wrong column silently.
- **Alternatives**: let the person map columns in the UI (more UI, not needed for the one known layout; can be added later); fuzzy matching (silent mistakes).

## R3. Parsing the contacts cell

- **Decision**: a pure parser turns one cell into a list of contacts plus leftover text. Rules, applied line by line:
  1. A line holding an `http(s)://` URL (or `linkedin.com/...` without a scheme, which gets `https://`) belongs to the person above it. A URL line with no person above it is kept as leftover text.
  2. Any other non-empty line starts a new person: `Name`, optionally followed by a separator (` - `, ` – `, ` — `, `,` or `(...)`) and a role, with an optional tag `[High]`, `[Med]`, `[Medium]` or `[Low]` (case-insensitive) anywhere on the line. The tag is removed from the name and role.
  3. `email: x` and `phone: x` (or `tel: x`) lines attach to the person above. They exist so an export with contacts round-trips (R7).
  4. A line after a person that is neither a URL nor a labelled field is a **new person** only if it has at most 6 words, starts with a capital letter and has no sentence punctuation (`.` `:` `;` `!`). Otherwise it is a **note line** on the person above.
  5. A cell with no person line at all (for example "no LinkedIn URL found - name via RocketReach") becomes a company note line (FR-005, edge case).
  6. More than 20 people: the first 20 are kept and the row is reported as *shortened*.
- **Rationale**: the spec gives the shape (name, role, tag, link on the next line). Free text must not be dropped (FR-005), so every line ends up as a field, a contact note or a company note. The heuristic in rule 4 is imperfect; its tests are written from the synthetic fixture before the rule is finalised, and a misplaced line is still kept as text, never lost.
- **Alternatives**: AI parsing (rejected: contacts must never reach an AI, FR-022; also non-deterministic); a strict format only (drops real-world cells).

## R4. Matching rows to companies and to contacts

- **Company**: website key first (host lower-cased, `www.` removed, scheme, path and trailing slash ignored; hosts must be equal, so `careers.acme.com` and `acme.com` do not match), then name key (lower-case, NFKD, punctuation and spaces removed, trailing suffixes `inc`, `ltd`, `pvt`, `llc`, `technologies` removed). One match: use it. None: add the company as the person's own. More than one: skip the row with "matches two companies: A, B" (spec AS4). A website match and a name match pointing at different companies count as two matches.
- **Contact**: unique per `(company, name_key)`. A contact in the file with the same `name_key` updates that contact's role, confidence, link, email, phone and note. If no name matches but the `link_key` (the LinkedIn path, lower-case, query and trailing slash removed) matches an existing contact of the same company, that contact is updated and renamed. Otherwise a new contact is added.
- **Rationale**: FR-006 defines identity as link first, or name when there is no link; AS5 also wants a changed link to update rather than duplicate. A database-unique `(company, name_key)` makes re-imports idempotent by construction. The trade-off: two people with the same name at one company cannot both be stored (very rare; the person can add a role to the name).
- **Confirmed by Ravi (2026-11-08)** and reflected in spec FR-006. Spec FR-007a records the note rule of R5.
- **Alternatives**: link-only identity (fails for contacts without links, and a changed link would duplicate); fuzzy name matching (surprising merges).

## R5. Imported notes versus typed notes

- **Decision**: a company note records its `source` (`import` or `typed`). A re-import replaces an imported note when the text differs (counted as "note changed"). If the person edited the note by hand (`source = typed`), the import leaves it alone and lists the row as "kept your edited note". An import never deletes a note: an empty notes cell changes nothing.
- **Rationale**: without this, one re-import silently overwrites what the person typed. The spec requires no duplicates but does not say edits may be destroyed. This is a safe reading of FR-006/FR-007; **flagged for Ravi to confirm when approving the plan.**
- **Alternatives**: always overwrite (data loss); always append (grows on every import, breaks idempotence).

## R6. Open-role counts: derived, with a pure title classifier

> **Superseded 2026-11-11.** The open-role counts and the title classifier were removed at the maintainer's request (open roles go stale). The page shows the applied flag instead; see the change note in `spec.md`. Kept for the record.

- **Decision**: no new column and no stored count. The Companies list runs one query for `(company_id, title)` of jobs with `state = 'explore'` and `listed = true`, and the pure function `areas_of(title)` returns a set of `frontend`, `backend`, `qa`. The application layer counts per company. A company with `last_checked_at IS NULL` returns `openings = null` ("not searched yet", FR-019). The click-through uses `GET /jobs?list=explore&company_id=…&area=…`; `area` is allowed only together with `company_id` (at most tens of rows), is classified in Python, and the whole set is returned without a cursor.
- **Classifier**: lower-case tokens. `frontend`, `front end`, `front-end`, `react`, `angular`, `vue`, `ui` → front end. `backend`, `back end`, `back-end`, `api`, `python`, `java`, `golang`, `node`, `server` → back end; `Go` counts only when written with a capital in the original title. `qa`, `sdet`, `test`, `tester`, `testing`, `quality` → QA. `full stack` or `fullstack` → front end and back end. A title with `designer`, `recruiter`, `sales`, `marketing` or `writer` is excluded unless it also has an engineering word (`engineer`, `developer`, `sdet`).
- **Rationale**: derived counts cannot drift from the Explore list (SC-005). A column on `jobs` would need a backfill migration that imports domain code, and every rule change would need another backfill. Jobs per install are in the low thousands, so one narrow query is cheap.
- **Alternatives**: store `areas text[]` on `jobs` at write time (fast filters, but backfill and drift); AI classification (cost, non-determinism, and the spec says no AI).
- **Accuracy**: the 95% target (SC-005) is measured on a labelled set of 100 synthetic titles in `fixtures/sheets/job_titles_labelled.csv`. The word lists above are the starting point and are expected to change while that test is made to pass.

## R7. Export with contacts

- **Decision**: `GET /companies/export` keeps its seven columns. With `include_contacts=true` it appends `contacts` and `notes` columns. The `contacts` cell is produced by the same module as the parser (`contacts_cell.render`): per person `Name - Role [High]`, then the link line, then `email: …`, `phone: …`, then note lines. Cells starting with `=`, `+`, `-` or `@` get the apostrophe escape 002 uses. Importing that file through the sheet importer restores the contacts (FR-024, US4 AS3), because the sheet importer already recognises `name`, `city`, `website`, `careers_url`, `contacts` and `notes` as headers.
- **Rationale**: the importer and exporter share one grammar, so a property test (`parse(render(x)) == x`) guards the round trip.
- **Alternatives**: a JSON export (a second format to maintain); a separate contacts file (two files to keep in step).

## R8. Delete, hide and seed updates

- **Decision**: no new code for delete-all: `setup_wiring` already truncates every `app` table, so the new tables go with it; a test asserts it (SC-007). Deleting one of the person's own companies cascades (`ON DELETE CASCADE` on both tables); the delete confirmation gets its contact count from `GET /companies/{id}/contacts`. Built-in companies are only tombstoned by 002, so their contacts survive; the seed loader updates built-in rows in place and keeps their ids, so contacts stay attached after a list update (FR-025, tested with 002's `seed_v1.yaml` then `seed_v2.yaml`). Hidden companies keep their contacts.
- **Rationale**: foreign keys and the existing wipe keep the privacy rules in the database, not in application code that could be forgotten.

## R9. Keeping contacts away from the AI

- **Decision**: three layers. (1) An import-linter contract: `hiretitan.search.workflow`, `hiretitan.prompts` and `hiretitan.platform.llm` may not import the contacts, sheet-import, or notes modules. (2) A security test runs a search with the scripted fake LLM while contacts and notes exist, and asserts none of their strings appear in any recorded request. (3) A test adds a `contacts` field to a seed file and expects the loader's existing "unknown field" rejection.
- **Rationale**: the rule is easy to break by accident later (someone adds "company notes" to a prompt). A lint failure catches it before any test run.

## R10. The page: where the data shows

- **Decision**: the Companies list gains per row: contact count, a note marker, the applied flag (changed 2026-11-11; it replaced the three opening counts), and client-side sort and filter ("has contacts", "has an application"). The list endpoint already returns all companies (002), so filtering on the client adds no endpoint. Opening a company shows a panel with its contacts (add, edit, delete with confirmation) and its note. Job detail shows the same panel for the job's `company_id`. All text renders as text; emails and phones are plain text; the LinkedIn link is an `<a target="_blank" rel="noopener noreferrer">`.
- **Rationale**: two clicks or fewer from the page or from a job (SC-004). Server-side sorting is only needed if the list grows past a few hundred rows; it can be added later behind the same response shape.

## R11. Validation of typed and imported contacts

- **Decision**: name 1–120 chars; role ≤ 120; link must parse as `http`/`https` with a host, ≤ 500 chars (a bare `linkedin.com/in/x` is accepted and stored with `https://`); email must look like `local@domain.tld`, ≤ 254; phone 5–30 characters of digits, spaces and `+ - ( )`; contact note ≤ 2,000; company note ≤ 5,000. Typed input that fails is refused with field errors (spec US2 AS6). Imported input is best-effort: an import adds `https://` where it can and drops only the bad field, reporting it, rather than skipping the person.
- **Rationale**: one bad link in a sheet must not lose a contact, but a person typing should be told straight away.
