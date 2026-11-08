# Implementation Plan: Company contacts, notes and open roles

**Branch**: `002b-company-contacts` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002b-company-contacts/spec.md` (1 clarification, 2026-11-08)

## Summary

On the Companies page, each company gains three things that belong to the person:
- **Contacts** (name, role, LinkedIn link, email, phone, confidence, note) that they type or import.
- **One private note.**
- **Live counts** of open front end, back end and QA jobs, derived from the jobs 002 already stores.

Approach, in one paragraph: a sheet importer reads the maintainer-style spreadsheet (CSV download) with a tolerant header finder and a contacts-cell parser. It shows a preview (same preview-then-confirm pattern as 002's company import), then attaches contacts and notes to companies matched by website, then name. Unknown companies are added as the person's own. Re-imports are idempotent through a unique key on `(company, name)`. Open-role counts are not stored: a pure title classifier runs over the company's open Explore jobs at read time. Contacts never reach any AI call, enforced by an import-linter contract and a recorded-calls test. Delete-all already truncates every `app` table; a test proves the new tables are covered.

Design decisions are in [research.md](research.md).

> **Dependency note.** 002 (PR #4, branch `002-job-search`) is not merged into `master`, and this branch was cut from `master`. This plan targets 002's code and migrations (up to `0014_job_role_short`). Before implementation starts, rebase this branch onto `master` after PR #4 merges. The new migration is `0015_company_contacts` and assumes `0014` is its parent.

## Technical Context

**Language/Version**: Python 3.12+ (backend, uv); TypeScript 5 strict (frontend, Node 22). No change to the runtime image.

**Primary Dependencies**: as in 001 and 002 (FastAPI, Pydantic 2, SQLAlchemy 2 async + Alembic, React 19, TanStack Query, Tailwind 4 + shadcn/ui). **None added**: the standard-library `csv` module reads the sheet, and matching is exact on normalized keys.

**Storage**: PostgreSQL 16, `app` schema. New tables `company_contacts` and `company_notes` ([data-model.md](data-model.md)). No change to `companies` or `jobs`. Migration `0015_company_contacts`.

**Testing**:
- pytest + Testcontainers Postgres (repos, uniqueness, cascade, delete-all).
- A synthetic sheet fixture with the maintainer sheet's *shape* (empty rows and columns above the header, multi-line contacts cell, confidence tags, links on their own line, free-text contact cells, a row with no name, a row that matches two companies). No real person's data (FR-026).
- A labelled set of 100 synthetic job titles for the area classifier (SC-005).
- The scripted fake LLM, recording every call, for SC-006.
- Vitest + Testing Library; one step added to the 002 Playwright journey.

**Target Platform**: unchanged (`docker compose up`, browser on `127.0.0.1`).

**Project Type**: web application (api + worker + SPA), extending 001 and 002. No worker or workflow change: everything here is request/response.

**Performance Goals**: importing the 62-row sheet in under 10 s (SC-001; expected well under 1 s); the Companies list with counts in three queries (companies, contact and note counts, open jobs), no per-company query.

**Constraints**:
- No outbound action; no link is fetched or opened by the server (FR-015).
- Contacts and notes never reach the LLM port (FR-022).
- Nothing specific to a person ships in the repo (FR-021, FR-026); the seed loader already rejects unknown fields.
- The imported file is untrusted: control characters stripped, length caps, links limited to `http`/`https`, spreadsheet-formula cells escaped on export.
- Import file: CSV, at most 1 MB and 2,000 rows (the limits of 002's company import).

**Scale/Scope**: dozens to a few hundred companies, up to a few thousand contacts, hundreds to low thousands of jobs. 1 import dialog, 1 company panel, 4 new columns on the Companies list, 1 panel in job detail. About 8 new endpoints. 0 workflows, 0 prompts.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Pre | Post |
|---|---|---|---|
| **I. Human in the loop, no outbound actions** | Contacts are reference data. Emails and phones are shown as plain text, not `mailto:`/`tel:` links, and nothing in the backend can send to them. The no-send architecture test (001, extended in 002) covers the new files. The import shows a preview and changes nothing until the person confirms. Nothing here is AI output. | ✅ | ✅ |
| **II. Truthful profile** | Not touched. Contacts and notes are not candidate facts and are never given to AI. | ✅ | ✅ |
| **III. Untrusted input is data** | The sheet is untrusted: parsed by code only, never by AI. Text is sanitized with 001's sanitizer (Unicode normalization, control characters stripped, length caps) before storage; links must be `http`/`https`; the UI renders everything as text; links open with `rel="noopener noreferrer"`. Injection screening is not needed because no AI step ever reads this text (guarded, see IV). | ✅ | ✅ |
| **IV. Validated, versioned, provider-agnostic AI** | No AI call, prompt or model is added. The only AI-related work is a guard: an import-linter contract forbids `search.workflow`, `prompts` and `platform.llm` from importing the contacts modules, and a test runs a search with contacts present and asserts no recorded call contains any contact or note text. | ✅ | ✅ |
| **V. Test-first** | Tests named after FR/US/SC ids ([test matrix](contracts/rest-api.md#test-matrix-names-reference-requirement-and-scenario-ids)). Real Postgres for repos and APIs. No new fakes (no external boundary is added). | ✅ | ✅ |
| **VI. Lean architecture** | No new module, port or abstraction. Two tables. Contacts live inside `search` next to `companies`. Pure code (sheet rules, contacts-cell parser, area classifier, keys) is in `search/domain`. Open-role counts are derived, so nothing needs syncing. | ✅ | ✅ |
| **VII. Permitted sources only** | Adds no source. The sheet is a file the person gives us. LinkedIn links are stored text and never requested by HireTitan (FR-015); a test fails if any contacts module imports an HTTP client. | ✅ | ✅ |
| **VIII. Self-hosted privacy and portability** | Third-party personal data is stored only in the person's database; never in the seed (the loader rejects unknown fields; a test adds a `contacts` field to a seed file and expects `SeedError`). Delete-all and per-company delete remove it (truncate and cascade). Export leaves it out unless chosen. Fixtures are synthetic. | ✅ | ✅ |
| **Quality gates** | ruff, mypy `--strict`, import-linter, coverage, frontend gates, licence checks (no new dependency). Reviews per story: Python/FastAPI, security (untrusted file, links), database, React. No prompt change, so no eval report. | ✅ | ✅ |

**Result**: passes with no new deviation. D1 (provider adapters) and D3 (live cost instead of upfront estimate) are unaffected.

## Project Structure

### Documentation (this feature)

```text
specs/002b-company-contacts/
├── spec.md
├── plan.md              # this file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── rest-api.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── alembic/versions/0015_company_contacts.py
├── src/hiretitan/search/
│   ├── domain/
│   │   ├── contacts.py          # contact fields, checks, name_key and link_key (pure)
│   │   ├── contacts_cell.py     # contacts-cell parser and renderer (pure; round-trips)
│   │   ├── sheet.py             # header finder, column aliases, row reader (pure)
│   │   ├── company_match.py     # website and name keys, match result (pure)
│   │   └── job_area.py          # title -> {frontend, backend, qa} (pure)
│   ├── application/
│   │   ├── contacts.py          # contact CRUD, note get/set
│   │   ├── sheet_import.py      # preview_sheet / apply_sheet (reuses the add-company path)
│   │   ├── openings.py          # open-role counts per company; a company's jobs by area
│   │   └── companies_csv.py     # (002 file) export gains include_contacts
│   ├── infra/
│   │   ├── models.py            # (002 file) + ContactRow, CompanyNoteRow
│   │   └── repos.py             # (002 file) + ContactsRepo, NotesRepo, counts query
│   └── api/
│       ├── companies.py         # (002 file) + counts on the list, sheet-import routes, export flag
│       ├── contacts.py          # /companies/{id}/contacts, /companies/{id}/note
│       └── jobs.py              # (002 file) + area filter with company_id
└── tests/
    ├── unit/search/             # sheet, contacts_cell, company_match, job_area, contacts
    ├── integration/search/      # repos, uniqueness, cascade, delete-all, seed guard
    ├── api/search/              # sheet import, contacts, notes, openings, export
    ├── security/test_contacts_privacy.py   # no AI call, no HTTP client, no send path
    └── fixtures/sheets/         # synthetic sheet CSVs, job_titles_labelled.csv

frontend/src/features/
├── companies/                   # (002) + count columns, filters, company panel, sheet import dialog
└── jobs/                        # (002) + company contacts panel on job detail
frontend/e2e/job-search.spec.ts  # + a contacts step
```

**Structure Decision**: extend the existing `search` module. Contacts have no meaning without a company, share its lifecycle (delete, hide, seed update) and its page, and a second module would need a cross-module wiring file for no gain.

## Complexity Tracking

No constitution violations to justify. Two new tables and five small pure files; no new port, service, queue or dependency.

| Addition | Why it is needed | Simpler option rejected |
|---|---|---|
| `add_company_from_import` in `search/application/discovery.py` (careers link optional) | 002's manual add refuses a company with no careers link, but a sheet row can have a name and nothing else (US1 AS2) | Skipping such rows would drop real companies from the person's sheet |
