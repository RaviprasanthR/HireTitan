# Feature Specification: Resume picker

**Feature Branch**: `002f-resume-picker`

**Created**: 2026-11-15

**Status**: Draft

**Input**: User description: "002f resume picker: when a person marks a pipeline job as applied (or inquired), they can pick which of their stored resume files they used, and the In pipeline list and the job's details show that resume. Today nothing records which resume was used. It overlaps feature 005 (tailored resume), so keep 002f to choosing and showing an existing stored resume file only: HireTitan never generates, sends or uploads anything. Resume files already live in the app (Profile page, resume files list). The resume is optional."

## Overview

A person who is job hunting keeps more than one version of their resume: one for backend roles, one for a lead role, an older one. Months later, when a recruiter calls, they cannot tell which version a company received. HireTitan already stores the resume files the person uploaded, but a job in the pipeline records nothing about them.

This feature lets the person say which stored resume file they used for a job, when they mark it applied or inquired or any time later, and shows that resume wherever the pipeline job is shown. It is a label the person sets. HireTitan does not attach, send, generate or change any resume (those are features 004 and 005, and the constitution forbids sending).

## Clarifications

### Session 2026-11-15

- Q: Should the resume be picked before pressing I applied (a choice beside the date), or only afterwards in the edit card? → A: Both. An optional **Resume used** choice sits beside the date, and the edit card sets or changes it later; leaving it alone keeps I applied one click.
- Q: When a resume file is removed from the profile, should jobs that used it forget it completely or keep its name as a note? → A: Keep the name as a note. The job shows the name marked as removed (plain text, no link to a file); the person can clear that note from the job's edit card, and removing the job or deleting all data removes it too.
- Q: When marking a job applied, should Resume used start empty or on a resume chosen for the person? → A: It starts on the person's own last choice when marking a job (None the first time, or when that resume has been removed). No other automatic pick is allowed, and later edit-card changes do not change the starting value.
- Q: Should clicking the resume name in the pipeline open or download the stored file? → A: No. The pipeline shows the name and the day it was added only; nothing new reads stored files back.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Say which resume I used when I apply (Priority: P1)

When the person marks a job as applied or inquired, the control where they can already adjust the date also offers a **Resume used** choice. The choice lists the resume files the person has stored, each shown by its name and the day it was added, plus **None**. It starts on whatever the person chose the last time they marked a job (a resume, or None), so repeating the same resume costs no extra step; the very first time, it starts on None. The choice is always visible, so it is clear what will be recorded, and the person can change it or set it to None before marking. The choice is optional: a person who never picks a resume sees it stay on None and marking a job works exactly as it does today.

**Why this priority**: This is the whole point of the feature: capturing the fact at the moment it is fresh. Without it nothing else has data to show.

**Independent Test**: Store two resume files, mark an Explore job as applied while choosing the second one; the job appears in In pipeline with that resume. Mark another job applied without choosing; it appears with no resume and nothing else changes.

**Acceptance Scenarios**:

1. **Given** the person has stored two resume files, **When** they mark a job as applied and choose one of them, **Then** the job moves to In pipeline as Applied and records that resume.
2. **Given** the person marks a job as inquired and chooses a resume, **When** they later press **I applied** on that job, **Then** the chosen resume is kept unless they choose a different one.
3. **Given** the person has never chosen a resume, **When** they mark a job as applied without touching **Resume used**, **Then** it has no resume and behaves as before this feature.
4. **Given** the person's last marked job used a resume, **When** they mark another job, **Then** **Resume used** starts on that same resume, and recording it takes no extra step; **When** they change it to another resume or to None before marking, **Then** the job records their change and the next job starts on it.
5. **Given** the resume the person last chose has since been removed, **When** they mark a job, **Then** **Resume used** starts on None.
6. **Given** the person has stored no resume file (for example they typed their profile in), **When** they mark a job as applied, **Then** the **Resume used** choice is not shown, and marking the job works as before.
7. **Given** a job was marked applied and the Undo notice is shown, **When** the person presses Undo, **Then** the job returns to Explore and its resume choice is forgotten.

---

### User Story 2 - See the resume in the pipeline (Priority: P1)

The In pipeline list has a **Resume** column showing the name of the resume used for each job, or a dash when none was chosen. The job's details (the expanded row and the job's own page) show the same resume, with the day it was added to HireTitan.

**Why this priority**: Recording a choice is only useful if the person can see it again when a recruiter calls.

**Independent Test**: With one job that has a resume and one without, open In pipeline: the first shows the name, the second a dash; expand the first and see the name and its added date.

**Acceptance Scenarios**:

1. **Given** a pipeline job with a resume, **When** the person opens In pipeline, **Then** the Resume column shows that resume's name.
2. **Given** a pipeline job without a resume, **When** the person opens In pipeline, **Then** the Resume column shows a dash.
3. **Given** a pipeline job with a resume, **When** the person expands its row or opens the job's page, **Then** the details show the resume name and the day it was added.
4. **Given** a long resume name, **When** it is shown in the list, **Then** it is shortened to fit and the full name is available on hover or in the details.

---

### User Story 3 - Change or clear the resume later (Priority: P2)

In a pipeline job's edit card (the pencil), the person can set, change or clear the **Resume used** choice at any time, including for jobs that were marked applied before this feature existed. The change is saved with the rest of the job's details and is covered by the same "unsaved changes" protection as the contact and interview notes.

**Why this priority**: People forget to choose at the moment of applying, and every existing pipeline job starts with no resume.

**Independent Test**: Open the edit card of an applied job with no resume, choose one, save, and see it in the list; change it to another; clear it back to None.

**Acceptance Scenarios**:

1. **Given** an applied job with no resume, **When** the person chooses a resume in the edit card and saves, **Then** the job shows that resume in the list and details.
2. **Given** a job with a resume, **When** the person chooses a different one or None and saves, **Then** the list and details show the new value.
3. **Given** the person changed the choice but has not saved, **When** they try to close the card, **Then** they are asked first, as for other unsaved edits.
4. **Given** jobs marked applied before this feature, **When** the person opens In pipeline, **Then** they show a dash in the Resume column and lose nothing.

---

### User Story 4 - Resume files that go away, jobs that merge or are removed (Priority: P3)

The resume choice stays consistent when other things change. If the person removes a resume file from their profile, the jobs that used it keep the file's name as a plain note marked as removed, which they can clear. If two duplicate jobs are merged, the kept job keeps its own resume and takes the other job's resume only when it has none. Removing a job, or all data, removes its resume choice with it.

**Why this priority**: These are the edge paths that keep the data trustworthy and keep the promise that a person can delete their data completely.

**Independent Test**: Choose a resume on two jobs, remove that resume file from Profile; both jobs show its name marked as removed, the removal confirmation said how many jobs it was used on, and clearing the note on one job leaves no trace of the resume there.

**Acceptance Scenarios**:

1. **Given** a resume file chosen on two pipeline jobs, **When** the person removes that file, **Then** the confirmation tells them it is used on two jobs and that they will keep its name as a note, and after confirming both jobs show the name marked as removed.
2. **Given** a job showing a removed-resume note, **When** the person clears it in the edit card and saves, **Then** the job shows a dash and nothing about that resume remains on it.
3. **Given** two duplicate jobs where only the other one has a resume, **When** they are merged, **Then** the kept job shows that resume; **When** both have one, **Then** the kept job keeps its own.
4. **Given** a job with a resume or a removed-resume note, **When** the job is removed, **Then** nothing about the choice remains.
5. **Given** the person deletes all their data, **When** it completes, **Then** no resume choice or removed-resume note remains anywhere.
6. **Given** a resume file chosen on two pipeline jobs, **When** the person removes it with **also clear the name from those jobs** ticked, **Then** both jobs show a dash and nothing of that file remains anywhere.

---

### Edge Cases

- The person uploads a second copy of the same file: both appear in the choice by name and added date, so they can tell them apart.
- A resume file is still being read (profile extraction not finished), or its reading failed: it is offered, since the person uploaded it as a resume. Only a file rejected as "not a resume" is not offered.
- The person has many resume files: the choice remains usable (scrolls) and shows the newest first.
- A resume file is removed while the edit card is open with it chosen: saving that card does not bring the removed file back; the choice becomes the removed-resume note and the person sees a message.
- A saved choice refers to a file removed in another browser tab: the next view shows the removed-resume note and no error.
- A removed-resume note cannot be picked again as a choice; only stored files are offered.
- Two quick changes in a row: the last one the person saved wins, and neither is lost or shown wrongly.
- A job that never became a pipeline job (still in Explore) has no resume choice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Beside the date, where the person marks a job as applied or inquired, the system MUST offer an optional **Resume used** choice listing the person's stored resume files by name and the day each was added (newest first), plus **None**. The choice starts on the resume used for the last marked job (None the first time, and None when that resume has been removed), except for a job that already has a resume (FR-003), and leaving it alone keeps marking a job a single action.
- **FR-002**: Marking a job applied or inquired without choosing a resume MUST work exactly as before this feature.
- **FR-003**: The system MUST record the chosen resume file on the pipeline job and MUST keep it when the job changes from inquired to applied, unless the person chooses another. For a job that already has a resume, the **Resume used** choice MUST start on that job's own resume, not on the last choice.
- **FR-004**: The In pipeline list MUST show a **Resume** column with the chosen resume's name, or a dash when none; a long name MUST be shortened with the full name available on hover.
- **FR-005**: A pipeline job's details (expanded row and the job's page) MUST show the chosen resume's name and the day it was added.
- **FR-006**: The person MUST be able to set, change or clear the resume on any pipeline job from its edit card, including jobs marked before this feature existed; such jobs MUST show no resume until chosen.
- **FR-007**: Unsaved resume changes in the edit card MUST be covered by the same unsaved-changes protection as the other edit-card fields.
- **FR-008**: Undoing an applied or inquired mark MUST also forget the resume choice for that job.
- **FR-009**: Removing a resume file MUST, by default, leave every job that used it showing the file's name as a plain note marked as removed (with no link to any file). The removal confirmation MUST say how many jobs it is used on and MUST offer an option, off by default, to **also clear the name from those jobs**, so the file can be removed completely in one action (constitution principle VIII). The person MUST also be able to clear a note on each job from its edit card.
- **FR-010**: Merging duplicate jobs MUST keep the kept job's resume and take the other job's resume only when the kept job has none.
- **FR-011**: Removing a job, and deleting all data, MUST remove the resume choice, and any removed-resume note, with it.
- **FR-012**: Only resume files stored as resumes MUST be offered; files rejected as "not a resume" MUST NOT be.
- **FR-013**: The resume choice, the resume's name and its content MUST NOT be sent to any AI model by any workflow, and the feature MUST NOT send, attach, upload, generate or change any resume or any message (constitution principle I).
- **FR-014**: The choice is a record the person sets. The only starting value the system MAY use is the person's own last choice when marking a job (FR-001); it MUST NOT guess, rank or pick a resume by any other rule (newest, best match, most used). Changes made later in the edit card MUST NOT change the starting value.

### Key Entities *(include if feature involves data)*

- **Resume file**: a resume the person uploaded earlier (existing). Has a name and the day it was added; it may be removed by the person.
- **Resume used**: an optional link from one pipeline job (applied or inquired) to one resume file, set by the person. A job has at most one; a resume file can be linked from many jobs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with two stored resumes can mark a job applied and record which one they used in no more than one extra step (choosing from the list), and marking without a resume takes the same number of steps as today.
- **SC-002**: For every pipeline job with a resume, the In pipeline list shows its name without opening the job, and the details show it with the added date, in 100% of the acceptance tests.
- **SC-003**: A person can set, change or clear the resume of any existing pipeline job in under 30 seconds from the list.
- **SC-004**: After a resume file is removed, 0 jobs fail to load or offer it as a choice, every job that used it shows its name marked as removed (or a dash when the person chose to clear the names), the removal confirmation states the number of jobs affected correctly, and clearing the note leaves nothing of the resume on the job.
- **SC-005**: 0 resume names or choices reach an AI model in the recorded-call privacy test, and 0 resume data remains after Delete all.
- **SC-006**: Existing pipeline jobs and the one-click applied and inquired marks behave identically to before in all existing tests.

## Assumptions

- Only the resume files already stored in HireTitan can be chosen; this feature adds no way to upload, create, tailor or attach resumes (features 004 and 005).
- The Resume used choice is a record for the person's own reference. HireTitan reads nothing from, and sends nothing to, any site or recruiter.
- The choice starts on the person's last choice when marking a job (Ravi's choice, 2026-11-15), not on a resume HireTitan picks. Because the choice is visible beside the date at the moment of marking, a stale value is easy to see and change. The remembered choice is a small local setting: it is cleared by Delete all, and reset to None when its resume file is removed.
- When a resume file is removed, jobs keep its name as a plain note (Ravi's choice, 2026-11-15) so the person still remembers which version they sent. Complete removal stays available, as constitution principle VIII requires: the removal confirmation offers "also clear the name from those jobs" (off by default), and each note can be cleared per job. The note never links to the removed file or its content, and goes with the job or with Delete all.
- A person who has no stored resume file (profile typed in by hand) simply does not see the choice; their pipeline works as before.
- Opening or downloading the stored file from the pipeline is out of scope; the name and the added day are shown.
- One resume per job; several resumes per job, resume notes and a history of changes are out of scope.
- The feature builds on the pipeline, edit card and interview-detail storage from features 002d and 002e, and on the resume files list from feature 001.
