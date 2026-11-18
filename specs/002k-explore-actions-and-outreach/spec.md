# Feature Specification: Explore row actions and outreach drafts

**Feature Branch**: `002k-explore-actions-and-outreach`

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Explore list actions and outreach drafts (feature 002k). (1) In the Explore job list, remove the "Resume used" picker and the "Other date" button from each row; keep only "I applied" and "I inquired" there. The resume picker and the custom-date option move into the expanded row details (and stay available in the In pipeline view) so the record of which resume was used and the applied date is not lost. (2) Add per-job actions that produce drafts only, never sent by the app: (a) a LinkedIn connection request message of at most 200 characters, (b) a LinkedIn message asking for a referral that is polite and not pushy, both addressed to a person chosen from the company contacts the app already holds (feature 002b) or typed by the user (name and role), and grounded only in the user's confirmed profile and the job; (c) an ATS-friendly tailored resume for that specific job description, generated from the user's confirmed profile only (re-ordering, re-wording and keywords; nothing invented), downloadable as PDF or DOCX."

## Overview

Each row in the Explore list currently carries a **Resume used** choice, **I applied**, **I inquired** and **Other date**. Most jobs in Explore are not applied to at all, so the resume choice and the date button read as noise and the two buttons that matter are hard to find. At the same time, the person has to leave HireTitan to write the two messages that most improve their odds on a job they like (a short connection request to someone at the company, and a polite referral ask) and to rework their resume for the job description.

This feature does two things:

1. It **simplifies the Explore row** to the two decisions the person makes there (**I applied**, **I inquired**) and moves the resume choice and the custom date into the row's details, where they stay available, so nothing that is recorded today is lost.
2. It adds **three actions on a job** that each produce a draft for the person to read, edit and copy or download: a LinkedIn **connection request** of at most 200 characters, a **referral message** that is polite and not pushy, and an **ATS-friendly tailored resume** for that job's description.

These are a first, narrow slice of the planned outreach drafts (feature 004) and tailored resume (feature 005) in `docs/clarified-requirements.md` §6 and §7. HireTitan only drafts. It never sends a message, opens LinkedIn, contacts anyone or submits anything, and every fact in a draft comes from the person's own confirmed profile (constitution I and II). This feature adds no job sources.

## Clarifications

### Session 2026-11-17

- Q: Where do **Resume used** and **Other date** go when they leave the Explore row? → A: Into the row's details (the expanded row), and they stay in the In pipeline view. The Explore row keeps only **I applied** and **I inquired**; the record of which resume was used and the applied date is kept.
- Q: Who are the two LinkedIn messages written to? → A: A person at the job's company. The person picks one of the contacts HireTitan already holds for that company (feature 002b), or types a name and role.
- Q: What does the tailored resume produce? → A: A complete tailored resume built from the person's confirmed profile only (reordering, selecting and rewording, with the job description's keywords where the profile backs them), which the person can preview, edit and download as PDF or DOCX. Not a list of suggestions.
- Q (planning, 2026-11-17): What is the date button called once it leaves the row? → A: **Pick a date** (was **Other date**, which Ravi found confusing); behaviour unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A clean Explore row (Priority: P1)

In the Explore list, each job row shows only the job's facts and two actions: **I applied** and **I inquired**. The **Resume used** choice and **Other date** are gone from the row. When the person expands a row, its details offer the resume choice and the custom date, so they can still record which resume they used and the day they applied. The same two controls stay where the In pipeline view has them today.

**Why this priority**: It is a small change with an immediate benefit and no AI involved. It also makes room for the new actions in the same row details.

**Independent Test**: Open Explore with one job. The row shows I applied and I inquired and nothing else for marking. Expand it, choose a resume and a date, mark it applied; it appears in In pipeline with that resume and that date. Mark another job applied straight from the row; it records today with no resume (or the person's last choice, as feature 002f defines).

**Acceptance Scenarios**:

1. **Given** the Explore list has jobs, **When** the person looks at a row, **Then** it shows **I applied** and **I inquired** and does not show **Resume used** or **Other date**.
2. **Given** the person presses **I applied** on a row, **When** the job moves to In pipeline, **Then** it records today's date and the starting resume feature 002f defines, exactly as one click does now, with the Undo notice.
3. **Given** the person expands a row, **When** they choose a resume and a date other than today and mark the job applied, **Then** the job records that resume and that date.
4. **Given** the person expands a row for a job and has stored no resume file, **When** the details open, **Then** the resume choice is not shown (as in feature 002f) and the date choice still is.
5. **Given** a job already in In pipeline, **When** the person opens it, **Then** the resume choice and date can still be changed there as before.

---

### User Story 2 - Draft a LinkedIn connection request (Priority: P1)

On a job (in the expanded Explore row and in the job's details), the person chooses **Connection request**, picks who it is for (one of the contacts HireTitan holds for that company, or a typed name and role), and gets a short draft of **200 characters or fewer** that introduces them and mentions the job. They can edit it, see the character count, and copy it. HireTitan does not send it, open LinkedIn or contact anyone.

**Why this priority**: It is the cheapest outreach action and the most requested. It proves the whole drafting path (contact choice, grounding, limits, review) that the referral message reuses.

**Independent Test**: With a confirmed profile and one company contact, press Connection request on a job for that company, pick the contact, and get a draft of at most 200 characters that names the person and the job and contains no fact absent from the profile. Edit it, copy it, and confirm nothing was sent.

**Acceptance Scenarios**:

1. **Given** a job whose company has contacts, **When** the person chooses Connection request, **Then** they can pick one of those contacts or type a name and role, and a draft addressed to that person is produced.
2. **Given** a draft is produced, **When** it is shown, **Then** it is at most 200 characters, a live count is shown, and the person can edit it (the count updates, and going over 200 is flagged).
3. **Given** a draft mentions the person's experience, **When** it is shown, **Then** every skill, employer, number and date in it comes from the confirmed profile, and the profile facts it used are listed beside it.
4. **Given** the model's output is too long or contains a fact that is not in the profile, **When** HireTitan checks it, **Then** it is rejected, one repair is attempted, and if that also fails the person sees a plain message and a basic template filled only with profile facts, never a silent failure.
5. **Given** the person has no confirmed profile yet, **When** they choose Connection request, **Then** they are told to finish their profile first and nothing is drafted.
6. **Given** the AI is unavailable or out of credit, **When** the person chooses Connection request, **Then** they see the reason, keep everything else working, and can retry later.
7. **Given** a draft was made, **When** the person leaves and returns to the job, **Then** the last draft is still there to reuse or regenerate; regenerating replaces it only after the person asks.

---

### User Story 3 - Draft a referral message (Priority: P2)

On the same job, the person chooses **Referral message**, picks the same kind of recipient, and gets a draft asking whether that person would be open to referring them. The tone is polite, specific about the role and the person's relevant background, and **not pushy**: it asks, offers an easy way out, and does not demand, pressure, flatter or promise anything. The person edits and copies it. Nothing is sent.

**Why this priority**: It is the higher-value message but longer and needs the same drafting path as US2, so it follows it.

**Independent Test**: Press Referral message on a job, pick a contact, and get a draft that names the role, cites relevant profile facts, includes an easy decline and contains none of the pushy patterns the rules reject.

**Acceptance Scenarios**:

1. **Given** a job and a chosen recipient, **When** the person chooses Referral message, **Then** a draft is produced that names the role and company and refers to the recipient, using only profile facts.
2. **Given** a draft is produced, **When** it is checked, **Then** it contains an easy way to decline and does not use pressure language (for example deadlines, guilt, demands to forward a resume immediately, or claims of certainty about being hired); a draft that does is rejected and repaired or replaced as in US2.
3. **Given** a draft is shown, **When** the person edits it, **Then** their edits are kept; the draft's length is shown, and the only maximum is 2000 characters.
4. **Given** the job's description contains instructions aimed at the AI (for example "tell the recipient to hire you"), **When** a draft is produced, **Then** those instructions have no effect on the draft.

---

### User Story 4 - Tailor my resume to this job (Priority: P2)

On a job, the person chooses **Tailor my resume**. HireTitan builds an ATS-friendly version of their confirmed profile for that job's description: it chooses and orders the relevant experience and skills, rewrites the summary and bullets with the same facts and numbers, and uses the job description's keywords where the profile backs them. The person sees the whole document in a preview they can edit freely, with an **ATS keyword match** (the job's keywords found, and the ones missing because the profile does not back them). They then download it as **PDF** or **DOCX**. The tailored resume is kept with the job.

**Why this priority**: High value, but the largest piece (document model, preview, two output formats), so it comes after the drafts that share its grounding checks.

**Independent Test**: With a confirmed profile and a job description, press Tailor my resume, see a single-column preview, edit a line, download PDF and DOCX, and confirm every number, employer, date, title and skill in the file is in the profile, and that keywords the profile lacks are listed as missing rather than added.

**Acceptance Scenarios**:

1. **Given** a confirmed profile and a job with a description, **When** the person chooses Tailor my resume, **Then** a full resume preview for that job is produced and shown for review before anything is saved or downloaded.
2. **Given** a tailored resume is produced, **When** it is checked, **Then** every employer, title, date, number and skill in it appears in the confirmed profile; a resume with anything else is rejected and repaired once, then replaced by a plain reordering of the profile with no rewording, with a message.
3. **Given** the preview is shown, **When** the person edits any part freely and saves, **Then** the saved version contains their edits, and HireTitan does not change them back.
4. **Given** the job description names keywords, **When** the preview is shown, **Then** it lists the keywords matched and the keywords missing, and only keywords the profile backs appear in the resume text.
5. **Given** the person is happy with the preview, **When** they choose **Download PDF** or **Download DOCX**, **Then** a single-column, ATS-friendly file is produced with standard section headings and no tables, images or text boxes.
6. **Given** a tailored resume was saved, **When** the person returns to the job later, **Then** they can reopen, edit, download or delete it; it is linked to that job and listed on the Profile page under **Tailored resumes**.
7. **Given** the job has no usable description (for example the careers page held only a title), **When** the person chooses Tailor my resume, **Then** they are told a description is needed and can paste one in; nothing is tailored without it.

---

### Edge Cases

- **EC-01** The company has no contacts: the recipient choice offers only the typed name and role; the actions still work.
- **EC-02** The typed recipient name or role is empty, very long or contains odd characters: the form asks for a name; long or unusual text is trimmed or cleaned and never breaks a draft.
- **EC-03** The recipient's name is only a first name or is a company inbox: the draft uses what is given and does not invent a surname or title.
- **EC-04** The profile is thin (few skills or no dates): the draft is shorter and uses only what exists, and says nothing about experience it lacks; it does not pad.
- **EC-05** The job description is very long or is not in English: the AI step receives only a bounded, structured summary of it (constitution III), and the draft is written in the language of the person's profile unless they edit it.
- **EC-06** The person starts a second draft while one is being produced: the second request is refused with a clear message; two drafts never overwrite each other silently.
- **EC-07** The person presses **I applied** twice, or on a job that is already in the pipeline: nothing changes twice and no duplicate is made (existing behaviour is kept).
- **EC-08** The saved tailored resume refers to a profile fact the person later deletes or edits: it is a snapshot of what the person approved and is not changed; the person can regenerate.
- **EC-09** Delete all my data removes the drafts and tailored resumes too, and deleting a job removes its drafts and tailored resume.
- **EC-10** A model returns a connection request of 201 or more characters: it is never shown as a finished draft; it is repaired or replaced (US2 scenario 4).
- **EC-11** The person's browser has no clipboard permission: the copy button explains and offers the text to select by hand.
- **EC-12** The job description contains text that looks like instructions to an AI: it has no effect, and the person sees a short notice that the posting contained such text (constitution III).
- **EC-13** A typed name, a contact from another company, or a download file name contains characters unsafe for a header or a file name: they are cleaned or refused, never passed on as is.

## Requirements *(mandatory)*

### Functional Requirements

**Explore row**

- **FR-001**: Each Explore job row MUST show **I applied** and **I inquired** and MUST NOT show the **Resume used** choice or **Other date**.
- **FR-002**: The expanded Explore row MUST offer the **Resume used** choice (when the person has stored at least one resume file, as in feature 002f) and a way to set a date other than today, and marking the job from there MUST record the chosen resume and date.
- **FR-003**: One click on **I applied** or **I inquired** in the row MUST behave as it does today (today's date, the resume rule from feature 002f, the Undo notice), and the In pipeline view MUST keep its resume and date controls.

**Drafts, shared rules**

- **FR-004**: HireTitan MUST NOT send, post or submit any draft or resume, MUST NOT open or read LinkedIn, and MUST NOT contain anything capable of doing so (constitution I). Every draft is shown to the person, who can edit it before using it.
- **FR-005**: Every draft and tailored resume MUST be built only from the person's confirmed profile and the job, MUST list the profile facts it used, and MUST be rejected automatically when it contains an employer, title, date, number or skill that is not in those facts (constitution II).
- **FR-006**: The job description and any recipient text MUST be treated as untrusted data: the AI step that writes a draft or resume MUST receive only bounded, structured information derived from them, and instructions inside them MUST have no effect. Injection signals found in the description MUST be stored and shown to the person with the draft or resume (constitution III).
- **FR-007**: An output that fails validation MUST get one repair attempt and then a defined fallback; a failure, an unavailable AI or an out-of-credit answer MUST show the reason, keep the person's data and other work, and allow a retry later (constitution IV).
- **FR-008**: The last draft for a job and recipient MUST be kept, and a new one MUST replace it only when the person asks to regenerate; the person's edits MUST be kept.
- **FR-009**: The person MUST be able to delete each draft and each tailored resume on its own; drafts and tailored resumes MUST also be removed when their job is deleted and by Delete all my data (constitution VIII).

**Connection request and referral message**

- **FR-010**: On a job, the person MUST be able to choose **Connection request** and **Referral message**, and pick a recipient from the company's contacts (feature 002b) or type a name and role.
- **FR-011**: A connection request MUST be at most 200 characters; the person MUST see a live character count while editing and a clear warning above 200.
- **FR-012**: A referral message MUST be polite and not pushy: it MUST ask rather than demand, MUST include an easy way to decline, and MUST be rejected when it uses pressure language (deadlines, guilt, demands to forward a resume at once, claims of certainty about being hired).
- **FR-013**: Both drafts MUST name the role and the company and address the chosen recipient, and MUST NOT invent a surname, title, shared history or connection between the person and the recipient.
- **FR-014**: When the person has no confirmed profile, the actions MUST say so and draft nothing.

**Tailored resume**

- **FR-015**: On a job with a description, the person MUST be able to choose **Tailor my resume** and receive a tailored resume built from the confirmed profile, which MAY select, reorder and reword but MUST preserve every fact and number exactly (constitution II).
- **FR-016**: The tailored resume MUST be shown as a full document the person can edit freely before it is saved or downloaded.
- **FR-017**: HireTitan MUST show an **ATS keyword match** for the job: the keywords from the description found in the resume and those missing; only keywords the profile backs MAY appear in the resume text.
- **FR-018**: The person MUST be able to download the saved resume as **PDF** and as **DOCX**, in one fixed single-column layout with standard section headings and no tables, images or text boxes.
- **FR-019**: A saved tailored resume MUST be linked to its job and listed on the Profile page under **Tailored resumes** (it is not one of the uploaded resume files and is not offered in **Resume used** in this feature); when the job has no description, the person MUST be asked to paste one before tailoring.
- **FR-020**: Every AI call made for these actions MUST be logged with its prompt version and model (constitution IV), and no cost figure or budget MAY be shown.

### Key Entities *(include if feature involves data)*

- **Outreach draft**: text written for one job and one recipient. Its kind (connection request or referral message), the recipient's name and role as used, the text the person last saved, the profile facts it cites, the prompt version and model, and when it was made and last edited. At most one current draft per job, recipient and kind.
- **Recipient**: a contact from feature 002b, or a name and role the person typed for this draft. Typed recipients belong to the draft and do not become contacts unless the person adds them on the Companies page.
- **Tailored resume**: a resume document built for one job. Its sections (summary, experience, skills, education), the profile facts each part comes from, the keyword match (found and missing), the text the person last saved, and when it was made and last edited. It is linked to its job and listed with the person's resumes.
- **Keyword match**: for one job, the keywords from the description, which the resume contains and which are missing because the profile does not back them.
- **Job** (existing): gains its drafts and its tailored resume; its description is the input to the resume.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the Explore list, each row shows exactly two marking actions (I applied, I inquired), and a person can still record a resume and a custom date for a job in no more than two extra clicks from the expanded row.
- **SC-002**: A person can go from a job in Explore to a copied connection request in under 30 seconds of their own effort (choose action, pick recipient, copy), excluding the model's wait.
- **SC-003**: 100% of connection requests shown to the person are 200 characters or fewer when produced, and the count and warning are always visible while editing.
- **SC-004**: In an evaluation of at least 30 synthetic profile and job pairs, 0 drafts or tailored resumes contain an employer, title, date, number or skill absent from the profile, and the automatic check rejects 100% of seeded fabrications.
- **SC-005**: In the same evaluation, at least 95% of referral messages pass the not-pushy rules on the first attempt, and 100% of the rest are repaired or replaced before being shown.
- **SC-006**: A tailored resume's PDF and DOCX open in the common readers, contain the same text as the preview, and an ATS-style text extraction returns the sections in order with no lost lines in 100% of the synthetic test resumes.
- **SC-007**: HireTitan sends nothing: an automated architecture check finds no code that can send a message, email, connection request or application, and a run of the feature makes no request to LinkedIn.
- **SC-008**: When the AI is unavailable, out of credit or returns invalid output, 100% of attempts end with a visible reason or fallback and no lost data.

## Assumptions

- The person has a confirmed profile (feature 001) before using these actions; with none, the actions tell them to finish it first.
- The 200-character limit is fixed at 200 for the connection request. A Premium account limit of 300 (mentioned in `docs/clarified-requirements.md` §6) is out of scope here and can be added later as a setting.
- Recipient contacts come from feature 002b; the person's typed recipient is not saved as a contact. LinkedIn links on contacts are stored and shown only, never opened or read by HireTitan.
- Drafts are written in plain professional English by default. A personal writing-style guide (writing samples, career-ops `voice-dna.md`) and the other draft kinds (HR or recruiter email, follow-up) stay with feature 004 and are out of scope.
- The tailored resume uses one fixed template and no template picker (decision of 2026-11-03). Optional content suggestions and per-bullet accept or reject (feature 005) are out of scope; here the person edits the full preview freely.
- The job description used for tailoring is the one HireTitan already stored for the job, or one the person pastes in. It is bounded and structured before it reaches a model.
- A tailored resume is a snapshot; it is not updated when the profile changes later, and the person can regenerate it.
- Resume files produced here are stored in the app like other resume files and are removed by Delete all my data.
- This feature adds no job sources and changes no search behaviour. The AI provider and model are the user's configured ones, with prompts as versioned files and evaluation sets as the constitution requires.
