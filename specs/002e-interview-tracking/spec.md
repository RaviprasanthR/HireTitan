# Feature Specification: Interview tracking

**Feature Branch**: `002e-interview-tracking`

**Created**: 2026-11-12

**Status**: Draft

**Input**: User description: "In the In pipeline tab, each applied or inquired job gets an expandable detail panel (and the same panel on the job's own page) holding: point of contact (name, role, email/phone/LinkedIn optional); how the job came: direct from the company, or through a hiring firm (firm name); and interview rounds. A job can have multiple rounds (round 1, 2, 3...), each with a type (screening, technical, HR, managerial, other), date/time, interviewer(s), a state (Scheduled, Cleared, Failed; Failed ends the process), a feedback/review note from the interviewer, and a list of questions and answers asked in that round. The Status column of the In pipeline table shows the latest round's state, e.g. 'Round 2 scheduled', 'Round 1 cleared', 'Failed'; with no rounds it keeps showing Applied or Inquired. Data is stored as structured fields so it can be queried for analytics later (no charts or stats page in this feature). All data is the user's own, never sent to AI and never sent anywhere (no messages sent). Delete all my data removes it. Follow constitution 2.0.0 (no cost shown) and the existing 002d UI style."

Builds on feature 002d (`specs/002d-navigation-and-pipeline/`): the In pipeline tab, the applied and inquired marks, and the job page. Decided with Ravi on 2026-11-12: a new feature on its own branch cut from 002d; the Status column shows the latest round's state; the details live in an expandable row and on the job's page; the data is kept as structured fields for later analytics, with no charts in this feature. HireTitan still never sends a message, email or application.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record who I deal with and how the job came (Priority: P1)

The person opens a row in In pipeline (or the job's own page) and records the point of contact for that application: a name, and optionally their role, email, phone and LinkedIn link. They also record how the job came to them: **direct** from the company, or **through a hiring firm**, with the firm's name.

**Why this priority**: knowing who to talk to and whether a recruiter sits in between is the first thing the person needs when a call comes in, and it is the simplest useful slice.

**Independent Test**: Open an applied job's row, add a contact with only a name, choose "Through a hiring firm" and type a firm name, save; reload; the row shows the contact and the firm. Change it to "Direct"; the firm name is no longer shown.

**Acceptance Scenarios**:

1. **Given** an applied or inquired job, **When** the person expands its row in In pipeline, **Then** a detail panel opens with the point of contact, the source (direct or hiring firm) and the interview rounds.
2. **Given** the detail panel, **When** the person saves a contact with only a name, **Then** it is kept; role, email, phone and LinkedIn are optional.
3. **Given** a contact email or LinkedIn link that is not well formed, **When** the person saves, **Then** that field is refused with a message saying what is wrong, and nothing else typed is lost.
4. **Given** the source set to **Through a hiring firm**, **When** the person saves without a firm name, **Then** it is refused; with a firm name it is kept and shown in the row.
5. **Given** the same job, **When** the person opens the job's own page, **Then** the same details are shown and can be edited there.

---

### User Story 2 - Track interview rounds and see where I stand (Priority: P1)

For each application the person adds interview rounds in order (Round 1, Round 2, ...). Each round has a type (screening, technical, HR, managerial or other), a date and time, the interviewer names, and a state: **Scheduled**, **Cleared** or **Failed**. The Status column of the In pipeline table shows the latest round, for example "Round 2 scheduled", "Round 1 cleared" or "Failed in round 3"; a job without rounds still shows Applied or Inquired.

**Why this priority**: the person has several rounds per role and wants to see at a glance where each application stands; this is the core of the request.

**Independent Test**: On an applied job add Round 1 (technical); the status reads "Round 1 scheduled". Mark it cleared and add Round 2; the status reads "Round 2 scheduled". Mark Round 2 failed; the status reads "Failed in round 2" and no further round can be added.

**Acceptance Scenarios**:

1. **Given** a job in the pipeline with no rounds, **When** the person adds a round, **Then** it is numbered Round 1, starts as Scheduled, and the Status column reads "Round 1 scheduled".
2. **Given** Round 1 is cleared, **When** the person adds a round, **Then** it is numbered Round 2 and the status reads "Round 2 scheduled".
3. **Given** a round is still Scheduled, **When** the person adds the next round, **Then** it is allowed and numbered after it (rounds are numbered in the order added, not by outcome).
4. **Given** any round is marked **Failed**, **Then** the Status column reads "Failed in round N", no new round can be added, and the person can still edit notes and questions on every round.
5. **Given** a round marked Failed by mistake, **When** the person changes it back to Scheduled or Cleared, **Then** adding rounds is allowed again and the status follows the latest round.
6. **Given** the person deletes the latest round, **Then** the status follows the round before it, or Applied or Inquired when none is left; the remaining rounds keep their numbers.
7. **Given** an inquired job (not yet applied), **When** the person adds a round, **Then** it is allowed (some recruiters screen before an application), and the status shows the round.
8. **Given** a round's date and time, **Then** it is shown in the person's local time; a past date on a Scheduled round is allowed (the person may update late).

---

### User Story 3 - Keep the questions, answers and feedback from each round (Priority: P2)

On each round the person writes down the questions they were asked and the answers they gave, as a list of question-and-answer pairs, and a feedback note: what the interviewer said, or what they themselves thought of it.

**Why this priority**: this is what the person will want to look back on before the next interview and analyse later, but tracking rounds is useful on its own first.

**Independent Test**: On Round 1 add three question-and-answer pairs and a feedback note; reload; all three pairs show in the order added with the note; edit the second answer and delete the third; the change is kept.

**Acceptance Scenarios**:

1. **Given** a round, **When** the person adds a question with or without an answer, **Then** it is kept in the order added; the answer can be filled in later.
2. **Given** several questions, **When** the person edits or deletes one, **Then** the others are unchanged.
3. **Given** a round, **When** the person writes a feedback note, **Then** it is kept with that round and shown when the round is opened.
4. **Given** a long answer or note (several paragraphs), **Then** it is kept in full and its line breaks are kept.

---

### User Story 4 - The data stays mine and can be queried later (Priority: P2)

Everything recorded here is the person's own: it is never sent to the AI, never sent anywhere, and removed by **Delete all my data**. It is kept as separate fields (round number, type, date, state, interviewers, each question and answer, the source type and firm), so a later feature can count, for example, how far applications got or how hiring-firm roles compare with direct ones.

**Why this priority**: privacy is binding (constitution) and the structured form is what makes later analytics possible; it shapes the data more than the screens.

**Independent Test**: Record a contact, a hiring firm, two rounds and questions on a job; run Delete all my data; none of it remains. Separately, check that no AI request or outgoing message carries any of it.

**Acceptance Scenarios**:

1. **Given** recorded contacts, rounds, questions and notes, **When** the person runs Delete all my data, **Then** none of it remains.
2. **Given** any AI task (search judging, profile reading), **Then** no contact, round, question, answer or note is part of what is sent to the AI.
3. **Given** the person deletes a job, **Then** its details are removed with it.
4. **Given** the person undoes Applied or Inquired on a job that has details, **Then** the details are kept, stay visible read-only on the job's own page, and become editable again when the job is marked again.

---

### Edge Cases

- A job is merged with its duplicate and both have details: the job that stays keeps its own details; the other job's contact, source and rounds are added only where the staying job has none (no silent overwrite).
- A round with no date yet: allowed; it shows "date not set".
- The person adds a round to a job that is no longer in the pipeline (undo happened in another tab): refused with a message; the details already there stay.
- Two rounds on the same day: allowed; order is by round number.
- A hiring firm later hands over to the company directly: the person edits the source; only the current value is kept.
- Very many questions on one round (dozens): all are kept and shown; the panel scrolls.
- The person collapses a row with unsaved edits: they are warned before the edits are dropped.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Each job in the pipeline (applied or inquired) MUST have an expandable detail panel in the In pipeline table and the same panel on the job's own page.
- **FR-002**: The person MUST be able to record one point of contact per job: name (required), role, email, phone and LinkedIn link (each optional); email and LinkedIn MUST be checked for form when given.
- **FR-003**: The person MUST be able to record the job's source as **Direct** or **Through a hiring firm**, or leave it not set; a hiring firm MUST have a name.
- **FR-004**: The person MUST be able to add, edit and delete interview rounds per job; rounds MUST be numbered 1, 2, 3 ... in the order added, and numbers MUST NOT change when another round is deleted.
- **FR-005**: Each round MUST have a type (screening, technical, HR, managerial, other), an optional date and time, optional interviewer names, a state (Scheduled, Cleared, Failed; a new round starts Scheduled) and an optional feedback note.
- **FR-006**: While any round of a job is Failed, adding a new round to that job MUST be refused; editing existing rounds MUST stay possible.
- **FR-007**: The Status column of In pipeline MUST show the latest round as "Round N scheduled" or "Round N cleared", and Applied or Inquired when the job has no rounds. If any round is Failed, the status MUST be "Failed in round N" (N = the highest failed round), whatever later rounds exist. Each state MUST have its own colour in the 002d style and meet the theme's contrast level.
- **FR-008**: Each round MUST hold an ordered list of question-and-answer pairs; the person MUST be able to add, edit and delete each pair; an answer MAY be empty.
- **FR-009**: Contacts, sources, rounds, questions, answers and notes MUST be stored as separate structured fields (not one free-text blob), so they can be queried later.
- **FR-010**: None of this data MAY be sent to the AI or to any outside service; HireTitan MUST NOT send any message, email or invitation to a contact.
- **FR-011**: Delete all my data MUST remove all of it; deleting a job MUST remove its details; undoing Applied or Inquired MUST keep them.
- **FR-012**: A duplicate merge MUST keep the staying job's details and add the other job's details only where the staying job has none.
- **FR-013**: Each section (contact, source, each round, each question) MUST be saved by an explicit action with a visible saved or error message; collapsing a row with unsaved edits MUST warn first.
- **FR-014**: Text fields MUST accept long text (several paragraphs) with line breaks kept; any length limit MUST be shown before saving.
- **FR-015**: No screen in this feature MAY show an AI cost, spend or budget (constitution 2.0.0).

### Key Entities *(include if feature involves data)*

- **Pipeline contact**: the person the user deals with for one application. Name; optional role, email, phone, LinkedIn link. At most one per job.
- **Job source**: how the job came: direct, or through a hiring firm with the firm's name. At most one per job.
- **Interview round**: one interview step of one job. Round number, type, date and time, interviewer names, state, feedback note.
- **Interview question**: one question asked in a round and the answer given, in order. Belongs to one round.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The person can record a contact, a source and a first round for a job in under 1 minute, from the In pipeline tab, without leaving Home.
- **SC-002**: For 100% of jobs in the test set the Status column matches the latest round's state, or Applied or Inquired when there are no rounds.
- **SC-003**: 0 pieces of contact, round, question, answer or note data appear in any AI request or outgoing request, checked by a test.
- **SC-004**: After Delete all my data, 0 contacts, sources, rounds, questions or notes remain.
- **SC-005**: Every recorded item can be listed by field (for example all rounds of type technical with state Failed) without reading free text, checked by a test over the stored data.
- **SC-006**: Undoing Applied or Inquired and marking again loses 0 details in the test set.

## Assumptions

- One point of contact per job is enough for now; several contacts per job is a later change. This contact is separate from the company contacts of feature 002b (those are the person's network at a company; this is the contact for one application).
- The hiring firm is a free-text name per job, not a shared list of firms.
- Round types are a fixed list (screening, technical, HR, managerial, other); "other" covers anything else.
- No calendar sync, reminders or notifications: HireTitan never sends anything, and reminders are out of scope.
- No charts or statistics page in this feature; analytics is a later feature that reads the structured data.
- An offer or a final "hired" state is out of scope; the person records the last round as cleared.
- Details are added only to jobs in the pipeline; Explore jobs have no detail panel in the list. A job that left the pipeline (Undo) keeps its details, shown read-only on its own page.
- English only, like the rest of HireTitan.
