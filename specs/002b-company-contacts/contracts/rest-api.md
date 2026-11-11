# REST API contract: Company contacts, notes and the applied flag (002b)

Extends 001's and 002's contracts. Base path `/api/v1`. Errors are RFC 7807 problem documents as in 001. Field errors come as `422` with `errors: [{field, message}]`. Everything is for the one local user; there is no authentication beyond the localhost binding.

## Companies (changes)

| Endpoint | Request → Response | Notes |
|---|---|---|
| `GET /companies?filter=all\|check_manually\|hidden` | → `200 {items: Company[]}` | `Company` gains `contact_count: int`, `has_note: bool`, `note_preview: string \| null` (the note on one line, at most 120 characters) and `has_application: bool` (true when a job at the company is in the applied state; it replaces the open-role counts, see the change note in `spec.md`) |
| `GET /companies/export?include_contacts=false\|true` | → `200 text/csv` | Default leaves contacts and notes out (FR-024). `true` adds columns `contacts` and `notes` in the format the sheet import accepts (research R7) |
| `DELETE /companies/{id}` | → `204` | Own companies only (002). Contacts and the note go with it. The UI shows the count from `GET /companies/{id}/contacts` before asking |

## Sheet import (US1)

| Endpoint | Request → Response | Notes |
|---|---|---|
| `POST /companies/sheet-import` | multipart CSV → `200 SheetPreview` | ≤ 1 MB, 2,000 rows. Nothing is saved. A preview lasts 30 minutes. `415`/`413`/`422` for a bad file with the reason (not CSV, too big, no company-name column: the headers seen are in the problem detail) |
| `POST /companies/sheet-import/{token}/confirm` | → `200 SheetResult` | Applies the previewed plan in one transaction. `404 preview_expired` if the token is unknown or older than 30 minutes (upload again) |

`SheetPreview` and `SheetResult` are defined in [data-model.md](../data-model.md#import-result-not-stored). Re-running the same file gives a preview with zero to add and zero to update (SC-002). The confirmed result counts new companies, contacts added, contacts updated, notes set, changed and kept (FR-007). A skipped row saves nothing (US1 AS4, SC-003).

## Contacts and notes (US2)

| Endpoint | Request → Response | Notes |
|---|---|---|
| `GET /companies/{id}/contacts` | → `200 {items: Contact[], note: Note \| null}` | One call gives the panel everything it needs. `404` for an unknown company |
| `POST /companies/{id}/contacts` | `{name, role?, linkedin_url?, email?, phone?, confidence?, note?}` → `201 Contact` | `422` field errors (FR-012); `409 contact_exists` when the name key already exists on the company |
| `PATCH /companies/{id}/contacts/{contact_id}` | partial of the same fields → `200 Contact` | Same checks. Renaming to another contact's name key: `409` |
| `DELETE /companies/{id}/contacts/{contact_id}` | → `204` | The UI asks first (FR-011) |
| `PUT /companies/{id}/note` | `{body}` → `200 Note` | Sets `source = typed`. An empty or whitespace body deletes the note (`200 {body: null}`) |

`Contact = {id, company_id, name, role, linkedin_url, email, phone, confidence, note, source, updated_at}`. `Note = {body, source, updated_at}`.

## Jobs (changes)

| Endpoint | Request → Response | Notes |
|---|---|---|
| `GET /jobs/{id}` | → `200 JobDetail` | Already returns `company_id`; the job screen then calls `GET /companies/{company_id}/contacts` (FR-014). `company_id` null (a pasted job with no company): no panel |

## Not in this contract (by design)

- No endpoint opens, fetches or resolves a contact's link, and none sends anything to an email, phone or LinkedIn (FR-015). The architecture test that bans send adapters is extended to the new files.
- No endpoint returns contacts to any AI step, and none is called by the workflows (FR-022).

## Test matrix (names reference requirement and scenario IDs)

| Test file | Test names | Covers |
|---|---|---|
| `unit/search/test_sheet.py` | `test_FR002_header_found_below_empty_rows_and_columns`, `test_FR002_unknown_columns_are_reported_ignored`, `test_FR008_openings_columns_are_ignored`, `test_FR001_no_name_column_refuses_the_file` | sheet reading |
| `unit/search/test_contacts_cell.py` | `test_US1_AS3_one_contact_per_person_with_role_tag_and_link`, `test_FR005_unplaceable_text_is_kept_as_a_note`, `test_FR005_cell_without_a_person_becomes_a_company_note`, `test_edge_more_than_20_people_is_shortened`, `test_FR024_render_then_parse_round_trips` (property test) | cell parser and renderer |
| `unit/search/test_company_match.py` | `test_FR003_website_ignores_www_scheme_and_trailing_slash`, `test_FR003_website_match_beats_name_match`, `test_US1_AS4_two_matches_are_ambiguous`, `test_FR003_name_ignores_case_spacing_punctuation_and_suffix` | company matching |
| `unit/search/test_contacts.py` | `test_FR012_link_must_be_http_or_https`, `test_FR012_email_and_phone_shapes`, `test_FR009_only_name_is_required` | field checks |
| `integration/search/test_contacts_repo.py` | `test_FR006_same_company_and_name_is_unique`, `test_FR023_deleting_own_company_removes_contacts_and_note`, `test_FR025_seed_update_keeps_contacts_attached`, `test_SC007_delete_all_removes_contacts_and_notes`, `test_FR021_seed_with_contacts_field_is_rejected` | storage rules |
| `api/search/test_sheet_import_api.py` | `test_US1_AS1_contacts_attach_and_shipped_facts_unchanged`, `test_US1_AS2_unknown_company_added_as_own`, `test_US1_AS2_row_without_careers_link_is_added_unresolved`, `test_SC001_every_named_contact_in_the_sample_is_attached`, `test_edge_same_name_at_two_companies_stays_two_contacts`, `test_US1_AS4_skipped_rows_listed_with_reason`, `test_US1_AS5_second_import_changes_nothing`, `test_US1_AS5_changed_role_updates_not_duplicates`, `test_US1_AS6_result_counts`, `test_R5_typed_note_is_kept_on_reimport`, `test_SC001_sixty_two_rows_under_ten_seconds`, `test_FR001_wrong_file_type_is_refused_before_saving` | import |
| `api/search/test_contacts_api.py` | `test_US2_AS2_contact_with_only_a_name`, `test_US2_AS3_edit_and_delete_persist`, `test_US2_AS6_bad_link_is_refused`, `test_FR010_note_set_and_clear`, `test_US2_AS5_job_company_panel_data` | CRUD |
| `api/search/test_export_contacts.py` | `test_US4_AS2_default_export_has_no_contact_fields`, `test_US4_AS3_opt_in_export_round_trips_through_sheet_import` | export |
| `api/search/test_delete_contacts_api.py`, `api/search/test_review_fixes_002b.py` | removal paths over HTTP; `preview_expired`, a preview used up only after it is saved, one huge cell gives 422, duplicate contact name at once gives 409 | removal, review fixes |
| `security/test_contacts_privacy.py` | `test_FR022_no_ai_call_contains_contacts_or_notes`, `test_FR015_contacts_code_has_no_http_client`, `test_FR015_no_send_path_in_contacts_code`, `test_FR022_workflows_cannot_import_contacts` | privacy |
| `frontend` (Vitest) | company row counts and filters, company panel add/edit/delete with confirm, sheet import preview and result, job detail panel | UI |
| `frontend/e2e/company-contacts.spec.ts` | import the synthetic sheet, see counts, reach the contacts in one click, add a contact, export with and without contacts, delete all | journey |
