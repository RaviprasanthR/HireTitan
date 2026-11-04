# Feature Specification: Setup and Profile (first slice)

**Feature Branch**: `001-setup-and-profile`

**Created**: 2026-11-03

**Status**: Draft (amended 2026-11-04: first-run setup, US5)

**Input**: User description: "001-setup-and-profile: First basic slice of HireTitan. (1) User preferences: a settings form for job-search preferences (target roles, locations/remote, experience level, pay expectations, currency, notice period, etc.) with documented global/India-friendly defaults, nothing hard-coded. (2) Resume upload and parsing: the user uploads a resume (PDF/DOCX), the system extracts text, and AI extracts a structured profile (contact, summary, experience, education, skills, projects, certifications), treating the file as untrusted input. (3) Profile review and edit: the user reviews the extracted profile, edits or confirms it; the confirmed profile becomes the only source of candidate facts; profile versions link to the resume file they came from. (4) A first-level UI: a basic dashboard shell (dark theme) with navigation to Preferences and Profile, and a status of AI configuration (API key read from .env; an invalid or missing key pauses AI tasks and is shown clearly). Single local user, no login. Requirements baseline: docs/clarified-requirements.md; design: docs/architecture.md."

**Context**: The requirements baseline is `docs/clarified-requirements.md` (§1–3, §9–10) and the approved design is `docs/architecture.md` (W1 `profile_ingest`, §6 untrusted input, §10 first-level UI). This spec covers the **first slice** of feature 001. Items deferred to a later slice are listed under Assumptions → Out of scope.

## Clarifications

### Session 2026-11-03

- Q: Should contact details be hidden from the AI provider during extraction? → A: Email addresses, phone numbers and profile links are extracted locally (no AI) and replaced with placeholders before the AI call; the name is still sent.
- Q: How can the user change the model used for each tier? → A: Not in this slice. Tier models are fixed defaults that Settings shows read-only; editing comes later.
- Q: Is total years of experience computed from profile dates or entered by the user? → A: Entered by the user in Preferences only; it is never computed from the profile.
- Q: Are skills kept as written or mapped to standard names? → A: Kept as written; only duplicates differing in case or spacing are merged. Synonym mapping for matching belongs to feature 002 (search rules).

### Session 2026-11-04

Design: `docs/superpowers/specs/2026-11-04-first-run-onboarding-design.md` (approved).

- Q: What does a first-time user see? → A: Guided setup cards, one at a time and with no sidebar: name, then resume, then profile review, then preferences. The usual app with the sidebar appears only after setup is complete (US5).
- Q: What if the user leaves part-way through setup? → A: They come back to the card they left. Which card to show is worked out from saved data, not from the browser.
- Q: Are preferences shown before a profile exists? → A: No. In the app, preferences come after the profile is confirmed. The API still accepts preferences without a profile (FR-026).
- Q: Does typing the profile in by hand autosave? → A: Yes. "Type it in myself" opens an empty review that autosaves like an extracted one (FR-019).
- Q: Can setup come back once finished? → A: No. Finishing setup is recorded and only "Delete all my data" clears it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Turn my resume into a confirmed profile (Priority: P1)

A person who has just installed HireTitan uploads their resume (PDF or DOCX). The app reads it, the AI pulls out their details (contact, summary, work history with bullets, education, skills, projects, certifications, links), and the person sees the result in an editable review screen. Anything the AI could not find in the document is left out and reported. Anything suspicious in the file (hidden text, instructions aimed at the AI) is flagged. The person corrects and completes the details, then confirms. The confirmed profile is saved as a version linked to the uploaded file and becomes the only source of facts about them for every later AI feature.

**Why this priority**: Every later feature (search rules, drafts, tailored resumes) depends on a confirmed, truthful profile. Without it the app has nothing to work from.

**Independent Test**: Upload a synthetic two-page resume, review the extracted profile, edit one field, and confirm. A profile version now exists, linked to the file, showing the edited value.

**Acceptance Scenarios**:

1. **US1-AS1** — **Given** no profile exists and AI is working, **When** the user uploads a valid PDF or DOCX resume, **Then** the app shows extraction progress and, when it finishes, a review screen pre-filled with the extracted contact, summary, experience (employer, title, location, dates, bullets), education, skills, projects, certifications and links.
2. **US1-AS2** — **Given** the review screen is open, **When** the user edits, adds or removes any field or list item and presses Confirm, **Then** a new profile version is saved with exactly the user's final values, linked to the uploaded resume file, and marked as the current profile.
3. **US1-AS3** — **Given** the AI returned a skill, employer, title, date or number that does not appear in the resume text, **When** the review screen opens, **Then** that item is not in the profile, and a notice lists each dropped item with the reason "not found in your resume".
4. **US1-AS3b** — **Given** the review lists a dropped item, **When** the user chooses "Add anyway" on it, **Then** the item is put back into the review draft as the user's own entry and becomes a profile fact only when the user confirms.
5. **US1-AS4** — **Given** the PDF contains hidden text (e.g. white-on-white, tiny or off-page), **When** the review screen opens, **Then** the hidden text is shown to the user in a visible warning, and it is not used as profile content unless the user adds it by hand.
6. **US1-AS5** — **Given** the resume text contains a high-severity injection signal (e.g. instructions addressed to an AI), **When** parsing finishes, **Then** the process pauses before extraction and shows the flagged text, and the user chooses either to continue with extraction or to stop and fill in the profile by hand.
7. **US1-AS6** — **Given** the file is a scanned image-only PDF with no readable text, **When** parsing finishes, **Then** the user is told the text could not be read and is offered to paste the resume text or fill in the profile by hand.
8. **US1-AS7** — **Given** the AI output is invalid even after one automatic repair attempt, **When** extraction ends, **Then** the user gets whatever partial profile passed checks (possibly empty), with the missing sections marked for manual entry, and nothing the user uploaded is lost.
9. **US1-AS8** — **Given** a confirmed profile exists, **When** the user uploads a newer resume and extraction finishes, **Then** the review opens pre-filled with the new values, every changed field is marked with its current value beside it, and the current profile stays unchanged until the user confirms.
10. **US1-AS9** — **Given** the user leaves the review screen without confirming, **When** they come back later, **Then** the pending review is still there with their unsaved edits kept, and no profile version has been created.

---

### User Story 5 - Get set up step by step (Priority: P1)

A person opening HireTitan for the first time sees a welcome card instead of the full app. The cards ask, one at a time, for their name, then their resume (upload, paste, or "Type it in myself"), then let them check and confirm the profile, then ask what they are looking for. Each card shows its step (1 to 4). After "Finish setup" the usual app with the sidebar opens, and the cards never come back unless all data is deleted. If they leave part-way, they return to the card they left.

**Why this priority**: The app is useless until there is a confirmed profile and preferences. The first visit should lead straight there, without empty pages.

**Independent Test**: On a fresh install, open any URL and see step 1 with no sidebar. Enter a name, upload a synthetic resume, close the tab during review and reopen it: step 3 shows with the edits kept. Confirm, save preferences, press "Finish setup": the usual app opens and greets the user by name.

**Acceptance Scenarios**:

1. **US5-AS1** — **Given** setup is not complete, **When** the user opens any page of the app, **Then** they see the setup card for their current step, with "Step N of 4", and no sidebar or other sections.
2. **US5-AS2** — **Given** step 1, **When** the user enters a name and continues, **Then** the name is saved and step 2 asks for the resume, addressing the user by name.
3. **US5-AS3** — **Given** the user closes the app part-way through setup, **When** they open it again, **Then** they see the card they left, with everything they entered or uploaded still there.
4. **US5-AS4** — **Given** step 2, **When** the user uploads or pastes a resume, **Then** the card shows the extraction progress and moves to step 3 by itself when the review is ready; a pause (key or budget) or the injection decision is shown in the card.
5. **US5-AS5** — **Given** step 2 and the AI key is missing or rejected, **When** the card is shown, **Then** it says that reading a resume needs a working key and how to fix it, and "Type it in myself" stays available, so setup can always be finished.
6. **US5-AS6** — **Given** the user chose "Type it in myself", **When** they type part of the profile and leave, **Then** their entries are kept and step 3 shows them when they come back; confirming creates the first profile version as a manual profile.
7. **US5-AS7** — **Given** a confirmed profile, **When** the user saves preferences in step 4 and presses "Finish setup", **Then** the usual app opens on Home, which greets them by name, and the setup cards no longer appear, even after a later resume upload.
8. **US5-AS8** — **Given** an install that already had a confirmed profile and saved preferences before setup cards existed, **When** the app is opened, **Then** the usual app shows; the user is not asked to go through setup.

---

### User Story 2 - Set my job preferences (Priority: P2)

The person fills in what they are looking for: target roles, seniority, years of experience, key skills, locations and work mode, locations to avoid, job type, expected pay with currency, notice period, and companies they prefer or want to avoid. The form starts from documented defaults (global, India-friendly) and can offer suggestions taken from the confirmed profile. The person saves it and can change it any time.

**Why this priority**: Preferences drive the job search in feature 002. They need no AI, so they can be built and used even if the AI key isn't working yet.

**Independent Test**: In setup step 4 on a fresh install (or Preferences after setup), check the documented defaults are shown, change the roles, locations and pay, save, reload, and see the saved values.

**Acceptance Scenarios**:

1. **US2-AS1** — **Given** preferences have never been saved, **When** the user opens Preferences, **Then** the form shows the documented defaults (see FR-024) and nothing person-specific.
2. **US2-AS2** — **Given** the form is filled, **When** the user saves, **Then** the values persist across reloads and app restarts, and the last-saved time is shown.
3. **US2-AS3** — **Given** a confirmed profile exists, **When** the user opens Preferences, **Then** the app offers the profile's skills and most recent job title as one-click suggestions for key skills and target roles; nothing is added until the user picks it.
4. **US2-AS4** — **Given** the user enters invalid values (e.g. minimum pay above target pay, negative years, empty role list), **When** they save, **Then** the save is refused and each problem is shown next to its field.
5. **US2-AS5** — **Given** the currency is INR, **When** pay is entered or shown, **Then** it uses lakhs per annum (LPA); for other currencies it uses the annual amount in that currency.

---

### User Story 3 - See where I stand and whether AI is working (Priority: P3)

Once setup is complete (US5), the person opens the app and lands on a dark-themed dashboard with a sidebar (Home, Profile, Preferences, Review, Settings). Home shows a setup checklist: AI key found and working, resume uploaded, profile confirmed, preferences saved, each with a link to finish it. If the AI key is missing or rejected, every page shows a clear banner explaining how to fix it (edit the key in the environment file and restart). AI tasks wait instead of failing and continue once the key works. Settings shows the key status (never the key itself), the monthly AI budget cap, this month's AI spend, and which model is used for each model tier.

**Why this priority**: It ties the slice together and makes AI problems visible, but the profile and preferences work on their own without it.

**Independent Test**: Start the app with no key configured. The banner shows "missing" on the setup cards, and after setup the Home checklist shows the key step not done. Add a valid key and restart: the status turns to "found, working" and a resume extraction that was waiting runs to completion.

**Acceptance Scenarios**:

1. **US3-AS1** — **Given** no AI key is configured, **When** the user opens any page, **Then** a banner says the key is missing and explains how to set it and restart (including on the setup cards), and once setup is done the Home checklist shows the key step as not done.
2. **US3-AS2** — **Given** a key is configured but the provider rejects it, **When** the app checks it (at start-up, on "Check again", or on a rejected AI call), **Then** the status becomes "rejected", the banner explains how to replace it, and any running or queued AI task is paused, not failed.
3. **US3-AS3** — **Given** an AI task was paused for a key problem, **When** the user fixes the key and restarts, **Then** the paused task continues automatically from where it stopped, and no user data or upload is lost.
4. **US3-AS4** — **Given** the app is running, **When** the user opens Settings, **Then** they see the key status, the monthly budget cap (default 25 USD) which they can change, this month's spend, and the model used for each tier (read-only), and the key value itself is never shown or sent to the browser.
5. **US3-AS5** — **Given** this month's spend plus the estimated cost of an AI call would exceed the budget cap, **When** that call is about to run, **Then** it is blocked, the user sees "monthly AI budget reached" with a link to Settings, and nothing is lost.
6. **US3-AS6** — **Given** a profile review is waiting for the user, **When** they open Review or Home, **Then** it is listed with a link to open it.

---

### User Story 4 - Delete my data (Priority: P3)

The person can delete an uploaded resume file, or wipe all their HireTitan data and start fresh.

**Why this priority**: Required by the constitution (VIII) for any feature that stores personal data, but rarely used.

**Independent Test**: Upload a resume, confirm a profile, then use "Delete all my data". Profile, preferences, files and AI logs are gone and the app shows setup step 1.

**Acceptance Scenarios**:

1. **US4-AS1** — **Given** an uploaded resume file, **When** the user deletes it and confirms, **Then** the stored file and any pending review from it are removed; profile versions created from it keep their confirmed content and show "source file deleted".
2. **US4-AS2** — **Given** any amount of stored data, **When** the user chooses "Delete all my data" and confirms by typing a confirmation word, **Then** all profiles, versions, preferences, files, AI call logs and settings are removed (except the key in the environment file, which the app never stores), and the app returns to its first-run state.

---

### Edge Cases

- File is not PDF/DOCX, is password-protected, corrupted, or larger than 5 MB → rejected before processing, with a specific message.
- DOCX with text in tables, text boxes, headers or footers → that text is included in parsing.
- Resume in a language other than English → extraction is attempted; there is no translation; whatever is found goes to review as usual.
- Very long resume (beyond the length cap for AI input) → text is truncated at the cap, and the user is told which part was not read.
- Dates such as "Present", "Current", year-only or month-year → normalised; an end date before its start date is flagged in review and blocks Confirm until fixed.
- Duplicate skills differing only in case or spacing → merged into one in review. Otherwise skills keep the resume's wording exactly; there is no synonym mapping in this feature ("ReactJS" and "React" stay separate).
- The user uploads a second resume while a review is pending → the user is asked whether to discard the pending review; there is at most one pending review at a time.
- A resume is uploaded when a confirmed profile already exists → handled as described in FR-014.
- The app or computer restarts during extraction → the task resumes or retries on start-up; the upload is not lost.
- AI call times out or the provider is unreachable → retried a limited number of times, then the task is shown as failed with "Try again"; the upload is kept.
- The user confirms a profile with sections still empty → allowed, except that a name and at least one of experience, education or skills must be present.
- Preferences saved before any profile exists → allowed by the API (FR-026); in the app, setup asks for preferences only after the profile is confirmed. A user with saved preferences but no profile lands on step 2, and step 4 shows their saved values.
- The user chooses "Type it in myself" while a resume is still being read or is paused → they are asked to confirm, and the reading is stopped (cancelled) before the empty review opens.

## Requirements *(mandatory)*

### Functional Requirements

**Resume intake and parsing**

- **FR-001**: Users MUST be able to upload a resume as PDF or DOCX up to 5 MB; other types, encrypted, corrupt or oversized files MUST be rejected with a message saying why.
- **FR-002**: Users MUST be able to paste resume text as an alternative to uploading a file.
- **FR-003**: The system MUST keep every uploaded file unchanged on the user's machine as a resume file record (name, type, size, upload time, content fingerprint).
- **FR-004**: The system MUST extract plain text from the resume, including text in tables, headers and footers, keeping section and bullet structure where present.
- **FR-005**: The system MUST detect hidden text in PDFs (white-on-white, very small, outside the page) and report it to the user in review; hidden text MUST NOT be used as extraction input.
- **FR-006**: The system MUST treat resume text as untrusted: normalise it, strip control characters, cap its length, and screen it for injection signals. Every signal MUST be stored and shown in review.
- **FR-007**: When a high-severity injection signal is found, the system MUST pause before extraction and let the user choose to continue or to fill in the profile by hand.
- **FR-008**: When no text can be read (e.g. a scanned image-only PDF), the system MUST tell the user and offer pasting text or manual entry; no OCR is performed.

**AI extraction**

- **FR-008a**: Before any AI call, the system MUST extract email addresses, phone numbers and profile links from the resume text without AI, and replace them with placeholders in the text sent to the AI. The extracted values go straight into the review's contact section. The name is not masked.
- **FR-009**: The system MUST use AI to extract a structured profile: contact (name, location; email, phone and links come from FR-008a), headline and summary, experience entries (employer, title, location, start and end dates or "current", bullet points), education entries (institution, qualification, field, dates, grade if stated), skills, projects (name, description, technologies, link), and certifications (name, issuer, date).
- **FR-010**: The extraction output MUST be validated against the expected structure and rules (dates in order, no experience entry without employer or title). Invalid output gets one automatic repair attempt, then falls back to the valid part, with the rest marked for manual entry.
- **FR-011**: Every extracted skill, employer, title, institution, date and number MUST be checked against the resume text; any item not found MUST be dropped and listed to the user with the reason. Each drop MUST be undoable: the user can add a dropped item back into the review with one action (US1-AS3b).
- **FR-012**: Each extraction MUST record the prompt version and model used, and each AI call MUST be logged with provider, model, tokens, cost, time taken and outcome.
- **FR-013**: Extraction MUST run in the background with visible progress, and MUST survive an app restart without losing the upload.

**Profile review, confirmation and versions**

- **FR-014**: When a confirmed profile already exists and the user uploads a newer resume, the review MUST open pre-filled with the new extraction, with each field that differs from the current profile marked and its current value shown beside it. Confirming creates a new version; discarding leaves the current profile unchanged. The older resume file is kept. (Per-item accept/reject of a diff comes in a later slice.)
- **FR-015**: The review screen MUST let the user edit, add, remove and reorder every field and list item, and MUST show dropped items, hidden-text findings and injection signals alongside it.
- **FR-016**: Unsaved review edits MUST be kept until the user confirms or discards the review.
- **FR-017**: Confirming MUST create a new, unchangeable profile version holding exactly the user's final values, linked to the resume file (or pasted text) it came from, and make it the current profile.
- **FR-018**: Confirm MUST be blocked, with the reason shown, while there is no name, while experience, education and skills are all empty, or while any entry has an end date before its start date.
- **FR-019**: Users MUST be able to create and confirm a profile entirely by hand, without any resume or AI. A profile typed in by hand before the first confirm MUST be kept as an autosaved review draft (FR-016), so nothing typed is lost on leaving.
- **FR-020**: Users MUST be able to edit the current profile at any time; saving an edit MUST create a new version (the previous version is kept).
- **FR-021**: Users MUST be able to view the list of profile versions (date, source file, what created it: extraction, manual edit) and open any earlier version read-only.
- **FR-022**: The current confirmed profile MUST be the only source of candidate facts available to other features; unconfirmed extractions MUST NOT be.

**Preferences**

- **FR-023**: Users MUST be able to set and save: target roles (one or more), seniority levels, total years of experience (a number the user types; never computed from the profile), key skills, preferred locations (city and country), work modes (on-site, hybrid, remote), willingness to relocate, blocked locations, job types (full-time, contract, internship), expected pay (minimum, optional target, currency, fixed or total compensation), notice period or earliest start date, preferred companies, and companies to avoid.
- **FR-024**: Defaults MUST be documented and changeable, and contain nothing person-specific: country India, currency INR, pay shown in LPA for INR, all work modes allowed, job type full-time, notice period 30 days, and every list empty.
- **FR-025**: Preferences MUST be validated on save (at least one target role; minimum pay ≤ target pay; non-negative years and notice), and errors shown per field.
- **FR-026**: Preferences MUST be saveable through the API without a profile and without working AI. The app shows them only after a profile is confirmed (FR-037).

**Shell, AI status and settings**

- **FR-027**: Once setup is complete (FR-037), the app MUST provide a dark-themed dashboard with navigation to Home, Profile, Preferences, Review and Settings, using the project palette, with text contrast meeting WCAG AA.
- **FR-028**: Home MUST show a setup checklist (AI key found and working, resume uploaded, profile confirmed, preferences saved) with each step's state and a link to complete it.
- **FR-029**: The system MUST read the AI key only from the local environment configuration, check it with a test call at start-up and on request, and report one of: "found, working", "missing", "rejected". The key MUST never be stored by the app, logged, or sent to the browser.
- **FR-030**: When the key is missing or rejected, every page (including the setup cards) MUST show a banner with fix instructions, and AI tasks MUST be paused, not failed, and continue automatically once a valid key is in place after restart.
- **FR-031**: Settings MUST show the key status, an editable monthly AI budget cap (default 25 USD), this month's spend, and the model used for each model tier (fast, strong). In this slice the tier models are fixed defaults, shown read-only.
- **FR-032**: Every AI call MUST be blocked before it runs if this month's spend plus its estimated cost would exceed the cap, and the user MUST be told why.
- **FR-033**: Review MUST list every item waiting for the user's decision (in this slice: pending profile reviews and paused extractions).

**First-run setup**

- **FR-037**: Until setup is complete, every page MUST show a guided setup card instead of the dashboard, in four steps: (1) the user's name, (2) the resume (upload, paste or "Type it in myself"), (3) the profile review, (4) preferences, ending with "Finish setup". Setup is complete when the user finishes step 4 with a confirmed profile and saved preferences.
- **FR-038**: The step shown MUST be worked out from saved data, checked in this order: setup completed → the usual app; no name → step 1; an open profile review → step 3; a resume being read, paused or waiting for the injection decision → step 2 with its progress; no confirmed profile → step 2; otherwise step 4. Leaving and coming back MUST return the user to the same step with nothing lost.
- **FR-039**: The name from step 1 MUST be saved locally, pre-fill the profile name in a review whose name is empty, and be used to greet the user. It is the user's own entry, never AI output.
- **FR-040**: Finishing setup MUST be recorded. After that, the setup cards MUST NOT reappear (for example after a later resume upload) until all data is deleted (FR-035). An install that already has a confirmed profile and saved preferences when this is introduced MUST count as set up.
- **FR-041**: Setup MUST never be a dead end: "Type it in myself" MUST be available in step 2 whatever the AI status, and the setup cards MUST give access to Settings (for the budget cap) and a way back: step 2 to change the name; step 3 to discard the review (after confirmation) and choose another resume.

**Data control**

- **FR-034**: Users MUST be able to delete an uploaded resume file (removing the file and any pending review from it; profile versions keep their content and show the source as deleted).
- **FR-035**: Users MUST be able to delete all their data in one action after typed confirmation, returning the app to its first-run state (setup step 1; the name and the setup-completed record are cleared).
- **FR-036**: The app MUST work for one local user with no sign-in, and MUST never send messages, emails or applications.

### Key Entities

- **Resume file**: an uploaded document or pasted text kept as-is; name, type, size, upload time, fingerprint, parse result (text, hidden-text findings, injection signals).
- **Profile extraction (pending review)**: the AI's validated output for one resume file, plus dropped items, flags and the user's unsaved edits; or an empty review the user is typing by hand, with no file and no AI provenance (FR-019); at most one pending at a time.
- **Profile**: the person's single profile; points to its current version.
- **Profile version**: an unchangeable snapshot of confirmed profile content (contact, summary, experience, education, skills, projects, certifications, links), with its creation time, how it was created, and the source resume file if any.
- **Preferences**: the person's job-search preferences (FR-023), with last-saved time.
- **Settings**: budget cap, model per tier (fixed defaults in this slice), key status (status only, never the key), the user's display name and when setup was completed.
- **AI call log**: one record per AI call: provider, model, task, prompt version, tokens, cost, time taken, outcome.
- **Workflow run**: one run of a background AI workflow (e.g. resume extraction) with state: queued, running, awaiting review (waiting for the user's decision), paused (key or budget problem), done, failed, cancelled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can go from first opening the app (with a working key) to a confirmed profile and saved preferences in under 10 minutes for a typical two-page resume.
- **SC-002**: Extraction of a typical two-page resume finishes within 60 seconds of upload in 95% of runs.
- **SC-003**: On the synthetic evaluation set of resumes, at least 90% of the fields a person would expect (employers, titles, dates, skills, education) are extracted correctly before any manual edit.
- **SC-004**: Zero items that are absent from the resume text reach the review screen as profile content, across the full synthetic and attack test sets.
- **SC-005**: 100% of planted hidden-text and injection samples in the attack test set are flagged to the user.
- **SC-006**: A missing or rejected AI key is shown to the user on the first page they open, and no upload or edit is lost in any key, budget or provider failure scenario in the test set.
- **SC-007**: A single resume extraction costs under 0.05 USD on the default fast model.
- **SC-008**: Deleting all data leaves no profile, file, preference or AI log record behind (verified by inspection after deletion).
- **SC-009**: Across the synthetic test set, no email address or phone number from a resume appears in any text sent to the AI provider, and 100% of them still appear correctly in the review's contact section.

## Assumptions

- One person per install, running locally on their own computer; no sign-in, no hosting.
- The AI provider for this slice is OpenAI only; other providers come before the public release (architecture ADR-02). Model tier defaults are decided by the extraction cost/quality test in this feature (ADR-11).
- The AI key lives only in the local environment file; changing it needs a restart (ADR-09).
- The UI is dark only in this release, from the project palette; colours are theme variables so a light theme can be added later.
- Resume content may be in any language, but the evaluation set and quality targets are English.
- Preferences are stored now but only used by feature 002 (job search); weighting of roles, stack and location is defined there.
- All test and demo resumes are synthetic.

**Out of scope for this slice (later in 001 or after):** changing the model per tier in Settings, per-item accept/reject on re-upload diffs (this slice shows changes in a pre-filled review instead), career-ops import (`cv.md`, `profile.yml`, `voice-dna.md`), other AI providers, OCR for scanned PDFs, light theme, "Export all my data" (feature 003), and AI content suggestions on the profile (feature 005).
