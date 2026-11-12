# Feature Specification: Navigation and pipeline

**Feature Branch**: `002d-navigation-and-pipeline`

**Created**: 2026-11-11

**Status**: Draft

**Input**: User description: "Restructure HireTitan's navigation and remove AI cost, decided by Ravi on 2026-11-11, with constitution v2.0.0 (Principle IV: no AI cost estimation, display or cap; the provider's out-of-credit/quota answer is the only spend stop). (1) Home: two tabs above the job list, Explore and In pipeline (every job the person has applied to or inquired about, replacing the Applied page). (2) A new 'I inquired' mark next to 'I applied'. (3) Preferences and Search rules become tabs inside Profile. (4) Review leaves the sidebar and shows as a notice on Home. (5) Settings keeps only the AI key status and Delete all my data. (6) Remove AI cost everywhere. Resulting sidebar: Home, Companies, Profile, Settings."

Builds on features 001 (`specs/001-setup-and-profile/`), 002 (`specs/002-job-search/`) and 002b (`specs/002b-company-contacts/`). It changes where existing screens live and removes the budget machinery that constitution v2.0.0 no longer allows; it adds one new piece of data, the inquired mark. HireTitan still never sends a message, email or application.

## Clarifications

### Session 2026-11-11

- Q (2026-11-12): What should the app look like? → A: Ravi's mockup: flat dark navy, one orange accent, icon sidebar, no logo (the name is plain text), Companies as lines with a second line, slate chip buttons; the row hover tint is a soft, low-opacity rust and the row action icons keep their earlier colours. Added as User Story 6. Later the same day: no logo anywhere, the name is plain text.
- Q: When a company's only pipeline job is inquired, what does the Companies page show? → A: an **Inquired** chip (an applied job anywhere at the company shows **Applied** instead), and the filter becomes **In pipeline**, listing companies with an applied or an inquired job.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One home for new jobs and my pipeline (Priority: P1)

The person opens HireTitan and sees two tabs above the job list: **Explore**, with the jobs found by searches (the search panel, filters and possible duplicates stay here), and **In pipeline**, with every job they have applied to or inquired about. They switch between the two without leaving Home. The separate Applied page and its menu entry are gone; a saved link to it opens the In pipeline tab.

**Why this priority**: the job list is where the person spends most of their time; seeing new jobs and jobs already in motion in one place is the main point of the change.

**Independent Test**: With some jobs in Explore and some marked applied, open Home: Explore is selected and lists only Explore jobs; choose In pipeline and see only the applied (and inquired) jobs in the table; open the old Applied address and land on In pipeline.

**Acceptance Scenarios**:

1. **Given** jobs in Explore and jobs marked applied, **When** the person opens Home, **Then** the Explore tab is selected and shows the Explore jobs with the search panel, filters and possible-duplicates notice.
2. **Given** the same jobs, **When** the person chooses **In pipeline**, **Then** a table lists every applied or inquired job with company, role, date, status (Applied or Inquired) and source, newest date first, and a row opens to show the job's description and sources.
3. **Given** the person is on In pipeline, **When** they reload the page or come back to Home later, **Then** the same tab is selected.
4. **Given** a saved link to the old Applied page, **When** the person opens it, **Then** Home opens on the In pipeline tab.
5. **Given** no applied or inquired jobs, **When** the person opens In pipeline, **Then** they see a short message saying nothing is in the pipeline yet and how to add a job to it.

---

### User Story 2 - Mark a job as inquired (Priority: P1)

Next to **I applied**, every job in Explore (and on a job's own page) has **I inquired**, for when the person has asked a recruiter or a contact about the job but has not applied. The job moves to In pipeline with the status **Inquired** and the date of the inquiry. The person can undo it, change it to applied later, and searches leave it alone just as they leave applied jobs alone.

**Why this priority**: the In pipeline tab is only useful if it holds the jobs the person is actively pursuing, and asking about a job is often the first step.

**Independent Test**: Mark an Explore job as inquired with today's date; it leaves Explore and shows in In pipeline as Inquired; mark it applied; it shows as Applied with the applied date; undo returns it to Explore.

**Acceptance Scenarios**:

1. **Given** a job in Explore, **When** the person presses **I inquired** (date defaults to today, editable), **Then** the job leaves Explore and appears in In pipeline with status Inquired and that date.
2. **Given** an inquired job, **When** the person presses **I applied**, **Then** its status becomes Applied with the applied date, and it stays in In pipeline.
3. **Given** a job just marked inquired, **When** the person presses **Undo**, **Then** it returns to Explore with no inquired date.
4. **Given** an inquired job, **When** a later search sees the same posting, **Then** the job keeps its inquired status and date and does not come back to Explore.
5. **Given** a date in the future or more than two years ago, **When** the person saves the mark, **Then** it is refused with a message, as for applied.
6. **Given** the Companies page, **When** a company has an inquired job and no applied job, **Then** the company's chip reads **Inquired**; a company with at least one applied job reads **Applied** (applied wins over inquired); the Companies filter "Has an application" becomes **In pipeline** and lists companies with an applied or an inquired job.

---

### User Story 3 - No AI cost anywhere (Priority: P1)

The person never sees an AI cost figure, a budget or a "budget reached" pause. AI work runs until it is done or the provider says the account has no credit left; then the work pauses, finished work is kept, the provider's message is shown, and **Check again** resumes it once the person has added credit.

**Why this priority**: constitution v2.0.0 forbids cost estimates and budget caps; until they are gone the product does not comply with its own rules.

**Independent Test**: Run a search with the AI on: no cost appears during or after it; the search summary and history show no cost; Settings has no budget; the profile and setup screens show no cost. Make the provider answer "out of credit": the search stops after the current batch with the provider's message, and Check again continues it.

**Acceptance Scenarios**:

1. **Given** a search with the AI on, **When** it runs and finishes, **Then** no cost or spend figure appears in the search panel, the search summary or the search history.
2. **Given** Settings, the Profile page and the setup screens, **When** the person opens them, **Then** none shows a cost, a spend total or a budget.
3. **Given** any amount of AI use in a month, **When** the person starts more AI work, **Then** it is never paused or refused because of a budget.
4. **Given** the provider answers that the account is out of credit, **When** that happens during a search or a resume reading, **Then** the work pauses with the provider's message, finished work is kept, and **Check again** resumes it after credit is added.
5. **Given** earlier installs that saved a budget or have runs paused because of a budget, **When** they update, **Then** those runs end with a clear message saying the old budget is gone and can be started again, and the stored budget is no longer used or shown.

---

### User Story 4 - Profile holds my preferences and search rules (Priority: P2)

The Profile page has three tabs: **Profile** (resume, the confirmed profile, versions), **Preferences** and **Search rules**. The Preferences and Search rules menu entries are gone. Saved links to the old addresses open the matching tab.

**Why this priority**: these are all "about me" settings that the person sets once and revisits rarely; grouping them shortens the menu.

**Independent Test**: Open Profile, switch to Preferences and Search rules, change and save something on each; open the old addresses and land on the matching tab.

**Acceptance Scenarios**:

1. **Given** the Profile page, **When** the person chooses the Preferences tab, **Then** they see and can save their preferences exactly as before.
2. **Given** the Profile page, **When** the person chooses the Search rules tab, **Then** they can propose, edit and approve rules exactly as before.
3. **Given** saved links to the old Preferences or Search rules pages, **When** the person opens them, **Then** Profile opens on the matching tab.
4. **Given** the setup checklist on Home says the search rules need approval, **When** the person follows its link, **Then** Profile opens on the Search rules tab.

---

### User Story 5 - A shorter menu, with review items on Home (Priority: P2)

The menu has four entries: **Home**, **Companies**, **Profile**, **Settings**. Items waiting for the person (a profile to review, a suspicious-content decision, a paused run) appear as a notice on Home that says how many there are and links to them. Settings shows only the AI key status (with Check again) and Delete all my data.

**Why this priority**: a short menu is easier to scan; review items are rare and need attention where the person already is.

**Independent Test**: Count the menu entries (four); with one review item waiting, Home shows a notice that opens it; with none, no notice; Settings shows only the key status and the danger zone.

**Acceptance Scenarios**:

1. **Given** the app after setup, **When** the person looks at the menu, **Then** it has exactly Home, Companies, Profile and Settings.
2. **Given** one or more items waiting for review, **When** the person opens Home, **Then** a notice shows how many and opens the review list.
3. **Given** no items waiting, **When** the person opens Home, **Then** no review notice is shown.
4. **Given** a saved link to the old Review page, **When** the person opens it, **Then** the review list still opens (it is reached from the notice, not from the menu).
5. **Given** Settings, **When** the person opens it, **Then** it shows the AI key status with Check again and Delete all my data, and nothing about budgets or models.

---

### User Story 6 - A calmer, flat look (Priority: P2)

The whole app uses one flat dark theme: a dark navy page, a slightly lighter sidebar, white text, and one warm accent, orange, for the active menu item, links, focus and selected states. There are no gradients or glows. The sidebar shows an outline icon next to every item and a thin line on its right edge. There is no logo anywhere: the app name is plain text, HireTitan, at the top of the sidebar, and the browser tab has no icon. On the Companies page each company is a plain line with a thin divider instead of a card, with a smaller second line under the name (the company's website), a plain title-case column header, and the row action icons in their own colours. Hovering a row tints it with a soft, see-through rust. The page's buttons (Show, Import / export, Check manually, Add a company) are filled slate chips with an icon.

**Why this priority**: the app is used for long sessions; a calm, flat look with one accent is easier on the eyes and makes the important things (the active section, the row under the pointer) stand out.

**Independent Test**: open any page: the page is flat navy, the active menu item is orange with its icon, every menu item has an icon, the name HireTitan is plain text at the top of the sidebar with no logo; on Companies the rows are lines with dividers and a second line, hovering a row shows a soft rust tint, the action icons keep their colours, the toolbar buttons are slate chips with icons; every text colour on the page and the surfaces meets the AA contrast ratio.

**Acceptance Scenarios**:

1. **Given** any page, **When** the person opens it, **Then** the background is flat dark navy with no gradient, text is white or muted grey, and the only accent colour is orange.
2. **Given** the sidebar, **When** the person looks at it, **Then** every item has an outline icon, the current section is highlighted with the orange accent, a thin line separates the sidebar from the page, and the app name is plain text with no logo or other graphic.
3. **Given** the Companies page, **When** the person looks at the list, **Then** each company is a plain line with a divider, its name has the website in a smaller second line, the header is plain title-case text, and the action icons show their own colours (details, website, careers page, hide, edit, delete).
4. **Given** the Companies page, **When** the person points at a row, **Then** the row gets a soft, see-through rust tint that leaves its text and icons easy to read.
5. **Given** the Companies toolbar, **When** the person looks at it, **Then** Show, Import / export, Check manually and Add a company are filled slate chips, each with an icon.

---

### Edge Cases

- An inquired job whose posting is merged into another as a duplicate keeps its inquired status on the job that remains, as an applied job does.
- Undo after marking inquired works only while the Undo notice is shown; after that the person changes the status from the job's page, as for applied.
- Delete all my data removes inquired marks with the jobs.
- An inquired job cannot be marked inquired again; an applied job cannot be moved back to inquired (applying is the later step). Undo of applied on a job that was inquired before returns it to Explore (it does not restore the inquiry).
- A run that was paused because of a budget before this change is resumed or failed safely on update; it never stays paused forever with no way out.
- Old saved links to `/applied`, `/preferences`, `/search/rules` and `/review` keep working.
- The small screen layout keeps the tabs above the list and the four menu entries.

## Requirements *(mandatory)*

### Functional Requirements

**Home and pipeline**

- **FR-001**: Home MUST show two tabs above the job list, Explore and In pipeline, with Explore selected by default; the chosen tab MUST survive a reload (it is part of the page address).
- **FR-002**: Explore MUST keep everything the current job list has: the search panel, filters, sort, possible duplicates, Add a job, and the setup checklist until setup is complete.
- **FR-003**: In pipeline MUST list every job whose status is Applied or Inquired in one table with company, role, date (applied date or inquired date), status, and source, newest date first; a row MUST open to show the job's description and sources and link to the job's page.
- **FR-004**: The separate Applied page and its menu entry MUST be removed; its address MUST open Home on the In pipeline tab.

**Inquired mark**

- **FR-005**: A job in Explore, or a skipped job, MUST offer **I inquired** next to **I applied**, with a date that defaults to today and can be changed; the same rules as the applied date apply (not in the future, not more than two years ago).
- **FR-006**: Marking a job inquired MUST move it to In pipeline with status Inquired and the inquired date; an Undo MUST be offered for 10 seconds, as for applied.
- **FR-007**: An inquired job MUST be markable as applied; it then shows status Applied with the applied date. An applied job MUST NOT be marked inquired.
- **FR-008**: Later searches MUST leave inquired jobs alone (status and date kept, never returned to Explore), exactly as for applied jobs.
- **FR-009**: On the Companies page, a company with an applied job MUST show an **Applied** chip; a company with only inquired jobs MUST show an **Inquired** chip; the filter MUST be named **In pipeline** and list companies with either. Sorting by that column MUST put Applied first, then Inquired, then the rest.

**No AI cost**

- **FR-010**: No screen MUST show an AI cost, a spend total, a budget or a cost estimate.
- **FR-011**: AI work MUST NOT be paused, refused or stopped because of a budget; the monthly budget setting MUST be removed.
- **FR-012**: When the provider answers that the account is out of credit or over its quota, AI work MUST pause, keep finished work and show the provider's message; Check again MUST resume it (unchanged from features 001 and 002).
- **FR-013**: AI calls MUST still be recorded with provider, model, token counts, latency and outcome, and MUST NOT record a cost.
- **FR-014**: Installs updated from an earlier version MUST NOT keep any run paused because of a budget: such runs resume or end with a clear status.
- **FR-015**: Evaluation reports MAY show token counts and MUST NOT show cost.

**Profile, menu, review, settings**

- **FR-016**: The Profile page MUST have three tabs, Profile, Preferences and Search rules, each doing what the former page did; the chosen tab MUST be part of the page address.
- **FR-017**: The old Preferences and Search rules addresses, and every link inside the app that pointed to them, MUST open Profile on the matching tab.
- **FR-018**: The menu MUST have exactly four entries: Home, Companies, Profile, Settings.
- **FR-019**: When review items are waiting, Home MUST show a notice with their number that opens the review list; with none, no notice. The review list itself MUST stay reachable at its address.
- **FR-020**: Settings MUST show only the AI key status (with Check again) and Delete all my data.

**Look (User Story 6)**

- **FR-021**: The app MUST use one flat dark theme: no gradients or glows; a dark navy page, a slightly lighter sidebar and panels, white and muted grey text, and orange as the only accent (active menu item, links, focus ring, selected states). Every text colour MUST reach a contrast ratio of at least 4.5:1 on the page and panel colours.
- **FR-022**: The sidebar MUST show an outline icon next to each item, highlight the current section with the accent, and have a thin divider on its right edge. The app MUST show no logo or other graphic mark anywhere (sidebar, setup screens, browser tab, README); the app name is plain text, HireTitan, at the top of the sidebar.
- **FR-023**: On the Companies page each company MUST be a plain line with a thin divider (not a card), with the website shown as a smaller second line under the name when the company has one, and a plain title-case column header.
- **FR-024**: Pointing at a company row MUST tint it with a soft, see-through rust; the row action icons MUST keep their own colours (details, website, careers page, hide, edit, delete).
- **FR-025**: The Companies toolbar buttons (Show, Import / export, Check manually, Add a company) MUST be filled slate chips, each with an icon.

### Key Entities

- **Job status** (from feature 002): gains a new value, **Inquired**, with its own date. Explore, Skipped, Applied and Deleted keep their meaning. In pipeline = Applied or Inquired.
- **Pipeline entry** (derived, not stored): a job with status Applied or Inquired, as shown in the In pipeline table.
- **AI call record** (from feature 001): keeps provider, model, tokens, latency and outcome; no longer carries a cost.
- **Settings** (from feature 001): no longer carries a budget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The menu has exactly 4 entries, and every screen of the earlier menu is reachable in 2 clicks or fewer from it, except the review list, which is reached in 1 click from the Home notice whenever items are waiting (with nothing waiting there is nothing to review).
- **SC-002**: Marking a job inquired, then applied, then undoing each takes 1 click per step (plus a date only when the person changes it), and the job is in the right tab after each step in 100% of cases in the test set.
- **SC-003**: 0 screens show an AI cost, spend or budget, checked by a test that scans every page for cost text and by the end-to-end journey.
- **SC-004**: 0 AI tasks are paused or refused for budget reasons, with any amount of earlier AI use; an out-of-credit answer still pauses work in 100% of the out-of-credit tests and Check again resumes it.
- **SC-005**: 100% of the old addresses (`/applied`, `/preferences`, `/search/rules`, `/review`) open the right place.
- **SC-006**: Later searches change 0 inquired jobs, in a test that searches again over jobs marked inquired.
- **SC-007**: 100% of the theme's text colours reach at least 4.5:1 contrast on the page and panel colours, checked by the contrast test; 0 gradients remain in the theme.

## Assumptions

- The inquired date follows the applied-date rules from feature 002 (today by default, not in the future, at most two years ago).
- "Status" in the In pipeline table shows Applied or Inquired only; richer statuses (interviewing, offer, rejected) arrive with feature 003 (applications).
- Inquiring never sends anything: it is a note the person makes after asking someone themselves (constitution I).
- The review list page stays as it is; only its menu entry is removed.
- Removing the budget also removes the setup screens' budget wording and the 002 "full search cost under limit" test; the provider's out-of-credit handling from feature 002 stays as it is.
- Stored cost figures in existing AI call records and search runs are removed when the install is updated; new records do not compute a cost.
- The Search history and search summary pages stay reachable from the Explore tab's search panel, without cost.
