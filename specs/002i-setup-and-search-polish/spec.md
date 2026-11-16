# Feature Specification: Setup and search polish

**Feature Branch**: `002i-setup-and-search-polish`

**Created**: 2026-11-16

**Status**: Draft

**Input**: User description (extended the same day with US5 and US6, see Clarifications): "Four user-facing improvements to HireTitan's first-run setup and search experience, from Ravi's feedback on 2026-11-16. (1) Auto-approve the first search rules when setup completes, so Explore is ready to search at once; later changes still need approval; fix the 'Finish setup first' dead end. (2) Redesign the Search rules page in plain language: no 'Skips jobs' / 'Guides the AI' badges or origin tags. (3) The Preferences step of first-run setup is long and cramped; use the available width. (4) Explore's search progress shows '0 of 0' at the start and batch numbers; show a clear searching state from the first second and less internal detail."

## Background

Ravi deleted his data, went through first-run setup again (name, resume, profile review, preferences) and landed on Explore with "No jobs yet. Finish setup first." Nothing on screen said what was missing. The missing step was approving the search rules, which lives under Profile > Search rules and is not part of the setup cards. When he found the page, its badges ("Skips jobs", "Guides the AI", "Similar title", "From your profile") and its draft-then-approve flow were hard to follow. When he started a search, the panel said "Batch 1 of 1" and "0 of 0 companies read" for the first seconds, so it looked as if nothing was found and nothing was happening.

## Clarifications

### Session 2026-11-16

- Q: Should the first rules be reviewed as an extra setup step, or approved automatically? → A: Approved automatically after setup (Ravi). Later changes still need the person's approval.
- Q: Extra scope? → A: Ravi added (same day) Explore rows that expand instead of opening a job page, with the title opening the posting (US5), and relevance that follows the resume's stack, area and experience instead of listing Java and front-end roles (US6). All six stories ship together.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Finish setup and search straight away (Priority: P1)

A person finishes the four setup cards. HireTitan approves the search rules it proposes from their profile and preferences on its own, and Explore opens ready to search: the person sees "Search now", not "Finish setup first". The rules can be checked and changed later under Profile > Search rules.

**Why this priority**: This is the dead end that stopped Ravi. Without it, a new user finishes setup and cannot search, which breaks the main journey of the app.

**Independent Test**: Start from a fresh install (or after Delete all my data), finish the four setup cards, and check that Explore offers "Search now" and that Profile > Search rules shows approved rules without anything else being clicked.

**Acceptance Scenarios**:

1. **Given** a person who has confirmed their profile and saved their preferences and has never had approved search rules, **When** they press "Finish setup", **Then** the rules proposed from that profile and preferences are approved, and Explore shows "Search now" with no "Finish setup first" message.
2. **Given** setup has just finished and the rules were approved automatically, **When** the person opens Profile > Search rules, **Then** they see the approved rules and a short note that HireTitan set them up from their profile and preferences and that they can change them.
3. **Given** the person already has approved rules (for example they finished setup before), **When** setup is finished again or the preferences are saved again, **Then** the approved rules are not replaced; a change in the profile or preferences still only offers updated rules, as today.
4. **Given** an install where setup is finished but no rules have ever been approved (for example it finished setup before this feature), **When** HireTitan next starts, **Then** the first rules are approved automatically, as in scenario 1, so Home and Explore are ready when the person opens them.
5. **Given** the proposed rules cannot be approved (for example they contain no job title to look for), **When** setup finishes, **Then** setup still finishes, nothing is approved, and Explore says what is missing in plain words with a link that opens Profile > Search rules.
6. **Given** any step is still missing (no AI key, no confirmed profile, no saved preferences, no approved rules), **When** Explore has no jobs, **Then** the message names the missing step and links straight to the place where it is done, instead of "Finish setup first".

---

### User Story 2 - See that a search is running (Priority: P1)

A person presses "Search now". From the first second the panel shows that a search is running: a moving indicator and a plain message such as "Searching your companies…". It never shows "0 of 0" or batch numbers. Once HireTitan knows how many companies it will check, the panel shows simple progress (companies checked out of the total and new jobs found so far). The Stop button stays.

**Why this priority**: The current panel made Ravi think the search had found nothing and was not running. A search takes minutes, so the person needs to trust that it is working.

**Independent Test**: Start a search with the scripted job sources and check what the panel shows before the first company is read, during the search and after it ends, with no batch number anywhere.

**Acceptance Scenarios**:

1. **Given** no search is running, **When** the person presses "Search now", **Then** within one second the panel shows a moving indicator and "Searching your companies…", and does not show "0 of 0" or any zero count.
2. **Given** a search is running and the number of companies to check is known, **When** the panel updates, **Then** it shows how many companies have been checked out of that number and how many new jobs were found so far, in one short line, plus a progress bar that matches.
3. **Given** a search is running and no new company has been checked for a while (a slow site), **When** the person looks at the panel, **Then** the indicator is still moving, so the search does not look stuck.
4. **Given** a search is running, **When** the person presses Stop, **Then** the panel says the search is stopping and that jobs found so far are kept, with no mention of batches.
5. **Given** a search has ended (finished, stopped, out of AI credit, or an error), **When** the person looks at the panel, **Then** it says how it ended in plain words without the word "batch", shows the number of new jobs added, and still links to the summary and search history. The out-of-credit message from the AI provider is shown as today.
6. **Given** a person uses a screen reader, **When** the search starts, progresses and ends, **Then** these changes are announced politely, and the moving indicator is not read out.
7. **Given** the person has asked their system to reduce motion, **When** a search is running, **Then** the "searching" state is still clear without movement (for example a static indicator and the message).

---

### User Story 3 - Understand and change the search rules (Priority: P2)

A person opens Profile > Search rules and understands at a glance which jobs HireTitan keeps and which it leaves out, in plain language, without internal labels. They can change the rules with one Edit button, and save or cancel.

**Why this priority**: The rules decide which jobs the person sees (in the last test, almost every job was left out), so they must be easy to read and change. It comes after US1 and US2 because the app works without it, just less clearly.

**Independent Test**: Open Search rules with approved rules, check that no "Skips jobs", "Guides the AI", "Similar title", "From your profile" or other per-item tags are shown, edit a title, save, and check the saved rules.

**Acceptance Scenarios**:

1. **Given** approved rules, **When** the person opens Search rules, **Then** the rules are shown in three plain groups: what jobs are kept (job titles), what jobs are left out (words to avoid in titles, places to skip, how old a posting may be), and what helps rank a job when the AI check is on (skills, places you prefer, plus work mode, seniority and years of experience from Preferences).
2. **Given** the page shows rules, **When** the person reads any rule, **Then** no item carries a tag such as "Skips jobs", "Guides the AI", "Similar title", "From your preferences", "From your profile" or "Added by you"; each group explains in one sentence what it does.
3. **Given** approved rules, **When** the person presses Edit, changes something and presses Save, **Then** the changed rules become the rules searches use, and the page shows "Rules saved." with the new rules.
4. **Given** the person is editing, **When** they press Cancel, **Then** nothing changes and the page shows the rules as they were.
5. **Given** the person is editing, **When** a value is not valid (for example no job title left, or a posting age outside 1 to 365 days), **Then** Save is refused and the problem is shown next to that group, in plain words.
6. **Given** the profile or preferences changed since the rules were approved, **When** the person opens Search rules, **Then** a notice says so and offers "Update from my profile", which opens the suggested rules in edit mode for the person to check and save; nothing changes until they save.
7. **Given** the person is editing, **When** they press "Start over with suggested rules", **Then** the editor is filled with the rules suggested from the current profile and preferences, still unsaved.
8. **Given** the person is editing and tries to leave the page with unsaved changes, **When** they navigate away, **Then** they are asked before the changes are lost, as other edit forms in the app do.

---

### User Story 4 - A roomier Preferences step in setup (Priority: P3)

During first-run setup the Preferences step uses the width of the screen, so its fields sit side by side as they do on the Preferences page, and the step is much shorter to scroll.

**Why this priority**: It is a comfort fix; setup already works.

**Independent Test**: Open the Preferences step of setup on a wide screen and check that the preference groups sit in two columns and that the step is shorter than before; check a narrow screen still shows one readable column.

**Acceptance Scenarios**:

1. **Given** a screen at least as wide as a common laptop (1280 pixels), **When** the person reaches the Preferences step, **Then** the step's card is wide enough for the preference groups to sit in two columns, as on the Preferences page.
2. **Given** a phone-width screen, **When** the person reaches the Preferences step, **Then** the groups stack in one column with no sideways scrolling.
3. **Given** the other setup steps (name, resume, profile review), **When** the person goes through them, **Then** they keep their current width unless a wider card clearly helps (the review step may use the same width as Preferences).
4. **Given** the Preferences step, **When** the person compares it with today, **Then** it collects exactly the same information and "Finish setup" behaves the same apart from US1.

---

### User Story 5 - Job details open in the Explore row (Priority: P2)

In Explore, a person clicks a job row and it expands in place to show what the job page shows today (place, work mode, posted date, why it was kept, sources, description when there is one, and the actions). The job title is a link that opens the job posting on the company's site in a new tab. Explore no longer opens a separate job page.

**Why this priority**: Opening a new page for a few facts breaks the flow of scanning a list; the In pipeline tab already expands rows the same way.

**Independent Test**: In Explore, click a row and check the details appear under it without leaving the list; click the title and check the posting opens in a new tab; check keyboard users can expand and collapse a row.

**Acceptance Scenarios**:

1. **Given** Explore lists jobs, **When** the person clicks a row (outside the title and the action buttons), **Then** the row expands in place to show the job's details and actions, and clicking it again collapses it.
2. **Given** Explore lists jobs, **When** the person clicks the job title, **Then** the posting opens on its own site in a new tab, and HireTitan stays on Explore.
3. **Given** a job has more than one source link, **When** the person clicks the title, **Then** the link of the source where the job was first found opens; the other links are listed in the expanded row.
4. **Given** a job has no link (for example a pasted job without one), **When** the person looks at the title, **Then** it is plain text, not a link.
5. **Given** a keyboard user, **When** they tab to a row's expand control and press Enter or Space, **Then** the row expands or collapses, and the expanded state is announced.
6. **Given** a row is expanded, **When** the person uses an action there (I applied, I inquired, Check again, Restore, Delete), **Then** it works as it does on the job page today.
7. **Given** other places that link to a job's page today (search summary, duplicates, In pipeline), **When** the person follows those links, **Then** they keep working as today; only Explore changes.

---

### User Story 6 - Explore shows only jobs that fit me (Priority: P1)

After a search, Explore lists jobs that fit the person's area of work, tech stack and experience from their profile and preferences. Roles in another area (for example front end when the person works on back end) or built on a stack the person does not use (for example Java for a Python and Go engineer) are left out, with a reason the person can read in the search summary.

**Why this priority**: In Ravi's search on 2026-11-16, 20 of 20 jobs kept by the AI check were generic "Software Engineer" or "Software Development Engineer" titles, including front-end, full-stack and Java roles. Explore is only useful if what it shows is relevant.

**Findings that shape this story (2026-11-16)**: every kept job reached the AI check with an empty description and no skills or years found, because the job sources give only the title, place and link; the approved rules looked only for "software engineer", "sde" and similar titles, with no words to avoid; the relevance prompt answers "relevant" when it cannot tell, so a title alone was nearly always enough; and the profile card sent to the AI check carried only the skills typed in Preferences (empty for Ravi), not the skills from the confirmed profile, so the check saw no skills at all.

**Independent Test**: Run a search against scripted job sources holding a set of synthetic postings for a back-end Python and Go profile (back-end Python roles, front-end roles, Java roles, generic "Software Engineer" titles with and without descriptions) and check which ones reach Explore.

**Acceptance Scenarios**:

1. **Given** a profile whose work is back end with Python and Go, **When** a search finds "Senior Software Engineer - Frontend", **Then** the job is left out, and the reason says it is front-end work.
2. **Given** the same profile, **When** a search finds "Senior Software Engineer - BackEnd (Java)", **Then** the job is left out, and the reason says it needs Java, which is not among the person's skills.
3. **Given** a job whose title alone does not show the area or stack (for example "Software Development Engineer"), **When** the job passes the free rules, **Then** HireTitan reads the posting's description from its source before the AI check, where the source allows it, and the AI decides on the description.
4. **Given** a job whose description cannot be read (the site does not allow it, or it fails), **When** the AI checks it, **Then** the decision is made on the title, company and place only, and the job is kept only if nothing in them points to another area or stack; its reason says the description could not be read.
5. **Given** a profile and preferences, **When** search rules are proposed, **Then** they include the person's area of work and words to avoid in titles for clearly different areas (for example "frontend", "front end", "android", "ios", "QA" for a back-end engineer), which the person can remove.
6. **Given** a job title that names a programming language or framework the person does not list (for example "Java Developer" for a person without Java), **When** the free rules run, **Then** the job is left out by the rules with the reason "needs <language>, which is not in your skills", unless the person also lists that language.
7. **Given** a job whose description shows a much higher or lower level than the person's years of experience (for example "10+ years" for a person with 4.5 years), **When** the AI checks it, **Then** it is left out with a reason that says so.
8. **Given** the relevance check changes, **When** the new version is used for the first time, **Then** it has passed the project's relevance evaluation on a set that includes the cases above, at least as well as the current version on the old cases.

---

### Edge Cases

- A person finishes setup while the AI key is missing or rejected: the rules are still approved (proposing rules uses no AI), and Explore shows the existing AI-key notice instead of "Search now" being blocked by rules.
- Two "Finish setup" presses at once, or a finish while start-up is approving the first rules (US1 AS4): exactly one set of rules is approved; the person never ends up with two approved versions from one setup.
- Delete all my data clears the rules and setup; going through setup again approves fresh first rules.
- The person changed or replaced the rules before (they had approved rules once): the automatic approval never runs again, because they already had approved rules.
- A search is started but the job sources answer before the panel's first refresh: the panel may go straight to the progress line; it must never flash "0 of 0".
- A search where every company is skipped or fails: the ended panel says the search finished, with zero new jobs and the link to the summary, which explains per company what happened.
- A very long search (many companies, slow sites): the progress line moves when companies are checked, and the indicator keeps moving in between.
- The person edits the rules while a search is running: the running search keeps the rules it started with (as today); the saved rules apply to the next search.
- The Search rules page with an open proposal left over from before this feature: it opens in edit mode with that proposal, so nothing is lost.

## Requirements *(mandatory)*

### Functional Requirements

**First rules approved automatically (US1)**

- **FR-001**: When the person finishes first-run setup and has never had approved search rules, the system MUST propose rules from the confirmed profile and saved preferences and approve them, with no extra step or click.
- **FR-002**: The automatic approval MUST happen at most once per install (or once again after Delete all my data). If approved rules exist or have existed, the system MUST NOT approve anything on its own; a later profile or preference change still only offers updated rules for the person to save.
- **FR-003**: An install where setup is finished but no rules were ever approved MUST get its first rules approved the same way the next time HireTitan starts (opening a page never changes data).
- **FR-004**: If the proposed rules cannot be approved, setup MUST still finish, nothing is approved, and Explore MUST explain what is missing and link to Profile > Search rules.
- **FR-005**: Automatically approved rules MUST be recorded the same way as rules the person approved (same history and version numbers), with a marker that they were set up automatically, so the Search rules page can say so.
- **FR-006**: When Explore has no jobs because a step is missing, the message MUST name the first missing step (AI key, profile, preferences or search rules) and link to where it is done.
- **FR-007**: The automatic approval MUST make no AI call (rules are proposed by the existing rule-based proposer).

**Search progress (US2)**

- **FR-008**: From the moment a search starts until it ends, the Search panel MUST show a "searching" state: a moving indicator (static under reduced motion) and the message "Searching your companies…".
- **FR-009**: The panel MUST NOT show batch numbers, "0 of 0", or counts of zero before the first company is checked.
- **FR-010**: Once the number of companies to check is known, the panel MUST show one short line with companies checked out of that number and new jobs found so far, and a progress bar for companies checked.
- **FR-011**: Messages for stopping and for how a search ended MUST NOT mention batches; they MUST say that jobs found so far are kept where that applies. The provider's out-of-credit message MUST still be shown.
- **FR-012**: Start, progress and end MUST be announced politely to screen readers; the moving indicator MUST be hidden from them.

**Search rules page (US3)**

- **FR-013**: The Search rules page MUST group the rules as: jobs kept (job titles), jobs left out (words to avoid in titles, places to skip, oldest posting age), and what helps rank a job when the AI check is on (skills, places you prefer, and the work mode, seniority and years of experience taken from Preferences). Each group MUST have a one-sentence plain explanation.
- **FR-014**: The page MUST NOT show per-item tags for where a rule came from or what it does ("Skips jobs", "Guides the AI", "Similar title", "From your preferences", "From your profile", "Added by you"). This amends 002 FR-002 (showing each rule's source) and FR-005 (showing each rule's effect): the effect is now explained once per group, and the source is no longer shown.
- **FR-015**: The page MUST have a read view and an edit view. Edit opens the current rules for changing; Save makes the edited rules the approved rules in one step; Cancel leaves everything as it was.
- **FR-016**: Save MUST be refused with field-level messages next to the affected group when the rules are not valid, using the existing rule checks.
- **FR-017**: When the profile or preferences changed since the rules were approved, the page MUST say so and offer "Update from my profile", which opens the suggested rules in the edit view; nothing changes until Save.
- **FR-018**: The edit view MUST offer "Start over with suggested rules", which fills the editor with the rules suggested from the current profile and preferences without saving.
- **FR-019**: Leaving the edit view with unsaved changes MUST ask first, as other edit forms in the app do.
- **FR-020**: When the rules were set up automatically and not changed since, the page MUST say so in one line ("HireTitan set these up from your profile and preferences. Change anything you like.").

**Preferences step (US4)**

- **FR-021**: The Preferences step of first-run setup MUST use a wider card than the name and resume steps, wide enough for the preference groups to sit in two columns at 1280 pixels and wider, and MUST stack to one column without sideways scrolling on a phone-width screen.
- **FR-022**: The Preferences step MUST collect the same information as today.

**Job details in the Explore row (US5)**

- **FR-025**: Clicking a job row in Explore MUST expand it in place to show the job's details (place, work mode, posted date, the decision and its reason, sources, description when present, duplicate notice) and its actions; clicking again MUST collapse it. Explore MUST NOT navigate to a separate job page.
- **FR-026**: The job title in an Explore row MUST open the job's first-found source link in a new tab; a job with no link MUST show its title as plain text.
- **FR-027**: Rows MUST be expandable by keyboard, with the expanded state exposed to screen readers, matching the In pipeline rows.
- **FR-028**: Links to a job's page from other places (search summary, duplicates, In pipeline) MUST keep working.

**Relevant jobs only (US6)**

- **FR-029**: For each job that passes the free rules in a search with the AI check on, the system MUST try to read the posting's description from its source before the AI check, obeying the same politeness rules as other page reads (robots.txt, spacing per site, allowed hosts, size limits). Descriptions read this way MUST be screened as untrusted text, like every other job text.
- **FR-030**: Search rules MUST include the person's area of work (for example back end, front end, full stack, mobile, data, QA, DevOps), proposed from the profile and preferences and editable on the Search rules page (Preferences keeps its fields, FR-022).
- **FR-031**: Proposed rules MUST include words to avoid in titles for areas clearly different from the person's (a fixed, reviewed table per area), shown on the Search rules page where the person can remove them.
- **FR-032**: The free rules MUST leave out a job whose title names a programming language or framework from a fixed, reviewed list that the person does not have among their skills, with the reason "needs <name>, which is not in your skills".
- **FR-033**: The AI check MUST receive the person's area of work, main skills (the person's languages and frameworks first, tools after), years of experience and recent job titles, and MUST be told to leave out jobs in another area, jobs whose main stack is not the person's, and jobs far above or below the person's experience.
- **FR-034**: When a job reaches the AI check with no description, the AI MUST decide on the title, company and place only, MUST leave it out when the title points to another area or stack, and its reason MUST say the description could not be read when it keeps the job.
- **FR-035**: The changed relevance check MUST be a new prompt version that passes the project's relevance evaluation before it is used; the evaluation set MUST gain synthetic cases for: different area named in the title, different stack named in the title, generic titles with a description, generic titles without a description, and experience far above the person's.
- **FR-036**: Leaving a job out for its area or stack MUST follow the existing rules: the job is listed among the skipped jobs of the search summary with its reason, and the person can restore it.

**All stories**

- **FR-023**: All new and changed text MUST be in English, MUST NOT show or estimate AI cost, and MUST keep the flat navy and orange theme, keyboard use and focus behaviour.
- **FR-024**: The requirements baseline (`docs/clarified-requirements.md` §3) and the 002 spec (FR-002, FR-004, FR-005, FR-006) MUST carry dated change notes for the automatic first approval and the page changes.

### Key Entities

- **Approved search rules**: the rule set searches use. Gains a marker saying whether it was approved automatically after setup or by the person, so the page can show FR-020 and FR-002 can tell "never had approved rules" from "had them once".
- **Area of work**: a new part of the search rules and preferences (one or more of back end, front end, full stack, mobile, data, QA, DevOps, other) that decides which title words are avoided and what the AI check is told.
- **Job description**: the posting's text, now read from the source for jobs that pass the free rules; stored with the job as today and shown in the expanded row.
- **Search run (existing)**: what the panel shows. The panel now uses only whether it is running, companies checked, companies to check (once known), new jobs found and how it ended; batch numbers are no longer shown.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person who finishes the four setup cards can start a search with one click from Explore, with no other page visited; checked by the setup journey test.
- **SC-002**: After pressing "Search now", a "searching" state is visible within 1 second, and "0 of 0" or a batch number never appears at any point of a search; checked by tests on the panel and the job-search journey.
- **SC-003**: The Search rules page shows none of the six old tag texts and the word "batch" appears nowhere in the Search panel; checked by tests.
- **SC-004**: A person can change one job title and save it from the Search rules page in 3 clicks or fewer (Edit, change, Save).
- **SC-005**: At 1280 × 800 the Preferences step needs at least 40% less vertical scrolling than before; measured once with screenshots before and after.
- **SC-007**: In Explore, a person can see a job's details without leaving the list, and open its posting with one click on the title.
- **SC-008**: On the new evaluation cases for a back-end Python and Go profile, at least 95% of front-end, mobile, QA and Java roles are left out, while recall on the existing relevant cases stays at 95% or higher.
- **SC-009**: In a real search with the AI check on, at least 70% of the jobs that pass the free rules reach the AI check with a description (measured once on Ravi's company list and recorded).
- **SC-006**: The automatic approval runs at most once per install: a test that finishes setup twice, saves preferences again and restarts HireTitan finds exactly one automatically approved rule set.

## Assumptions

- "Setup finished" means the existing "Finish setup" action at the end of the Preferences step.
- The rule-based proposer from 002 already produces a valid rule set from a confirmed profile and saved preferences in the usual case; when it does not (for example no target role), the person is sent to Search rules (FR-004).
- Approving the first rules automatically is an accepted change to "you approve what is proposed" for the first rules only (Ravi, 2026-11-16). Every later change still needs the person to save it.
- Saving an edit on the Search rules page counts as the person's approval; the separate draft-then-Approve step is merged into Save. The stored history of proposals and approvals stays as it is.
- The "Rules only (no AI)" checkbox on the Search panel and the search summary and history pages stay as they are.
- Work mode, seniority and years of experience stay editable only in Preferences; the Search rules page shows them read-only with a link to Preferences.
- The search keeps reading companies in groups internally; only the display stops mentioning them.
- No new job sources. Jobs are still listed the same way; what changes is that a job passing the free rules gets its description read before the AI check (US6), and how relevance is judged. The careers-page gzip fix found on 2026-11-16 is a separate bug fix.
- Reading descriptions adds one request per job that passes the free rules, spaced per site; searches get somewhat slower. The plan decides, per job source, where the description comes from (some boards return it in the listing, others need one request per posting).
- The language and framework list (FR-032) and the area table (FR-031) are small, fixed, reviewed files in the repo, like the title synonym table from 002; they are not learned or AI-generated.
- Running the relevance evaluation needs Ravi's API key and costs a small amount; it is run before the new prompt goes live.
- The job page itself stays (other pages link to it); Explore just stops opening it.
