# Feature Specification: Job Search and Home Page List

**Feature Branch**: `002-job-search`

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Job discovery and home page listing: fetch relevant jobs for the user from job sources based on their confirmed profile and preferences, deduplicate them, score or rank them for relevance, and list them on the home page. The app never applies or sends anything."

## Clarifications

### Session 2026-11-05

- Q: Should the optional AI extras, Story 6 (AI relevance check) and Story 7 (scoring), be built as part of feature 002, or moved to a later feature? → A: Moved to a later feature; 002 ends at Story 5. (The relevance check was later brought back as an automatic step of every search; see the third answer. Scoring stays later.)
- Q: Should the optional free job boards (RemoteOK, Remotive, Himalayas, We Work Remotely, Arbeitnow, HN "Who's hiring") be in 002 or added later with the other extra sources? → A: Later, in the "more sources" feature; 002 searches the company list and paste only.
- Q: How should HireTitan decide which fetched jobs are relevant enough to show? → A: Irrelevant jobs are never shown ("we dont need irrelavant jobs, thats extra noise"). Rules first: the approved title words and exclusions drop obvious noise for free; then the AI judges the remaining jobs on each search, with the cost shown first. With no key or no budget left, rules alone decide. Skipped jobs are kept with their reason and can be looked at and restored from the search summary.
- Q: Before each search, should HireTitan ask to confirm the estimated AI cost? → A: No upfront estimate gate ("our cost estimation is not perfect, its just assumption, lets not rely on it"). A search works through the companies in **batches**; each batch's relevant jobs appear in Explore as soon as it finishes, the actual cost so far is shown live, and the search stops cleanly when the monthly budget is reached or the AI provider reports the account is out of credit, showing the provider's message. Finished batches are kept, and the next search continues with the companies not yet read. The relevance check uses the most token-efficient model that passes its evaluation, and receives only the parts of a posting it needs.

## User Scenarios & Testing *(mandatory)*

HireTitan already knows who the user is (the confirmed profile) and what they want (job preferences). This feature turns that into a short list of real, open, relevant jobs. The person presses **Search now**; HireTitan works through the companies on its list in batches, reads their job boards and careers pages, removes duplicates, drops what is clearly unrelated using the person's approved search rules, asks the AI to judge the jobs that are left, and shows only the relevant ones on the home page (the **Explore** list), newest first, each with the reason it was shown. Jobs that were skipped are not shown in Explore but are kept with their reason, so the person can check them and bring one back. HireTitan never applies to a job, sends a message or contacts anyone.

### User Story 1 - Search now and see relevant jobs on the home page (Priority: P1)

After setup, the person presses **Search now**. HireTitan works through the shipped list of companies in batches. For each batch it reads the companies' job boards, keeps only jobs that pass the approved rules, has the AI judge those against the confirmed profile and preferences, and adds the relevant ones to Explore as soon as the batch is done, showing the AI cost spent so far. Explore is one list, newest first, each job with its title, company, location, work mode, posted date, where it was found, and why it was shown.

**Why this priority**: This is the first moment the app does real job-search work, and the thing the person asked for. Without it nothing else in the feature has a place to show up.

**Independent Test**: With a confirmed profile, saved preferences and approved rules, run a search against recorded job-board data for a few companies and a scripted AI. Explore lists only the relevant jobs, newest first, each with a reason; the summary counts the skipped ones; a second search adds only new jobs.

**Acceptance Scenarios**:

1. **Given** a confirmed profile, saved preferences and approved search rules, **When** the person presses Search now, **Then** the search starts at once, progress is shown batch by batch with the AI cost spent so far, and after each batch Explore lists the relevant jobs found, newest first, each with title, company, location, work mode, posted date and source.
2. **Given** a finished search, **When** the person looks at any job in Explore, **Then** it shows why it was shown, for example "title matches 'backend engineer'; AI: Python and Postgres match your profile".
3. **Given** a company lists jobs unrelated to the person's roles (for example sales or HR), **When** the search finishes, **Then** none of them appear in Explore, and the summary says how many jobs were skipped and offers to show them.
4. **Given** a job whose location is in the person's blocked list, **When** the search finishes, **Then** it is skipped with the reason "location Pune is in your blocked list" and does not appear in Explore.
5. **Given** skipped jobs exist, **When** the person opens them from the search summary and restores one, **Then** it moves into Explore and stays there on later searches.
6. **Given** a job was found in an earlier search, **When** the person searches again and the job is still open, **Then** it appears once, not twice, keeps any state the person gave it, and is not judged again by the AI.
7. **Given** the AI key is missing or rejected, **When** the person presses Search now, **Then** the search runs with rules only, the summary says the AI step was skipped and why, and nothing is charged.
8. **Given** a search is part-way through, **When** the monthly budget is reached or the AI provider reports the account is out of credit, **Then** the search stops after the current call, every finished batch stays in Explore, the person sees the reason (for out of credit, the provider's own message, such as "You exceeded your current quota"), and the next search continues with the companies not yet read.
9. **Given** a search is running, **When** the person presses Stop, **Then** it stops after the current batch and keeps everything already found.
10. **Given** no search has been run yet, **When** the person opens the home page, **Then** it explains that no jobs have been fetched and offers Search now.
11. **Given** setup is not finished (no confirmed profile or no preferences), **When** the person opens the home page, **Then** the setup checklist is shown first and Search now is explained as waiting for it.

---

### User Story 2 - Approve the search rules (Priority: P1)

HireTitan proposes **search rules** from the confirmed profile and preferences: job-title words to look for and to avoid, synonyms, stack keywords, locations and work mode, blocked locations, and the oldest posting to show. The person reads them, edits them by hand and approves them. A search runs only from approved rules. When the profile or preferences change, the app proposes updated rules and changes nothing until the person approves.

**Why this priority**: The rules decide what is fetched, what is skipped for free, and what the AI is asked to judge, so the person must own them. It is P1 because Story 1 cannot start without approved rules.

**Independent Test**: Starting from a confirmed profile, the person gets proposed rules with each rule explained, edits one, approves, and the saved rules are what the next search uses. Without the AI, the person can still write rules by hand.

**Acceptance Scenarios**:

1. **Given** a confirmed profile and saved preferences, **When** the person opens the search rules for the first time, **Then** proposed rules are shown, each with the profile or preference fact it came from.
2. **Given** proposed rules, **When** the person edits, adds or removes any rule and approves, **Then** exactly those rules are saved and used by later searches.
3. **Given** the AI is unavailable or the person prefers not to use it, **When** they open the search rules, **Then** a sensible set built from their preferences is offered without the AI, and they can write rules by hand.
4. **Given** approved rules exist, **When** the profile or preferences change, **Then** the app proposes updated rules, and the existing rules and the current Explore list stay as they are until the person approves.
5. **Given** no rules are approved, **When** the person presses Search now, **Then** the search does not run and the person is taken to approve rules first.
6. **Given** a rule is shown, **When** the person reads it, **Then** it says what it does: skips jobs (title words to avoid, blocked locations, titles matching none of the person's roles, postings older than the limit) or guides the AI's judgment (stack keywords, preferred locations and work mode, seniority).

---

### User Story 3 - See and manage the companies being searched (Priority: P2)

HireTitan ships a list of companies with their careers pages, and the person can see it. They can add their own companies (by careers link), hide built-in ones, edit entries, delete their own entries, and import or export the list as a spreadsheet file. For a company added by the person, HireTitan finds the matching job board and asks the person to confirm the match before using it. Companies whose board cannot be read automatically go to a **check manually** list with their careers link and the date they were last checked.

**Why this priority**: The built-in list gives a first search something to read, so Story 1 works without this. Letting the person shape the list makes the results theirs.

**Independent Test**: Add a company by careers link, confirm the suggested match, search, and see that company's relevant jobs; hide a built-in company, search, and see none of its jobs.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the person opens the companies screen, **Then** the built-in companies are listed with name, city, careers link and whether a job board was found for each.
2. **Given** the person adds a company with a careers link, **When** a matching job board is found, **Then** the match is shown and used only after the person confirms it.
3. **Given** a company with no readable job board, **When** the search finishes, **Then** it appears on the check-manually list with its careers link and last-checked date, and the search did not fail because of it.
4. **Given** the person hides a built-in company, **When** they search again, **Then** none of its jobs are fetched, and a later app update does not bring it back.
5. **Given** the person has edited or hidden companies, **When** the app is updated with a newer shipped list, **Then** new companies are added and the person's edits are kept.
6. **Given** a spreadsheet file of companies, **When** the person imports it, **Then** valid rows are added or updated, invalid rows are listed with the reason, and nothing else changes; exporting gives a file the import accepts.

---

### User Story 4 - Add a job by hand (Priority: P2)

The person pastes a job link and its description into HireTitan. Because the person chose it, the job goes straight into Explore, deduplicated against the jobs already there.

**Why this priority**: Many good jobs come from friends, recruiters or boards HireTitan may not read. Paste always works, even when no source does.

**Independent Test**: Paste a job link and description for a job that is also in Explore from a search; Explore still shows it once, with both sources noted.

**Acceptance Scenarios**:

1. **Given** the person pastes a link and description, **When** they save it, **Then** it appears in Explore with the reason "added by you".
2. **Given** the pasted job is already in Explore from a search, **When** it is saved, **Then** Explore shows one job with both sources, not two.
3. **Given** the pasted text contains instructions aimed at an AI, **When** it is saved, **Then** it is treated as plain text, a warning is shown, and nothing in it changes how HireTitan behaves.
4. **Given** the link or description is missing, **When** the person tries to save, **Then** a clear message says what is missing and nothing is saved.

---

### User Story 5 - Mark a job as applied (Priority: P2)

The person opens a job from Explore, applies on the company's own site, and comes back and presses **I applied**. The job moves from Explore to the **Applied** list with the date. HireTitan only records what the person tells it; it never applies itself. The Applied list is the same list that the later applications feature fills from the person's Gmail and extends with statuses, reminders and contacts.

**Why this priority**: Without it, jobs the person already applied to keep showing up in Explore, and there is no record of what they sent. It is small and needed before the list is useful day to day.

**Independent Test**: Mark one job as applied; it leaves Explore, shows in Applied with today's date, and a later search does not bring it back to Explore. Undo it and it returns to Explore.

**Acceptance Scenarios**:

1. **Given** a job in Explore, **When** the person presses I applied, **Then** it leaves Explore and appears in Applied with the date (today by default, editable) and a link to the posting.
2. **Given** a job in Applied, **When** a later search finds it again, **Then** it stays in Applied and is not judged again, skipped or listed twice.
3. **Given** a job was marked applied by mistake, **When** the person undoes it, **Then** it returns to Explore.
4. **Given** the person applied to a job HireTitan never found, **When** they add it by pasting it (Story 4), **Then** they can mark it applied straight away.

---

### Edge Cases

- A search is started while another is running: the second is refused with "a search is already running", and the first is unaffected.
- One company's board is down, slow, or returns unreadable data: that company is reported as failed with the reason, other companies' jobs still arrive, and jobs already stored are kept.
- Every source fails: the person sees a clear message, the previous list is untouched, and nothing is lost.
- The same job appears from two sources with slightly different titles or locations: it is shown once, with both sources, and a "possible duplicate" the person can confirm or split when the match is not certain.
- A job disappears from its board between searches: it stays where it is marked "no longer listed" and is not deleted.
- A posting has no date, no location or no pay: it is shown with those fields empty, not guessed; a job is never skipped only because a fact is missing, and its reason says the fact was not stated.
- A posting is very long or not in English: text is length-capped before the AI sees it; English is the supported language, and unreadable postings are skipped with the reason "could not read this posting" instead of failing the search.
- The AI provider fails part-way with a temporary error (rate limit, server error, timeout): the call is retried a few times; if it still fails, that batch's remaining jobs are decided by rules alone and marked "not checked by AI", and the person can re-check them later.
- The AI provider says the account is out of credit: this is not retried; the search stops (Story 1, scenario 8) and the message tells the person to add credit with their provider.
- The AI returns something unusable for a job: that job is decided by rules alone and marked "not checked by AI"; the search does not fail.
- The person changes rules between searches: jobs already in Explore stay until the person asks to re-check them or they are found again; nothing is silently removed by a rule the person has since dropped.
- The AI key is missing or rejected: the search runs with rules only (Story 1, scenario 7); manual paste, the lists and marking jobs applied all still work.
- A company lists hundreds of jobs: the rules shrink them before the AI sees any, and batches keep each step small, so the person sees results and cost early and can stop at any time.
- The person has hundreds of jobs: the list stays usable through paging, filtering and sorting.
- The person deletes all their data: jobs, rules, company edits and search history are removed with everything else.

## Requirements *(mandatory)*

### Functional Requirements

**Search rules**

- **FR-001**: The system MUST propose search rules from the confirmed profile and saved preferences: title words to look for and to avoid, synonyms, stack keywords, locations, work mode, blocked locations, and the oldest posting age.
- **FR-002**: Each proposed rule MUST show the profile or preference fact it came from, and MUST be editable, removable and addable by hand before approval.
- **FR-003**: The person MUST be able to build and approve rules without any AI, and the AI proposal MUST be optional and shown for approval before it takes effect.
- **FR-004**: The system MUST NOT run a search until the person has approved a set of rules, and MUST save the approved rules until they are changed.
- **FR-005**: The system MUST show for each rule whether it skips jobs (title words to avoid, blocked locations, titles matching none of the person's roles or their synonyms, postings older than the limit) or guides the AI's judgment (stack keywords, preferred locations and work mode, seniority, years of experience).
- **FR-006**: When the profile or preferences change, the system MUST propose updated rules and MUST change nothing until the person approves.

**Running a search**

- **FR-007**: A search MUST run only when the person starts it ("Search now"); the system MUST NOT search on a schedule or in the background.
- **FR-008**: A search MUST work through the companies in batches, MUST add each batch's relevant jobs to Explore when the batch finishes, and MUST show progress and a final summary: companies read, jobs found, jobs skipped by rules, jobs judged by the AI and how many were kept, new jobs added to Explore, jobs merged as duplicates, the AI cost, and any company that failed or needs manual checking.
- **FR-009**: Only one search MAY run at a time.
- **FR-010**: A search MUST start without an upfront cost confirmation; while it runs, the system MUST show the actual AI cost spent so far, and the person MUST be able to stop it (it stops after the current batch) or choose to run it with rules only.
- **FR-010a**: When the monthly budget is reached or the AI provider reports that the account is out of credit, the search MUST stop after the current call, keep all finished batches, show the reason (for out of credit, the provider's message), and record which companies were not read so the next search continues with them. An out-of-credit response MUST NOT be retried; temporary provider errors (rate limits, server errors, timeouts) MAY be retried a bounded number of times.
- **FR-011**: Sources MUST be isolated: a failing, slow or blocked source MUST NOT stop other sources or remove jobs already stored.
- **FR-012**: The system MUST fetch jobs only from permitted sources: public job-board interfaces of the companies being searched, those companies' own public careers pages, and content the person pastes. It MUST NOT scrape or automate sites whose terms forbid it.
- **FR-013**: Reading a company's careers page MUST respect that site's crawling rules, use slow request rates and caching, and identify the app honestly.
- **FR-014**: The system MUST NOT apply to jobs, send messages or emails, or contact anyone.

**Companies**

- **FR-015**: The system MUST ship a versioned list of companies with careers links and the resolved job board for each, containing only company-level facts and no personal data about any individual.
- **FR-016**: The person MUST be able to view, add, edit, hide and delete companies (deleting only their own), and import and export the list as a spreadsheet file.
- **FR-017**: For a company added by the person, the system MUST suggest the matching job board and use it only after the person confirms.
- **FR-018**: Updates to the shipped list MUST be merged without overwriting the person's edits, hidden entries or additions.
- **FR-019**: A company whose job board cannot be read automatically MUST appear on a check-manually list with its careers link and last-checked date.

**Duplicates and relevance**

- **FR-020**: The system MUST merge the same job found in different searches or sources into one entry that records every source it came from.
- **FR-021**: When two entries are only possibly the same job, the system MUST keep them separate but show a possible-duplicate notice the person can confirm (merge) or dismiss.
- **FR-022**: The system MUST first apply the approved skip rules to every fetched job; a job that a rule skips MUST NOT be sent to the AI.
- **FR-023**: The system MUST then have the AI judge each remaining job as relevant or not relevant against the confirmed profile and preferences, with a short reason; only relevant jobs MUST appear in Explore.
- **FR-024**: Every job, shown or skipped, MUST record and show the reason for the decision and whether a rule or the AI made it.
- **FR-025**: Skipped jobs MUST be kept, reachable from the search summary, and restorable; a restored job MUST stay in Explore on later searches. Skipped jobs MUST NOT appear in Explore.
- **FR-026**: A job MUST be judged by the AI at most once; later searches that find it again MUST reuse the earlier decision unless the person asks to re-check it.
- **FR-027**: A job MUST NOT be skipped only because a fact (date, location, pay) is missing; fields the posting does not state MUST be left empty and never guessed.
- **FR-028**: When the AI is unavailable, the key is missing or rejected, the budget would be exceeded, or the AI's answer for a job is unusable, the affected jobs MUST be decided by rules alone and marked "not checked by AI", and the search MUST still complete.

**Home page list**

- **FR-029**: Once setup is complete, the home page MUST show the **Explore** list: relevant jobs only, newest first by default, with the reason on each job.
- **FR-030**: The person MUST be able to filter Explore (by source, company, work mode, location) and sort it (newest, company).
- **FR-031**: The home page MUST show when the last search ran and its summary, and MUST keep the setup checklist visible until setup is done.
- **FR-032**: Each job MUST open to a detail view with the full description, every source with its link, the reason it was shown, and the search that first found it, and MUST link to the original posting so the person can apply there themselves.

**Manual paste**

- **FR-033**: The person MUST be able to add a job by pasting a link and description; it goes into Explore with the reason "added by you", deduplicated against existing jobs, and is not judged by the AI.

**AI use**

- **FR-034**: The AI actions in this feature are proposing search rules, judging the relevance of jobs that pass the rules, and reading a careers page that has no readable board. Each MUST count against the monthly budget and MUST be blocked when the budget would be exceeded; their actual cost MUST be recorded and shown.
- **FR-035**: The relevance judgment MUST use only the confirmed profile, the saved preferences and the posting; it MUST NOT add facts about the person.
- **FR-035a**: The relevance judgment MUST use the most token-efficient model that passes its evaluation set, and MUST receive only the parts of the profile and posting needed to judge (for example title, location, work mode, required skills and experience, and a length-capped excerpt), not whole documents.

**Applied jobs**

- **FR-036**: The person MUST be able to mark any job as applied, with the date (today by default, editable), and undo it. The system records only what the person tells it and MUST NOT apply on their behalf.
- **FR-037**: Applied jobs MUST appear in an Applied list, separate from Explore, with the date and a link to the posting; later searches MUST NOT judge, skip or duplicate them.

**Untrusted text and data**

- **FR-038**: All job text (descriptions, titles, pasted text) MUST be treated as untrusted data: cleaned, length-capped, screened for instructions aimed at an AI, with any warnings stored and shown; it MUST NOT be able to change what the app does.
- **FR-039**: Raw job or careers-page text MUST only reach AI steps that have no tools and return a fixed, bounded structure (for relevance: relevant or not, and a short reason).
- **FR-040**: The system MUST NOT hard-code anything specific to a person; locations, roles, pay and companies come from the person's settings and the shipped neutral company list.
- **FR-041**: The person MUST be able to delete a single job, a company they added, or all search data, and "Delete all my data" MUST remove jobs, rules, company edits and search history.
- **FR-042**: The system MUST keep a history of searches (when, what was read, what was found, skipped and kept, what failed, what it cost) that the person can view.

### Key Entities

- **Search rules**: the approved set the person searches with: title words to look for and to avoid, synonyms, stack keywords, locations, work mode, blocked locations, oldest posting age. Each rule records where it came from (profile fact, preference, or the person) and whether it skips jobs or guides the AI. Has a version and approval date.
- **Company**: a name, city, website, careers link and the resolved job board, with where it came from (shipped or added by the person), whether the person edited or hid it, and when it was last checked.
- **Search run**: one press of Search now: when it ran, which rules version, which companies were read, counts of jobs found, skipped by rules, judged by the AI, kept and merged, failures per company, the batches finished, the companies not yet read, why it stopped (finished, stopped by the person, budget reached, out of credit), and the actual AI cost.
- **Job**: one open position: title, company, location, work mode, posted date, description, pay if stated, where it was found, and its state (in Explore, skipped, restored, applied with date, no longer listed, deleted).
- **Job source**: one place a job was seen (a company board, a company careers page, or a paste) with its link and the date seen; a job can have several.
- **Relevance decision**: shown or skipped, the reason, who decided (a rule, the AI, or the person), and for AI decisions the prompt version and model used.
- **Possible duplicate**: a pair of jobs that may be the same, awaiting the person's merge or dismiss decision.
- **Check-manually entry**: a company whose board cannot be read, with its careers link and last-checked date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person with a confirmed profile can go from the home page to a list of relevant jobs, approving rules on the way, in under 5 minutes, excluding the time the sources take to respond.
- **SC-002**: A search over the shipped company list finishes within 5 minutes on a normal home internet connection, and the person sees progress throughout.
- **SC-003**: On a labelled test set of recorded postings for a synthetic profile, at least 90% of the jobs marked relevant in the answers appear in Explore, and at least 90% of the jobs in Explore are marked relevant in the answers.
- **SC-004**: On the same test set, no job matching the person's explicit exclusions (blocked locations, title words to avoid) appears in Explore.
- **SC-005**: Every job, in Explore or skipped, shows the reason for its decision and who made it; no job is placed without a visible reason.
- **SC-006**: A full search over the shipped company list costs under $0.25 in AI spend with the default model, the cost spent so far is visible throughout, and the first relevant jobs appear in Explore before the whole search finishes.
- **SC-006a**: When the budget is reached or the provider reports out of credit, 100% of finished batches are kept, no out-of-credit call is retried, the person sees the reason, and the next search reads only the companies not yet read.
- **SC-007**: A job already judged is never sent to the AI again on a later search unless the person asks; a second search with no new jobs costs nothing.
- **SC-008**: On a test set of recorded sources with known duplicates, at least 95% of true duplicates are merged into one entry, and no pair is merged unless it is certain or the person confirmed it.
- **SC-009**: When any one source fails, or the AI is unavailable, 100% of jobs from the working sources are still processed and 100% of previously stored jobs remain.
- **SC-010**: The home page shows the first screen of jobs in under 2 seconds with 1,000 stored jobs.
- **SC-011**: A set of job postings containing instructions aimed at an AI is run through every step that reads job text; in 100% of cases the instructions have no effect on decisions, rules or behaviour, and a warning is recorded.
- **SC-012**: No code path in the feature can apply to a job, send a message or contact anyone, shown by an automated check that fails the build if one is added.
- **SC-013**: In a test, deleting all data removes 100% of jobs, rules, company edits and search history.

## Assumptions

- **Delivery in slices.** Stories are ordered by priority. Stories 1 and 2 are the first deliverable: approve rules, search the shipped company list, and see the relevant jobs on the home page. Stories 3, 4 and 5 follow. Each story can be built and tested alone.
- **Only relevant jobs are shown** (clarified 2026-11-05). Explore has no "maybe" or "hidden" group. Rules skip the obvious noise for free; the AI judges what is left; skipped jobs are kept out of sight with their reason and can be restored from the search summary, as the constitution requires for anything AI hides.
- **Scoring later** (clarified 2026-11-05). Scoring picked jobs (score, matched skills, gaps, strong / moderate / stretch bands) is a later feature.
- **Cost guard** (clarified 2026-11-05). No upfront cost estimate is relied on, because it is only a guess. Safety comes from batches, judging each job once, the monthly budget cap (which already blocks a call before it runs), and stopping on the provider's out-of-credit error. Batch size is set in the plan. The constitution's "show estimated cost first" rule for batch AI actions is met by showing the cost live per batch with a Stop button; the plan records this reading in its Constitution Check.
- **Efficient model** (Ravi, 2026-11-05). The relevance check uses the cheapest model that passes its evaluation, chosen the same way as for resume reading (`docs/how-we-choose-a-model.md`); today that is the `fast` tier. Tokens are kept low by sending only the needed fields and a capped excerpt of each posting, and by judging several jobs per call if the evaluation shows quality holds.
- **Out of credit today.** Feature 001's provider adapter treats every "too many requests" response as temporary and retries it, including OpenAI's out-of-credit response (`insufficient_quota`). This feature changes that so out of credit stops and is shown, not retried.
- **Home page.** Once setup is complete, the home page becomes the Explore list, and the setup checklist stays at the top until every step is done. The existing setup flow does not change.
- **Newest first.** The default order is newest posted first; jobs without a date sort by the date they were first seen.
- **No automatic expiry.** Jobs stay until the person deletes them or they are marked "no longer listed"; nothing is removed automatically.
- **Shipped company list.** The shipped list is the 62 Chennai companies already prepared, with only the company-level facts; the 10 missing careers links are filled in before release or stay on the check-manually list. Boards were verified by a maintainer for the built-in entries.
- **Sources in scope** (Ravi, 2026-11-05). This feature covers company job boards, company careers pages and manual paste. **AI web-search discovery is moved to a later feature** (the "future pipeline"). The optional free job boards (RemoteOK, Remotive, Himalayas, We Work Remotely, Arbeitnow, HN "Who's hiring"; clarified 2026-11-05), job-alert emails and aggregator interfaces (Adzuna, Jooble, Careerjet) are the later "more sources" feature.
- **Applied list and Gmail** (Ravi, 2026-11-05). This feature adds "I applied" and the Applied list. Filling that list from the person's Gmail (application confirmation emails, read-only) belongs to the applications feature (003), together with statuses, reminders and contacts; jobs marked applied here and jobs found in Gmail end up in the same list there.
- **Site terms.** Nothing in this feature fetches from LinkedIn, Naukri, Indeed, Cutshort or similar sites; jobs from them come in only by paste.
- **Language.** English only, as for the rest of the product.
- **Dependencies.** Requires feature 001 (confirmed profile, preferences, AI key and budget guard, untrusted-text screening, background runs, delete-all). Relies on the bundled job-board scanner named in the project constitution; whether its terms and any browser requirement allow what this feature needs is checked in the plan.
- **Open for the plan.** Whether the bundled scanner needs a browser (image size) and what its terms allow; how many of the shipped companies resolve to a readable board; how the labelled relevance test set for SC-003 is built; the relevance prompt and its evaluation set (constitution IV).
- **Single user.** One user per install; no sharing, accounts or notifications. Reminders and application tracking belong to a later feature.
