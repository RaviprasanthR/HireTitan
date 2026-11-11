# Feature Specification: Company contacts, notes and open roles

**Feature Branch**: `002b-company-contacts`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "002b-company-contacts: On the Companies page, show per company (1) the person's own contacts at that company (name, role, LinkedIn link, confidence), imported locally from a spreadsheet such as the maintainer's "Product companies" sheet (columns: Org Name, Location, Company site, Careers page, HR / LinkedIn contacts, Frontend openings, Backend openings, Notes) — stored only in the user's local database, never in the repo or the shipped list; (2) the person's private notes per company (from the import or typed); (3) live counts of open Frontend / Backend (and QA) jobs per company, taken from HireTitan's own search results rather than the sheet's stale snapshot. The import matches rows to existing companies by name/website, adds unknown companies as the person's own, lists rows it could not use with the reason, and can be re-run without creating duplicates. Contacts and notes are included in export and in Delete all my data. HireTitan never messages or contacts anyone; contacts are for the person's reference only."

Builds on feature 002 (`specs/002-job-search/`): the Companies page, the shipped company list, the person's own companies, spreadsheet import and export, search results and Delete all my data. Earlier decisions recorded in `docs/CONTEXT.md` (2026-11-07) are carried in here: contacts are the person's own data, kept only in their own install; LinkedIn links are stored and shown but never opened or read by HireTitan; HireTitan never contacts anyone (drafting messages is feature 004).

> **Change of scope, 2026-11-11 (maintainer decision).** User Story 3 (open front end, back end and QA counts, FR-017 to FR-020 and SC-005) is **dropped**: open roles change all the time and HireTitan does not keep them current, so showing them would mislead. In its place the Companies page shows one simple fact per company: **whether the person has an application there** (a job in the applied state). It is a yes or no (`has_application` in the company list), shown as an "Applied" column, a "Has an application" filter and a sort. The sheet import still ignores the sheet's own openings columns (FR-008). The work done for T019 to T023 (title-to-area classifier, openings counts, the `area` filter on `GET /jobs`) was removed. Other Companies page changes the same day: one compact row per company with aligned columns, a sortable header, a search box, a company-site icon and a careers-page icon, the company name opening the company site, details on expand, and import and export behind one button.

## Clarifications

### Session 2026-11-08

- Q: Should the job links in the sheet's openings columns be added to Explore as pasted jobs, or ignored? → A: Ignored (listed as ignored columns in the import result; the person can paste any link into Explore themselves).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bring my company sheet in, contacts and notes included (Priority: P1)

The person keeps a spreadsheet of companies they want to work at, with the people they know or have found there and their own notes. They import that file on the Companies page. Each row is matched to a company already on the list (by website or name); companies not on the list are added as the person's own. The contacts and notes from each row are attached to the matching company. Rows that cannot be used are listed with the reason. Importing the same file again changes nothing.

**Why this priority**: The person already has this information in a sheet. Without the import they would retype dozens of contacts by hand, and nothing else in this feature has data to show.

**Independent Test**: Import a synthetic sheet with the same columns as the maintainer's sheet (company name, location, site, careers page, contacts cell, two openings cells, notes) against a fresh install with the shipped list. Check that rows match the right companies, new companies are added as the person's own, contacts and notes are attached, the problem rows are listed with reasons, and a second import of the same file reports no changes.

**Acceptance Scenarios**:

1. **Given** the shipped company list and a sheet whose rows name companies on that list, **When** the person imports it, **Then** each row's contacts and notes are attached to the matching company, and the shipped company facts (name, city, careers link, job board) are not changed.
2. **Given** a sheet row for a company that is not on the list, **When** it is imported, **Then** the company is added as the person's own, with its name, location, website and careers link (the careers link may be empty), and goes through the same job-board matching and confirmation as a company added by hand in feature 002.
3. **Given** a contacts cell with several people, each with a name, a role, a confidence tag such as `[High]`, `[Med]` or `[Low]`, and a LinkedIn link on the next line, **When** it is imported, **Then** one contact is created per person with those four facts, and text the import cannot place is kept as a note on the contact rather than dropped.
4. **Given** a row with no company name, or a company name that matches two companies equally, **When** it is imported, **Then** that row is listed with the reason ("no company name", "matches two companies: A, B") and nothing from it is saved.
5. **Given** the same file was imported before, **When** it is imported again, **Then** no contact, note or company is duplicated and the import reports that nothing changed; a contact whose role or link changed in the file is updated, not duplicated.
6. **Given** the import finished, **When** the person looks at the result, **Then** they see how many rows matched, how many companies were added, how many contacts were added or updated, and the list of rows that were skipped with their reasons.
7. **Given** I edited a company's note by hand, **When** I re-import a sheet with a different note for that company, **Then** my note stays and the result says it was kept.

---

### User Story 2 - See and keep my contacts and notes per company (Priority: P1)

On the Companies page, each company shows how many contacts and whether it has a note. Opening a company shows its contacts (name, role, LinkedIn link, how sure the person is, any note on the contact) and the person's notes for that company. The person can add, edit and delete contacts and edit the notes by hand. The LinkedIn link is shown as a link the person can open themselves; HireTitan does not open or read it.

**Why this priority**: This is what the person asked for: when they look at a company, they see who to approach and what they already know about it.

**Independent Test**: With a company that has two imported contacts and a note, open it, check both contacts and the note are shown, add a third contact by hand, edit one, delete one, change the note, reload, and check the changes stayed.

**Acceptance Scenarios**:

1. **Given** a company with contacts and a note, **When** the person opens the Companies page, **Then** the company's row shows the number of contacts and a note marker, and opening it shows each contact's name, role, LinkedIn link and confidence, and the note.
2. **Given** a company, **When** the person adds a contact with only a name, **Then** it is saved; role, LinkedIn link, email, phone, confidence and note are optional.
3. **Given** a contact, **When** the person edits or deletes it, **Then** the change is kept after a reload, and deleting asks for confirmation first.
4. **Given** a contact with a LinkedIn link, **When** it is shown, **Then** the link opens in a new browser tab only when the person clicks it, and HireTitan never fetches it.
5. **Given** a job in Explore or Applied whose company has contacts, **When** the person opens that job, **Then** the company's contacts and note are shown with it.
6. **Given** a contact link that is not a web address (for example plain text), **When** it is saved, **Then** the person is told it is not a valid link and the contact is not saved until it is fixed or cleared.

---

### User Story 3 - See which companies have open front end, back end and QA roles (Priority: P2)

The Companies page shows, per company, how many open jobs HireTitan has found there for front end, back end and QA roles, from HireTitan's own search results. The person can sort or filter by these counts to see which companies are worth their time right now. The openings columns in an imported sheet are a stale snapshot and are not used for these counts.

**Why this priority**: It turns the list into a to-do list (where to apply first) but needs search results to exist, so it comes after the contacts.

**Independent Test**: With search results containing jobs at two companies (titles such as "Senior Frontend Engineer", "Backend Developer (Go)", "SDET", "Marketing Manager"), open the Companies page and check each company shows the right counts per area, that a closed or hidden job is not counted, and that filtering by "has back end openings" shows only the right company.

**Acceptance Scenarios**:

1. **Given** open jobs found at a company, **When** the person opens the Companies page, **Then** the company shows the number of open front end, back end and QA jobs, and each count links to those jobs.
2. **Given** a job whose title fits none of the three areas, **When** counts are shown, **Then** it is not counted in any of them.
3. **Given** a full stack job, **When** counts are shown, **Then** it is counted in both front end and back end.
4. **Given** a job that has closed, or that the person marked as applied, **When** counts are shown, **Then** it is not counted as open.
5. **Given** a company that was never searched, **When** it is shown, **Then** its counts show "not searched yet", not zero.

---

### User Story 4 - My contacts stay mine (Priority: P2)

Contacts and notes stay in the person's own install. They are never written to the shipped list, never sent to the AI, and are removed by Delete all my data. Export leaves them out unless the person chooses to include them.

**Why this priority**: The contacts are third-party personal data. Keeping them out of the product and out of AI calls is a constitution rule (principle VIII), not a nice-to-have.

**Independent Test**: Import contacts, run a search, export with and without the "include contacts and notes" option, then use Delete all my data. Check the AI calls of the search contain no contact data, the default export has no contacts, the opt-in export has them and can be imported back, and after Delete all no contact or note remains.

**Acceptance Scenarios**:

1. **Given** contacts and notes exist, **When** the person uses Delete all my data, **Then** every contact and note is removed.
2. **Given** contacts exist, **When** the person exports the company list without choosing to include contacts, **Then** the file contains no contact names, links, emails, phones or notes.
3. **Given** contacts exist, **When** the person exports and chooses to include contacts and notes, **Then** the file contains them in the same columns the import accepts, and importing that file into a fresh install restores them.
4. **Given** contacts exist, **When** a search runs, **Then** no contact data or company note is sent to the AI provider.
5. **Given** a newer shipped company list arrives with an app update, **When** it is applied, **Then** the person's contacts and notes are kept and stay attached to the same companies.

---

### Edge Cases

- A sheet with extra empty rows or header rows above the real header (the maintainer's sheet has five empty rows and two empty columns before the data): the import finds the header row by its column names and ignores empty rows.
- Column names that differ slightly ("Org Name" vs "Company", "HR / LinkedIn contacts" vs "Contacts"): the import recognises a fixed set of names for each column and tells the person which columns it used and which it ignored.
- A contact cell that is free text without names or links ("no LinkedIn URL found - name via RocketReach"): kept as a contact note on the closest named person, or as a company note if no person is named.
- The same person listed under two companies: kept as two contacts (one per company); no merging across companies.
- Two different people with the same name at one company cannot both be stored; the person can tell them apart by adding a role to the name.
- A contact with an email or phone in the sheet: stored like the other fields; still never used to send anything.
- A company that the person has hidden: its contacts and notes are kept and shown when the person shows hidden companies.
- A company the person deletes (their own only, as in feature 002): its contacts and notes are deleted with it after confirmation that says how many contacts will go.
- A very large contacts cell (more than 20 people) or a note longer than 5,000 characters: imported up to the limit, and the row is listed as "shortened" with the reason.
- An import file that is not a spreadsheet, or is larger than the import limit set in feature 002: rejected with the reason before anything is saved.
- The website in the sheet points to the same company as a shipped entry but with a different form (`www.`, trailing slash, `http` vs `https`): treated as the same website.

## Requirements *(mandatory)*

### Functional Requirements

**Import**

- **FR-001**: The person MUST be able to import a spreadsheet file of companies on the Companies page; the import MUST accept the same file types as the company import in feature 002 and the column layout of the maintainer's sheet (company name, location, company site, careers page, contacts, front end openings, back end openings, notes).
- **FR-002**: The import MUST find the header row by its column names, MUST ignore empty rows and columns, and MUST report which columns it used and which it ignored.
- **FR-003**: Each row MUST be matched to an existing company by website first (ignoring `www.`, scheme, and trailing slash) and by name second (ignoring case, spacing and punctuation); a row that matches no company MUST add the company as the person's own; a row that matches more than one company MUST be skipped with the reason.
- **FR-004**: The import MUST NOT change the shipped facts of a built-in company (name, city, careers link, job board); it MAY fill a missing website or careers link on the person's own companies.
- **FR-005**: The import MUST split a contacts cell into one contact per person, reading name, role, confidence (`High`, `Med`/`Medium`, `Low`) and LinkedIn link where present, and MUST keep any text it cannot place as a note instead of dropping it.
- **FR-006**: Re-importing MUST NOT create duplicates: a contact is identified by its company and its name (ignoring case, spacing and punctuation), so a company holds at most one contact of a given name; when no contact of that name exists but one at the same company has the same LinkedIn link, that contact is updated and renamed; a changed role, confidence, link, email, phone or note on the same contact MUST update it.
- **FR-007**: The import MUST show a result: rows matched, companies added, contacts added, contacts updated, notes added or changed, notes kept because the person edited them by hand, and each skipped or shortened row with its reason; nothing from a skipped row is saved.
- **FR-007a**: A re-import MUST replace a note it imported earlier when the text differs, MUST NOT replace a note the person has edited by hand, and MUST NOT delete a note when the sheet's note cell is empty.
- **FR-008**: The openings columns of an imported sheet MUST NOT be used for the open-role counts. The import MUST NOT add the job links in those columns to Explore; the columns are listed as ignored in the import result.

**Contacts and notes**

- **FR-009**: Each company MUST be able to hold any number of contacts, each with a name (required) and optional role, LinkedIn link, email, phone, confidence and note.
- **FR-010**: Each company MUST be able to hold one free-text note written by the person.
- **FR-011**: The person MUST be able to add, edit and delete contacts and edit the note by hand; deleting a contact MUST ask for confirmation.
- **FR-012**: Links MUST be checked to be web addresses before saving; emails and phones MUST be checked for a plausible format.
- **FR-013**: The Companies page MUST show per company the number of contacts and whether it has a note; opening a company MUST show its contacts and note.
- **FR-014**: When a job is opened in Explore or Applied, the contacts and note of its company MUST be shown with it.
- **FR-015**: HireTitan MUST NOT open, fetch or read any contact link, MUST NOT send any message, email, connection request or application to a contact, and MUST NOT look up people on any site.

**Open-role counts**

- **FR-016**: The Companies page MUST show per company the number of open jobs found by HireTitan in each of three areas: front end, back end, QA; each count MUST link to those jobs.
- **FR-017**: A job MUST be placed in areas by its title (and, when available, the short role from feature 002); a full stack job counts as front end and back end; a job that fits no area is not counted.
- **FR-018**: Only open jobs count: jobs that have closed, are marked as applied, or were skipped by the rules or the AI are not counted.
- **FR-019**: A company that has never been searched MUST show "not searched yet" instead of zero counts.
- **FR-020**: The person MUST be able to sort and filter the Companies page by these counts and by "has contacts".

**Privacy**

- **FR-021**: Contacts and notes MUST be stored only in the person's own install; they MUST NOT be added to the shipped company list or to any file in the product.
- **FR-022**: Contacts and notes MUST NOT be sent to the AI provider in any call.
- **FR-023**: Delete all my data MUST remove all contacts and notes; deleting one of the person's own companies MUST delete its contacts and note after a confirmation that states how many contacts will go.
- **FR-024**: Export MUST leave out contacts and notes unless the person chooses to include them; an export that includes them MUST use columns the import accepts.
- **FR-025**: Updating the shipped company list MUST keep the person's contacts and notes attached to the same companies.
- **FR-026**: Test fixtures and demo data for this feature MUST be synthetic; no real person's name, link, email or phone may appear in the repository.

### Key Entities

- **Contact**: a person the user knows of at a company. Belongs to one company. Name (required); optional role, LinkedIn link, email, phone, confidence (high, medium, low), note; where it came from (import or typed) and when it was last changed.
- **Company note**: the person's free text about one company. One per company; when it was last changed.
- **Import result**: the outcome of one import: counts of rows matched, companies added, contacts added and updated, notes changed, and the skipped or shortened rows with reasons. Shown once; not kept as history.
- **Open-role count**: derived, not stored by the person: per company, the number of open jobs in each area (front end, back end, QA), from feature 002's jobs.
- **Company** (from feature 002): gains its contacts, its note and its open-role counts; its shipped facts are unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Importing a synthetic copy of the 62-row maintainer sheet attaches 100% of contacts that have a name to the right company, with no duplicate companies, and finishes in under 10 seconds.
- **SC-002**: Re-importing the same file creates 0 new contacts, companies or notes.
- **SC-003**: Every skipped row is listed with a reason; 0 rows are dropped without being reported.
- **SC-004**: The person can see who to contact at a company in 2 clicks or fewer from the Companies page or from a job.
- **SC-005**: Open-role counts match the jobs in Explore for 100% of companies in a test set, and title-to-area placement is correct for at least 95% of a labelled set of 100 synthetic job titles.
- **SC-006**: 0 AI calls contain contact data or company notes, checked by recording every AI call during a search with contacts present.
- **SC-007**: After Delete all my data, 0 contacts and 0 notes remain; the default export contains 0 contact fields.

## Assumptions

- The person imports a file they downloaded from their spreadsheet tool (for a Google Sheet, File > Download > Comma-separated values; CSV is the only supported type, as in feature 002); HireTitan does not connect to Google Sheets.
- Front end, back end and QA are the three areas because they are the roles the maintainer targets and match the role suggestions on the Preferences page; more areas can be added later without changing this feature's behaviour.
- Area placement uses title words (for example frontend, front end, react, ui; backend, back end, api, python, java, go, node; qa, test, sdet, quality); full stack counts for both front end and back end. No AI is used for placement.
- Confidence is the person's own judgement copied from the sheet; HireTitan does not compute it.
- "Several locations per company" (from the 2026-11-07 notes) is out of scope here: the location text from the sheet is kept as the company's location for the person's own companies only.
- The feature number `002b` is the working name agreed on 2026-11-07; `docs/clarified-requirements.md` §12 also lists a `002b more-sources`, which will be renumbered when that feature is specified.
- Implementation starts only after feature 002 (PR #4) is merged into `master` and after Ravi approves this spec, its plan and tasks.
