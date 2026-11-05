# Feature Specification: Job Search and Home Page List

**Feature Branch**: `002-job-search`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Job discovery and home page listing: fetch relevant jobs for the user from job sources based on their confirmed profile and preferences, deduplicate them, score or rank them for relevance, and list them on the home page. The app never applies or sends anything."

## User Scenarios & Testing *(mandatory)*

HireTitan already knows who the user is (the confirmed profile) and what they want (job preferences). This feature turns that into a list of real, open jobs. The person presses "Search now"; HireTitan reads job boards and company careers pages that the rules allow, removes duplicates, sorts every job into **match**, **maybe** or **hidden** with the reason for each, and shows the result on the home page, newest first. By default a search uses no AI and costs nothing. AI is offered only as optional extras the user chooses and sees a cost for first. HireTitan never applies to a job, sends a message or contacts anyone.

### User Story 1 - Search now and see relevant jobs on the home page (Priority: P1)

After setup, the person presses **Search now**. HireTitan uses their approved search rules, reads the shipped list of companies' job boards, and shows the jobs it found on the home page: one list, newest first, each job with its title, company, location, work mode, posted date, where it was found, and a **match / maybe** label with the reason. Jobs the rules hide are kept out of the main list but can be shown and restored.

**Why this priority**: This is the first moment the app does real job-search work, and the thing the person asked for. Without it nothing else in the feature has a place to show up.

**Independent Test**: With a confirmed profile, saved preferences and approved rules, run a search against recorded job-board data for a few companies. The home page lists the jobs, newest first, each with a label and a reason, and a second search adds only the new jobs.

**Acceptance Scenarios**:

1. **Given** a confirmed profile, saved preferences and approved search rules, **When** the person presses Search now, **Then** progress is shown, and when it finishes the home page lists the jobs found, newest first, each with title, company, location, work mode, posted date and source.
2. **Given** a finished search, **When** the person looks at any job, **Then** it shows whether it is a match or a maybe and the rule that decided it, for example "title contains 'backend engineer'" or "location Chennai is in your list".
3. **Given** a job whose location is in the person's blocked list, **When** the search finishes, **Then** the job is hidden, the reason reads "hidden: location Pune is in your blocked list", and it is not in the main list.
4. **Given** hidden jobs exist, **When** the person opens the hidden view and restores one, **Then** it moves back to the main list and stays there on later searches.
5. **Given** a job was found in an earlier search, **When** the person searches again and the job is still open, **Then** it appears once, not twice, and keeps any state the person gave it.
6. **Given** no search has been run yet, **When** the person opens the home page, **Then** it explains that no jobs have been fetched and offers Search now.
7. **Given** setup is not finished (no confirmed profile or no preferences), **When** the person opens the home page, **Then** the setup checklist is shown first and Search now is explained as waiting for it.

---

### User Story 2 - Approve the search rules (Priority: P1)

HireTitan proposes **search rules** from the confirmed profile and preferences: job-title words to include and to exclude, synonyms, stack keywords, locations and work mode, and the oldest posting to show. The person reads them, edits them by hand and approves them. A search runs only from approved rules. When the profile or preferences change, the app proposes updated rules and changes nothing until the person approves.

**Why this priority**: Searching needs rules, and the person must stay in control of what is searched and hidden. It is P1 because Story 1 cannot start without approved rules.

**Independent Test**: Starting from a confirmed profile, the person gets proposed rules with each rule explained, edits one, approves, and the saved rules are what the next search uses. Without the AI, the person can still write rules by hand.

**Acceptance Scenarios**:

1. **Given** a confirmed profile and saved preferences, **When** the person opens the search rules for the first time, **Then** proposed rules are shown, each with the profile or preference fact it came from.
2. **Given** proposed rules, **When** the person edits, adds or removes any rule and approves, **Then** exactly those rules are saved and used by later searches.
3. **Given** the AI is unavailable or the person prefers not to use it, **When** they open the search rules, **Then** a sensible set built from their preferences is offered without the AI, and they can write rules by hand.
4. **Given** approved rules exist, **When** the profile or preferences change, **Then** the app proposes updated rules and offers to re-sort the open jobs, and the existing rules and job labels stay as they are until the person approves.
5. **Given** no rules are approved, **When** the person presses Search now, **Then** the search does not run and the person is taken to approve rules first.
6. **Given** a rule excludes something (a blocked city or an excluded title word), **When** it is shown, **Then** it is marked as hiding jobs, while preference-based rules are marked as ranking only.

---

### User Story 3 - See and manage the companies being searched (Priority: P2)

HireTitan ships a list of companies with their careers pages, and the person can see it. They can add their own companies (by careers link), hide built-in ones, edit entries, delete their own entries, and import or export the list as a spreadsheet file. For a company added by the person, HireTitan finds the matching job board and asks the person to confirm the match before using it. Companies whose board cannot be read automatically go to a **check manually** list with their careers link and the date they were last checked.

**Why this priority**: The built-in list gives a first search something to read, so Story 1 works without this. Letting the person shape the list makes the results theirs.

**Independent Test**: Add a company by careers link, confirm the suggested match, search, and see that company's jobs; hide a built-in company, search, and see none of its jobs.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the person opens the companies screen, **Then** the built-in companies are listed with name, city, careers link and whether a job board was found for each.
2. **Given** the person adds a company with a careers link, **When** a matching job board is found, **Then** the match is shown and used only after the person confirms it.
3. **Given** a company with no readable job board, **When** the search finishes, **Then** it appears on the check-manually list with its careers link and last-checked date, and the search did not fail because of it.
4. **Given** the person hides a built-in company, **When** they search again, **Then** none of its jobs are fetched, and a later app update does not bring it back.
5. **Given** the person has edited or hidden companies, **When** the app is updated with a newer shipped list, **Then** new companies are added and the person's edits are kept.
6. **Given** a spreadsheet file of companies, **When** the person imports it, **Then** valid rows are added or updated, invalid rows are listed with the reason, and nothing else changes; exporting gives a file the import accepts.

---

### User Story 4 - Add a job by hand (Priority: P2)

The person pastes a job link and its description into HireTitan. It joins the same list as any other job: deduplicated, sorted by the same rules and shown with a label and reason.

**Why this priority**: Many good jobs come from friends, recruiters or boards HireTitan may not read. Paste always works, even when no source does.

**Independent Test**: Paste a job link and description for a job that is also in the list from a search; the list still shows it once, with both sources noted.

**Acceptance Scenarios**:

1. **Given** the person pastes a link and description, **When** they save it, **Then** it appears in the list with a label and reason like any other job.
2. **Given** the pasted job is already in the list from a search, **When** it is saved, **Then** the list shows one job with both sources, not two.
3. **Given** the pasted text contains instructions aimed at an AI, **When** it is saved, **Then** it is treated as plain text, a warning is shown, and nothing in it changes how HireTitan behaves.
4. **Given** the link or description is missing, **When** the person tries to save, **Then** a clear message says what is missing and nothing is saved.

---

### User Story 5 - Mark a job as applied (Priority: P2)

The person opens a job from the Explore list, applies on the company's own site, and comes back and presses **I applied**. The job moves from Explore to the **Applied** list with the date. HireTitan only records what the person tells it; it never applies itself. The Applied list is the same list that the later applications feature fills from the person's Gmail and extends with statuses, reminders and contacts.

**Why this priority**: Without it, jobs the person already applied to keep showing up in Explore, and there is no record of what they sent. It is small and needed before the list is useful day to day.

**Independent Test**: Mark one job as applied; it leaves Explore, shows in Applied with today's date, and a later search does not bring it back to Explore. Undo it and it returns to Explore.

**Acceptance Scenarios**:

1. **Given** a job in Explore, **When** the person presses I applied, **Then** it leaves Explore and appears in Applied with the date (today by default, editable) and a link to the posting.
2. **Given** a job in Applied, **When** a later search finds it again, **Then** it stays in Applied and is not re-labelled, hidden or listed twice.
3. **Given** a job was marked applied by mistake, **When** the person undoes it, **Then** it returns to Explore with its previous label.
4. **Given** the person applied to a job HireTitan never found, **When** they add it by pasting it (Story 4), **Then** they can mark it applied straight away.

---

### User Story 6 - Optional AI relevance check on the "maybe" jobs (Priority: P3)

On the jobs labelled maybe, or jobs the person picks, they can choose **Check with AI**. HireTitan first shows what it will cost. The AI then says relevant or not relevant with a visible reason, shown next to the rule-based label. The person can undo any AI decision.

**Why this priority**: The rules already do the main work for free. AI is a paid extra for the undecided jobs only.

**Independent Test**: Pick three maybe jobs, see the cost estimate, confirm, and see a verdict with a reason on each; undo one and the job returns to maybe.

**Acceptance Scenarios**:

1. **Given** maybe jobs are selected, **When** the person chooses Check with AI, **Then** an estimated cost is shown first and nothing is sent until they confirm.
2. **Given** the person confirms, **When** the check finishes, **Then** each job shows relevant or not relevant with a reason, and these are marked as AI judgments.
3. **Given** an AI verdict hides a job, **When** the person undoes it, **Then** the job returns to its previous label.
4. **Given** the monthly AI budget would be exceeded, **When** the person tries to confirm, **Then** the check is blocked with a clear message and no job changes.
5. **Given** the job description contains instructions aimed at an AI, **When** the check runs, **Then** those instructions have no effect, a warning is recorded and shown, and the verdict only follows the schema asked for.

---

### User Story 7 - Optional score for jobs the person picks (Priority: P3)

On jobs the person picks, they can choose **Score**. After the estimated cost is shown and confirmed, each job gets a score, the skills of the person's that match, the gaps, and a verdict (strong 80%+, moderate 60 to 79%, stretch below 60%), based only on facts in the confirmed profile.

**Why this priority**: Useful for choosing between the best jobs, but costs money and builds on Stories 1 and 2.

**Independent Test**: Score one job against the demo profile; the score, matched skills, gaps and band are shown, every matched skill is in the profile, and the cost matches the estimate within a small margin.

**Acceptance Scenarios**:

1. **Given** jobs are picked, **When** the person chooses Score, **Then** an estimated cost is shown first and nothing is sent until they confirm.
2. **Given** a scored job, **When** the person opens it, **Then** the score, band, matched skills, gaps and short verdict are shown.
3. **Given** a scored job, **When** it names a matched skill, **Then** that skill is in the confirmed profile; a result naming a skill the profile lacks is rejected and flagged.
4. **Given** the profile changes, **When** the person opens a previously scored job, **Then** it says the score is from an older profile and offers to score it again.

---

### Edge Cases

- A search is started while another is running: the second is refused with "a search is already running", and the first is unaffected.
- One company's board is down, slow, or returns unreadable data: that company is reported as failed with the reason, other companies' jobs still arrive, and jobs already stored are kept.
- Every source fails: the person sees a clear message, the previous list is untouched, and nothing is lost.
- The same job appears from two sources with slightly different titles or locations: it is shown once, with both sources, and a "possible duplicate" the person can confirm or split when the match is not certain.
- A job disappears from its board between searches: it stays in the list marked "no longer listed" and is not deleted.
- A posting has no date, no location or no pay: it is shown with those fields empty, not guessed, and the rules that need them say so ("location not stated").
- A posting is very long or in a language other than English: text is length-capped; English is the supported language, and unreadable postings are shown with a note instead of failing the search.
- The person changes rules between searches: older jobs keep their label until a re-sort is requested or the next search; nothing is silently hidden by a rule the person has since removed.
- The monthly AI budget is reached mid-action: the action stops cleanly, completed results are kept, and the rest are left as they were.
- The AI key is missing or rejected: rule-based search, dedup, the list and manual paste all still work; only AI extras are unavailable, with a short reason.
- The person has hundreds of jobs: the list stays usable through paging or filtering and sorting by label, source and date.
- The person deletes all their data: jobs, rules, company edits and search history are removed with everything else.

## Requirements *(mandatory)*

### Functional Requirements

**Search rules**

- **FR-001**: The system MUST propose search rules from the confirmed profile and saved preferences: title words to include and exclude, synonyms, stack keywords, locations, work mode, and the oldest posting age.
- **FR-002**: Each proposed rule MUST show the profile or preference fact it came from, and MUST be editable, removable and addable by hand before approval.
- **FR-003**: The person MUST be able to build and approve rules without any AI, and the AI proposal MUST be optional and shown for approval before it takes effect.
- **FR-004**: The system MUST NOT run a search until the person has approved a set of rules, and MUST save the approved rules until they are changed.
- **FR-005**: The system MUST mark each rule as either hiding (the person's explicit exclusions, such as a blocked city or an excluded title word) or ranking-only (weighted preferences), and only hiding rules may hide a job.
- **FR-006**: When the profile or preferences change, the system MUST propose updated rules and offer to re-sort open jobs, and MUST change nothing until the person approves.

**Running a search**

- **FR-007**: A search MUST run only when the person starts it ("Search now"); the system MUST NOT search on a schedule or in the background.
- **FR-008**: A search MUST show progress and a final summary: companies read, jobs found, new jobs added, jobs merged as duplicates, and any company that failed or needs manual checking.
- **FR-009**: Only one search MAY run at a time.
- **FR-010**: A search with the default settings MUST use no AI and incur no AI cost.
- **FR-011**: Sources MUST be isolated: a failing, slow or blocked source MUST NOT stop other sources or remove jobs already stored.
- **FR-012**: The system MUST fetch jobs only from permitted sources: public job-board interfaces of the companies being searched, those companies' own public careers pages, the optional free job boards the person enables, and content the person pastes. It MUST NOT scrape or automate sites whose terms forbid it.
- **FR-013**: Reading a company's careers page MUST respect that site's crawling rules, use slow request rates and caching, and identify the app honestly.
- **FR-014**: The system MUST NOT apply to jobs, send messages or emails, or contact anyone.

**Companies**

- **FR-015**: The system MUST ship a versioned list of companies with careers links and the resolved job board for each, containing only company-level facts and no personal data about any individual.
- **FR-016**: The person MUST be able to view, add, edit, hide and delete companies (deleting only their own), and import and export the list as a spreadsheet file.
- **FR-017**: For a company added by the person, the system MUST suggest the matching job board and use it only after the person confirms.
- **FR-018**: Updates to the shipped list MUST be merged without overwriting the person's edits, hidden entries or additions.
- **FR-019**: A company whose job board cannot be read automatically MUST appear on a check-manually list with its careers link and last-checked date.

**Duplicates and sorting**

- **FR-020**: The system MUST merge the same job found in different searches or sources into one entry that records every source it came from.
- **FR-021**: When two entries are only possibly the same job, the system MUST keep them separate but show a possible-duplicate notice the person can confirm (merge) or dismiss.
- **FR-022**: The system MUST sort every job into match, maybe or hidden using the approved rules, and MUST record and show the rule that decided each one.
- **FR-023**: Hidden jobs MUST be kept, viewable and restorable, and a restored job MUST NOT be hidden again by later searches.
- **FR-024**: Jobs MUST be rated only from facts in the posting and the approved rules; where a fact is missing, the job MUST NOT be hidden for it, and the label MUST say the fact was not stated.
- **FR-025**: Fields the posting does not state (date, location, pay) MUST be left empty and never guessed.

**Home page list**

- **FR-026**: Once setup is complete, the home page MUST show the job list (the **Explore** list): match and maybe jobs together, newest first by default, with the label and reason on each job, and a clear way to see hidden jobs.
- **FR-027**: The person MUST be able to filter the list (by label, source, company, work mode, location) and sort it (newest, company, label).
- **FR-028**: The home page MUST show when the last search ran and what it found, and MUST keep the setup checklist visible until setup is done.
- **FR-029**: Each job MUST open to a detail view with the full description, every source with its link, the label and reason, and the search that first found it.
- **FR-030**: Each job MUST link to the original posting so the person can apply there themselves.

**Manual paste**

- **FR-031**: The person MUST be able to add a job by pasting a link and description, which joins the same list with the same dedup and sorting.

**Optional AI features**

- **FR-032**: Every AI action in this feature (rule proposal, relevance check, scoring, AI page reading) MUST be explicitly started by the person, MUST show an estimated cost first, MUST count against the monthly budget, and MUST be blocked when the budget would be exceeded.
- **FR-033**: AI relevance verdicts MUST show a reason, be marked as AI judgments, and be undoable.
- **FR-034**: Scores MUST use only facts in the confirmed profile; any matched skill, number or claim not in the profile MUST cause the result to be rejected.
- **FR-035**: Score bands MUST be strong (80% and above), moderate (60 to 79%) and stretch (below 60%), and every score MUST show matched skills and gaps.
- **FR-036**: When the AI is unavailable or the key is missing, rule-based search, dedup, the list, manual paste and marking jobs applied MUST keep working.

**Applied jobs**

- **FR-037**: The person MUST be able to mark any job as applied, with the date (today by default, editable), and undo it. The system records only what the person tells it and MUST NOT apply on their behalf.
- **FR-038**: Applied jobs MUST appear in an Applied list, separate from Explore, with the date and a link to the posting; later searches MUST NOT re-label, hide or duplicate them.

**Untrusted text and data**

- **FR-039**: All job text (descriptions, titles, snippets, pasted text) MUST be treated as untrusted data: cleaned, length-capped, screened for instructions aimed at an AI, with any warnings stored and shown; it MUST NOT be able to change what the app does.
- **FR-040**: Only structured, length-bounded fields derived from job text MAY reach AI steps that score or judge; raw job text MUST only reach steps that return a fixed, bounded structure.
- **FR-041**: The system MUST NOT hard-code anything specific to a person; locations, roles, pay and companies come from the person's settings and the shipped neutral company list.
- **FR-042**: The person MUST be able to delete a single job, a company they added, or all search data, and "Delete all my data" MUST remove jobs, rules, company edits and search history.
- **FR-043**: The system MUST keep a history of searches (when, what was read, what was found, what failed) that the person can view.

### Key Entities

- **Search rules**: the approved set the person searches with: title words to include and exclude, synonyms, stack keywords, locations and work mode, oldest posting age. Each rule records where it came from (profile fact, preference, or the person) and whether it hides or only ranks. Has a version and approval date.
- **Company**: a name, city, website, careers link and the resolved job board, with where it came from (shipped or added by the person), whether the person edited or hid it, and when it was last checked.
- **Search run**: one press of Search now: when it ran, which rules version, which companies were read, counts of jobs found, added and merged, failures per company, and any AI cost.
- **Job**: one open position: title, company, location, work mode, posted date, description, pay if stated, where it was found, and its state (new, seen, restored, applied with date, no longer listed, deleted).
- **Job source**: one place a job was seen (a company board, a company careers page, a free job board, or a paste) with its link and the date seen; a job can have several.
- **Job label**: match, maybe or hidden, with the deciding rule, whether a rule or the AI decided it, and whether the person restored it.
- **Possible duplicate**: a pair of jobs that may be the same, awaiting the person's merge or dismiss decision.
- **Job score**: score, band, matched skills, gaps, verdict, and which profile version and prompt version produced it.
- **Check-manually entry**: a company whose board cannot be read, with its careers link and last-checked date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with a confirmed profile can go from the home page to a list of relevant jobs, approving rules on the way, in under 5 minutes, excluding the time the sources take to respond.
- **SC-002**: A search with the default settings (no AI) over the shipped company list finishes within 3 minutes on a normal home internet connection, and the person sees progress throughout.
- **SC-003**: A default search costs nothing: zero AI calls and zero AI spend are recorded for it.
- **SC-004**: On a test set of recorded postings with known right answers, at least 90% of jobs a person would call relevant are labelled match or maybe, and none that match the person's explicit exclusions appear outside hidden.
- **SC-005**: Every job in the list shows the rule that decided its label; no job is labelled without a visible reason.
- **SC-006**: On a test set of recorded sources with known duplicates, at least 95% of true duplicates are merged into one entry, and no pair is merged unless it is certain or the person confirmed it.
- **SC-007**: When any one source fails, 100% of jobs from the other sources still arrive and 100% of previously stored jobs remain.
- **SC-008**: The home page shows the first screen of jobs in under 2 seconds with 1,000 stored jobs.
- **SC-009**: Every AI action in this feature shows its estimated cost before it runs, and the recorded cost stays within 20% above the estimate.
- **SC-010**: Every score names only skills present in the person's confirmed profile; across the scoring test set, there are zero scores naming a skill the profile lacks.
- **SC-011**: A set of job postings containing instructions aimed at an AI is run through every step that reads job text; in 100% of cases the instructions have no effect on labels, scores, rules or behaviour, and a warning is recorded.
- **SC-012**: No code path in the feature can apply to a job, send a message or contact anyone, shown by an automated check that fails the build if one is added.
- **SC-013**: In a test, deleting all data removes 100% of jobs, rules, company edits and search history.

## Assumptions

- **Delivery in slices.** Stories are ordered by priority. Stories 1 and 2 are the first deliverable: approve rules, search the shipped company list, and see the list on the home page. Stories 3, 4 and 5 follow. Stories 6 and 7 are optional paid extras and may ship after the rest of the feature if the plan says so. The plan decides the cut line; each story can be built and tested alone.
- **Home page.** Once setup is complete, the home page becomes the job list, and the setup checklist stays at the top until every step is done. The existing setup flow does not change.
- **Rules first, AI optional.** The default search is rule-based with no AI, following the project baseline. The AI only proposes rules, checks maybe jobs, scores picked jobs, and reads a careers page that has no readable board.
- **Weighted preferences do not hide.** Only the person's explicit exclusions (blocked cities, excluded title words) hide jobs. Roles, stack and location weigh most in the match label.
- **Newest first.** The default order is newest posted first; jobs without a date sort by the date they were first seen.
- **No automatic expiry.** Jobs stay until the person deletes them or they are marked "no longer listed"; nothing is removed automatically.
- **Scoring weights.** The starting weights are skills overlap 3x, years of experience 2x, domain 2x, seniority 2x, projects 1x, education 1x, tuned later with the scoring evaluation set; bands are as in FR-035.
- **Shipped company list.** The shipped list is the 62 Chennai companies already prepared, with only the company-level facts; the 10 missing careers links are filled in before release or stay on the check-manually list. Boards were verified by a maintainer for the built-in entries.
- **Sources in scope** (Ravi, 2026-11-05). This feature covers company job boards, company careers pages, the optional free job boards, and manual paste. **AI web-search discovery is moved to a later feature** (the "future pipeline"). Job-alert emails and aggregator interfaces (Adzuna, Jooble, Careerjet) are also later.
- **Applied list and Gmail** (Ravi, 2026-11-05). This feature adds "I applied" and the Applied list. Filling that list from the person's Gmail (application confirmation emails, read-only) belongs to the applications feature (003), together with statuses, reminders and contacts; jobs marked applied here and jobs found in Gmail end up in the same list there.
- **Site terms.** Nothing in this feature fetches from LinkedIn, Naukri, Indeed, Cutshort or similar sites; jobs from them come in only by paste.
- **Language.** English only, as for the rest of the product.
- **Dependencies.** Requires feature 001 (confirmed profile, preferences, AI key and budget guard, untrusted-text screening, background runs, delete-all). Relies on the bundled job-board scanner named in the project constitution; whether its terms and any browser requirement allow what this feature needs is checked in the plan.
- **Open for the plan.** Whether the bundled scanner needs a browser (image size) and what its terms allow; how many of the shipped companies resolve to a readable board; how the relevance test set for SC-004 is built.
- **Single user.** One user per install; no sharing, accounts or notifications. Reminders and application tracking belong to a later feature.
