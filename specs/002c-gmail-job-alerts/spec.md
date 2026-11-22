# Feature Specification: Gmail job alerts

**Feature Branch**: `002c-gmail-job-alerts`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Connect the person's own Gmail (read-only) to HireTitan and read job-alert emails from job sites (LinkedIn, Naukri, Indeed, Cutshort, Instahyre, foundit and similar) so the jobs in them show up in Explore, with deduplication against jobs HireTitan already knows (from searches, pasted jobs and earlier alerts) and across alerts that repeat the same job. Feature folder name: 002c-gmail-job-alerts (the baseline's 002c more-sources, Gmail part only; aggregator APIs stay for later). Application-update mail (applied confirmations, rejections, interview invites) is the NEXT feature, not this one, though the Gmail connection built here must be reusable by it."

## Context

Job sites such as LinkedIn, Naukri, Indeed, Cutshort, Instahyre and foundit offer job seekers no public search API, and HireTitan must never scrape them. The one permitted route to their jobs is the alert emails they already send to the person's own inbox (requirements baseline §4; constitution: "the user's own email inbox (read-only)"). This feature reads those alerts, turns each job in them into an Explore entry, and keeps the list free of repeats. It reads mail only; it never sends, deletes, labels or changes anything in the mailbox.

## Clarifications

### Session 2026-11-18

- Q: When should HireTitan check mail, given each check reads only the last 24 hours? → A: Automatically once a day while HireTitan is running, plus the "Check job-alert mail" button and Search now.
- Q: May an alert email's text be sent to the AI provider to read the jobs out of it? → A: Fixed per-site readers first, with no AI; only an email they cannot read goes to the AI (sanitised, delimited, strict bounded output).
- Q: What happens to alert jobs from companies not on the company list? → A: They are shown in Explore; the search rules still filter them; the company is not added to the list.
- Q: Should the AI relevance check judge alert jobs that have no description? → A: No. Alert jobs are filtered by the rules only and marked "not checked by AI"; the AI check runs once the person pastes the description.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect my Gmail, read-only (Priority: P1)

The person opens Settings, follows a short guide to create their own Google sign-in credentials (each self-hosted install uses its own), and connects their Gmail. HireTitan asks Google only for permission to read mail. Settings then shows the connected address, when mail was last checked, and a Disconnect button.

**Why this priority**: nothing else in this feature (or the next one, application updates) works without the connection, and it is where the person decides to trust HireTitan with their inbox.

**Independent Test**: follow the guide on a fresh install, connect a test Gmail account, see "Connected as …" in Settings, then disconnect and see that HireTitan no longer holds any access.

**Acceptance Scenarios**:

1. **Given** Gmail is not connected, **When** the person opens Settings, **Then** they see what connecting does ("HireTitan reads job-alert emails from the senders listed; it never sends, deletes or changes mail"), a link to the setup guide and a Connect button.
2. **Given** the person has entered their own Google credentials, **When** they press Connect and approve in Google's own window, **Then** Settings shows "Connected as <address>" and the only permission granted is read-only access to mail.
3. **Given** Gmail is connected, **When** the person presses Disconnect and confirms, **Then** HireTitan stops any running check, revokes its access with Google, forgets the stored access and the records of emails read, and Settings shows "Not connected"; jobs already added from alerts stay in Explore.
4. **Given** the person's access has expired or was revoked in their Google account, **When** HireTitan next tries to read mail, **Then** it stops, says "Gmail access has ended. Reconnect to keep reading job alerts." and offers Reconnect; nothing else breaks.
5. **Given** the person has not set up Google credentials, **When** they press Connect, **Then** HireTitan explains which two values are missing and links the guide, instead of failing.

---

### User Story 2 - Jobs from my alert emails appear in Explore (Priority: P1)

With Gmail connected, HireTitan checks once a day on its own while it is running; the person can also press "Check job-alert mail" (or run "Search now", which also checks mail). HireTitan reads new alert emails from the known job-site senders, takes out each job they list (title, company, location, link, the site it came from, the alert's date) and adds the new ones to Explore, marked with where they came from, e.g. "Email alert · LinkedIn". The jobs go through the person's approved search rules like any other job.

**Why this priority**: this is the value of the feature: jobs from sites HireTitan cannot search show up next to the others without the person copying them by hand.

**Independent Test**: with a connected test mailbox holding synthetic alert emails from three sites, check mail and see each listed job once in Explore with its site, link and alert date; jobs the rules leave out are in the check's summary with their reason.

**Acceptance Scenarios**:

1. **Given** Gmail is connected and the mailbox holds alert emails from listed senders, **When** the person checks mail, **Then** every job in those alerts that passes the rules appears in Explore with its title, company, location (when the alert gives one), the link to the posting on the site, the site's name and the alert's date.
2. **Given** a check has run, **When** the person checks again with no new alert emails, **Then** nothing is added and the summary says "No new job-alert emails since <time>".
3. **Given** an alert email lists ten jobs, **When** it is read, **Then** all ten are taken out, not only the first, and the summary counts "1 email, 10 jobs".
4. **Given** an alert job is left out by the person's rules (for example a title with an avoid word), **When** the check ends, **Then** it is not in Explore and the check's summary lists it with the rule's reason and a Restore action, as for searched jobs.
5. **Given** an alert job has no description (alerts carry only a summary), **When** the person opens it in Explore, **Then** it says the description is not known yet, links to the posting, and offers "Add the job description" (paste); HireTitan never fetches the posting page from these sites.
6. **Given** an alert email contains text that looks like instructions to an AI, **When** it is read, **Then** the instructions have no effect, the jobs are still read, and the job shows "This email contains text that looks like instructions to an AI. HireTitan ignored it."
7. **Given** a mail check is running, **When** the person looks at Explore, **Then** they see that mail is being checked and can stop it; jobs read so far are kept.

---

### User Story 3 - No repeats: one job, however many alerts mention it (Priority: P1)

Alert emails repeat jobs: the same LinkedIn job comes in the daily and the weekly alert, Naukri sends it again three days later, and the company's own job board was already searched. The person sees each job once.

**Why this priority**: without deduplication the alerts flood Explore with copies, which is worse than not reading them.

**Independent Test**: load synthetic alerts in which the same posting appears in four emails (two sites, two dates, one link with tracking parameters) and once on a searched company board; after checking mail, Explore shows the job once, its sources list every place it was seen, and a near match from another site waits in "Possible duplicates".

**Acceptance Scenarios**:

1. **Given** the same posting link appears in several alert emails (with or without tracking parameters), **When** they are read, **Then** there is one job, and its sources list each alert it came in with its date.
2. **Given** a job from an alert has the same posting link as a job already known (from a search, a paste or an earlier alert), **When** it is read, **Then** no new job is added; the known job gains the alert as another source.
3. **Given** a job from an alert has a different link but the same company, the same known city and an almost identical title as a known job, **When** it is read, **Then** it is added and the pair is shown in "Possible duplicates" for the person to Merge or mark Not the same; nothing is merged without them.
4. **Given** a job from an alert is almost certainly a job already in the person's pipeline (applied or inquired: same company, same known city, title the same but for punctuation or a letter), **When** it is read, **Then** it is not listed again in Explore, and the summary says "Already in your pipeline as <title>".
5. **Given** the person deleted a job or marked two jobs Not the same, **When** a later alert mentions it again, **Then** the deleted job does not come back and the pair is not proposed again.
6. **Given** an email has been read once, **When** mail is checked again, **Then** that email is not read a second time.

---

### User Story 4 - Choose which senders count as job alerts (Priority: P2)

HireTitan ships a list of the job-alert sender addresses of the common sites. In Settings the person sees that list, can switch a site off, and can add a sender (for example a niche board or a recruiter's weekly digest). Only mail from senders on the list is ever read.

**Why this priority**: it keeps HireTitan out of the rest of the inbox and lets the person cover sites the built-in list misses; the built-in list works for most people without it.

**Independent Test**: switch LinkedIn off and add a custom sender; check mail; LinkedIn alerts are not read, the custom sender's emails are, and no other mail was opened.

**Acceptance Scenarios**:

1. **Given** the built-in list, **When** the person opens the sender list, **Then** they see each site with its sender addresses and an on/off switch, all on by default.
2. **Given** the person adds a sender address, **When** mail is checked, **Then** emails from that sender are read like alerts; if no job can be read from one, the summary says "No jobs found in 1 email from <sender>" instead of failing.
3. **Given** a site is switched off, **When** mail is checked, **Then** its emails are not read.
4. **Given** any check, **When** HireTitan asks Google for mail, **Then** it asks only for messages from enabled senders within the time window; it never lists or opens other mail.

---

### User Story 5 - The last 24 hours, and what a check found (Priority: P3)

Every check reads the alert emails received in the last 24 hours (the person's decision, 2026-11-18: job alerts are daily, so a day's mail is what matters). Emails already read in an earlier check are skipped. After each check the person sees a short summary: emails read, jobs found, new, already known, left out, possible duplicates, and emails that could not be read.

**Why this priority**: useful feedback, but the fixed window works without any setting.

**Independent Test**: on a mailbox with alerts spread over three days, check mail and see only the alerts of the last 24 hours counted, with a summary whose numbers add up; check again an hour later and see the same emails skipped as already read.

**Acceptance Scenarios**:

1. **Given** Gmail is connected and HireTitan has been running, **When** a day has passed since the last check, **Then** HireTitan checks on its own and the summary is available in the same place as a manual check's.
2. **Given** alerts received over the last three days, **When** the person checks mail, **Then** only those received in the last 24 hours are read.
3. **Given** a check read some emails, **When** the person checks again within 24 hours, **Then** those emails are skipped and only alerts that arrived since are read.
4. **Given** a check ends, **When** the person looks at the summary, **Then** the counts add up: jobs found = new + already known + left out + already in pipeline.
5. **Given** Settings, **When** the person looks at the Gmail section, **Then** it says "Each check reads job-alert emails from the last 24 hours" and when the last check ran, so a person who has not checked for days knows older alerts were not read.

---

### User Story 6 - A clear Settings page: AI key, Gmail set-up as a flow, senders, data (Priority: P2)

*Added 2026-11-23 (Ravi: "properly style and organize settings ... a proper visual flow for setting up gmail connection, list of senders, options to configure api key via ui, segregate everything clearly"; folded into this feature's Phase 9).*

Settings is one long column today: the AI key status (with "edit `.env` and restart"), the Gmail section, and Delete all my data. The person wants it organised into clearly separate parts, the Gmail set-up shown as a sequence of steps that says which are done, the sender list shown clearly by site, and the AI key entered on the page instead of in `.env`.

**Why this priority**: setting up Gmail and the AI key are the two places a new person gets stuck; the features work without this, but are hard to set up.

**Independent Test**: on a fresh install with no key and no Gmail, open Settings: three separate parts (AI, Gmail job alerts, Your data) with a short index; type an OpenAI key and save: it is checked and shows "working" without a restart, and it never appears again on the page or in any answer; the Gmail part shows numbered steps (Google client, Connect, Senders, First check) with the first one open and the others waiting; complete them one by one and see each marked done.

**Acceptance Scenarios**:

1. **Given** Settings, **When** the person opens it, **Then** it has separate parts, AI, Gmail job alerts and Your data, each with its own heading and a short line saying what it is for, and an index at the top that jumps to each part.
2. **Given** no AI key, **When** the person types an OpenAI key and saves, **Then** the key is checked with the provider, the status shows "working" (or the provider's reason it is not), and AI tasks that were paused for the key continue, all without restarting HireTitan.
3. **Given** a saved key, **When** the person looks at the page or at any answer from the app, **Then** the key itself is never shown; only whether one is set, where it comes from (this page or `.env`), and its status. They can replace it or remove it.
4. **Given** a key set in `.env`, **When** the person opens the AI part, **Then** it says the key comes from `.env` (which wins over a key saved on the page) and offers no field to change it there.
5. **Given** Gmail is not set up, **When** the person opens the Gmail part, **Then** it shows the steps in order: 1 Google client (ID and secret), 2 Connect (read-only), 3 Senders, 4 First check; each step shows done, current or waiting; only the current step is open, a done step can be reopened, and a waiting step says what it waits for.
6. **Given** Gmail is connected, **When** the person looks at the Senders step, **Then** the built-in senders are listed by site, each site with its switch and its addresses, the site's domain that is also read, and the person's own senders below with Remove and an Add field.
7. **Given** "Delete all my data", **When** the person opens Your data, **Then** it stands apart from the rest, with its warning, and also removes a key saved on the page.

### Edge Cases

- An alert email in a layout HireTitan does not recognise (a site changed its template): the email is still read with the general reader; if no job can be taken out, it is counted under "could not read" with the sender and date, and nothing is invented.
- A job in an alert has no company (some sites hide it) or no location: it is added with what is known ("Company not shown"), never with a guessed value.
- An alert link is a tracking redirect: HireTitan keeps the link as given for the person to open, and uses the posting identifier inside it, when the site's link format shows one, to recognise repeats; it never follows the redirect.
- More alert emails in a day than one check reads: a check reads at most 200 alert emails and says so when there are more ("Read 200 of 240 emails; check again to continue"); the next check skips the ones already read.
- HireTitan was not running for several days: only the last 24 hours are read when it starts again; older alerts are not, and Settings shows when the last check ran.
- No AI key, or the AI is unavailable: fixed readers still work; an email that needs the AI is counted "could not read" and is read again on a later check once the AI is back.
- Google limits or a network failure in the middle of a check: emails read so far are kept, the check ends with "Stopped: Gmail did not answer. Check again later.", and the next check continues where it stopped.
- The person disconnects while a check runs: the check stops, nothing more is read.
- Two checks at once (a double click, or Search now while a check runs): the second waits or says one is already running; no email is read twice.
- An alert written in another language: jobs are read if the general reader can; otherwise counted as "could not read".
- The same job comes from two different alert sites with different links: handled as a possible duplicate (US3 AS3), not merged.
- "Delete all my data": removes the Gmail connection, the stored access, the sender settings and every record of read emails, along with the jobs.

## Requirements *(mandatory)*

### Functional Requirements

**Connection (reusable by the application-update feature)**

- **FR-001**: The person MUST be able to connect their own Gmail account using Google credentials they create for their own install; HireTitan MUST NOT ship shared Google credentials.
- **FR-002**: The connection MUST request read-only access to mail and nothing more (no sending, composing, deleting, labelling or settings access).
- **FR-003**: HireTitan MUST store the access it receives only on the person's machine, never show it, log it or pass it to an AI.
- **FR-004**: The person MUST be able to disconnect; disconnecting MUST stop a running check, revoke the access with Google, and delete the access and the records of emails read and of checks locally. Jobs already added stay.
- **FR-005**: When the access stops working (expired, revoked, wrong credentials), HireTitan MUST stop reading, keep everything already read, and tell the person how to reconnect.
- **FR-006**: The connection MUST be a shared capability that another feature can use to read other kinds of mail, so application-update mail (the next feature) does not need a second connection.
- **FR-007**: HireTitan MUST NOT contain any ability to send, draft, delete or change mail (the no-send architecture test covers the mail adapter).
- **FR-008**: A setup guide MUST explain, step by step, how to create the Google credentials for a self-hosted install, including Google's "testing" mode for a personal app.

**Which mail is read**

- **FR-009**: HireTitan MUST read only emails from senders on the enabled sender list or from the own domain of a built-in site that is switched on (for example `naukri.com`, including its sub-domains), received within the check window, and MUST NOT list, open or store any other mail. *Amended 2026-11-22 (Ravi): the built-in addresses are unverified guesses and sites change them, so the site's domain is asked for too. Only an email in which a fixed reader finds jobs is kept; any other mail from a site's domain is dropped without the AI and without being listed as unreadable. A custom sender is still an exact address, and the AI fallback never reads mail that came only through a site's domain.*
- **FR-010**: HireTitan MUST ship a built-in list of job-alert senders for at least LinkedIn, Naukri, Indeed, Cutshort, Instahyre and foundit, which the person can switch off per site and extend with their own sender addresses.
- **FR-011**: Every check MUST read only alert emails received in the 24 hours before it starts, and MUST NOT read an email a previous check already read.
- **FR-012**: A check MUST read at most 200 emails and report when more remain.

**Reading jobs out of alerts**

- **FR-013**: For each alert email, HireTitan MUST take out every job it lists, with the title, company, location, posting link, site, and the alert's date, and MUST NOT invent any value the email does not give.
- **FR-013a**: Emails from the built-in sites MUST first be read by a fixed reader for that site, with no AI. Only an email no fixed reader can read (an unknown layout or a sender the person added) MAY go to the AI, as sanitised, delimited text with a strict, length-bounded output of job fields; a value the AI returns that does not appear in the email MUST be dropped.
- **FR-014**: Alert content MUST be treated as untrusted: sanitised, delimited and screened for instructions to an AI; signals MUST be stored and shown on the job; only structured, length-bounded job data may leave the reading step.
- **FR-015**: HireTitan MUST NOT fetch the posting pages of LinkedIn, Naukri, Indeed or the other alert sites; the person opens the link themselves and may paste the description.
- **FR-016**: Only the job data taken out of an email and the email's identifier, sender and date MAY be stored; the email's body MUST NOT be kept after it is read.
- **FR-017**: An email from which no job can be read MUST be counted in the summary as "could not read" with its sender and date, without failing the check.

**Into Explore**

- **FR-018**: Jobs read from alerts MUST go through the person's approved search rules, and those left out MUST be listed with their reason and a Restore action. They MUST NOT go to the AI relevance check while they have no description; they are marked "not checked by AI" until the person pastes the description, after which the check can run.
- **FR-018a**: Alert jobs from companies that are not on the person's company list MUST be shown like any other job (the rules still apply); reading alerts MUST NOT add companies to the list.
- **FR-019**: Each alert job MUST show where it came from ("Email alert · <site>") and its alert date; the Explore source filter MUST offer "Email alerts".
- **FR-020**: An alert job whose posting date, as the alert gives it, is more than 30 days old MUST be marked "may have closed".
- **FR-021**: While Gmail is connected and HireTitan is running, mail MUST be checked automatically once a day; checking MUST also be possible on its own ("Check job-alert mail") and MUST happen as part of "Search now". When HireTitan starts and the last check is more than 24 hours old, it MUST check soon after starting. A check MUST be stoppable and show progress, and only one check may run at a time.

**Deduplication**

- **FR-022**: Two jobs with the same posting link (after removing tracking parameters) or the same site's posting identifier MUST be one job, with every alert and other source it came from listed.
- **FR-023**: A job from an alert with a different link but the same company, the same known city and a very similar title as a known job MUST be offered as a possible duplicate for the person to Merge or mark Not the same; it MUST NOT be merged automatically.
- **FR-024**: A job almost certainly already in the pipeline (applied or inquired) MUST NOT be listed again; the summary MUST say which pipeline job it matched.
- **FR-025**: Deleted jobs and pairs marked Not the same MUST stay that way when later alerts mention them again.

**Summary and data**

- **FR-026**: Every check MUST end with a summary whose numbers add up: emails read, emails that could not be read, jobs found, new, already known, left out by rules, already in the pipeline, and possible duplicates.
- **FR-027**: "Delete all my data" MUST remove the Gmail connection, stored access, sender settings and every record of read emails.

**Settings** *(added 2026-11-23)*

- **FR-028** *(added 2026-11-23)*: Settings MUST be organised into separate parts, AI, Gmail job alerts and Your data, each with a heading and a one-line purpose, with an index at the top that jumps to each part; it MUST work at phone width and with the keyboard.
- **FR-029** *(added 2026-11-23)*: The person MUST be able to enter, replace and remove an OpenAI API key on the page. A saved key MUST be stored only in `<data_dir>/secrets/llm.json` (owner-only where the system supports it), MUST never be returned by any endpoint, shown on the page or written to a log, and MUST be checked with the provider when saved. A key in the environment (`OPENAI_API_KEY`) MUST win over a saved one, and the page MUST say so. *Amends ADR-09 ("keys in `.env` only").*
- **FR-030** *(added 2026-11-23)*: A key saved, replaced or removed on the page MUST take effect for the API and the worker without a restart, and AI tasks paused because the key was missing or rejected MUST continue once the new key works.
- **FR-031** *(added 2026-11-23)*: The Gmail part MUST show the set-up as ordered steps (Google client, Connect, Senders, First check), each marked done, current or waiting from the app's real state; only the current step is open by default and a done step can be reopened.
- **FR-032** *(added 2026-11-23)*: The Senders step MUST list the built-in senders grouped by site (switch, addresses and the site's domain that is also read), then the person's own senders with Remove, then an Add field.
- **FR-033** *(added 2026-11-23)*: "Delete all my data" MUST also remove a key saved on the page.

### Key Entities

- **Gmail connection**: the person's link to their mailbox: the address, the stored read-only access (secret), when it was made, the last successful check, and its state (connected, needs reconnecting, not connected). One per install. Shared with later mail features.
- **Alert sender**: a sender address that counts as a job-alert source: the site it belongs to, built-in or added by the person, on or off.
- **Read email**: the record that one email was read: its mailbox identifier, sender, date, how many jobs were taken out, and whether it could be read. No body.
- **Alert sighting**: one mention of a job in one alert email: the job it belongs to, the site, the posting link as given, the alert date. A job has one or more sightings, alongside its other sources.
- **Mail check**: one run of reading mail: when, the window, the counts of the summary, how it ended (finished, stopped, access ended, Gmail did not answer).
- **Job** (existing): gains "email alert" as a kind of source.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person who has a Google account connects Gmail by following the guide in under 15 minutes, the first time.
- **SC-002**: On a test set of at least 60 alert emails (at least 10 per built-in site), at least 95% of the listed jobs are taken out with the correct title, company and link, and 0 values are invented; at least 90% of the built-in sites' emails are read without the AI.
- **SC-003**: The same posting mentioned in several alerts appears as one job in 100% of the test cases that share a link or a site's posting identifier.
- **SC-004**: 0 emails from senders outside the enabled list are listed or opened during a check (shown by a recorded request log in tests).
- **SC-005**: A check of a day's alerts (up to 50 emails) finishes in under 2 minutes.
- **SC-006**: After Disconnect, HireTitan holds no mail access, and the person's Google account shows the access removed.
- **SC-007**: HireTitan can send, draft, delete or change no mail (the architecture test passes).
- **SC-008**: In every check summary, jobs found = new + already known + left out + already in pipeline.
- **SC-009** *(added 2026-11-23)*: A person with an OpenAI key and no `.env` edits gets AI working from Settings in under 2 minutes, without restarting HireTitan.
- **SC-010** *(added 2026-11-23)*: The saved key appears in 0 API responses, 0 log lines and 0 rendered pages (shown by tests that look for it).

## Assumptions

- Each self-hosted install uses the person's own Google credentials in Google's "testing" mode (the person adds their own address as a test user); Google's app verification is not needed for personal use, and access granted in testing mode may need reconnecting every 7 days, which the reconnect notice covers.
- Gmail is the only mail provider in this feature; other providers (Outlook, IMAP) are out of scope.
- Mail is checked automatically once a day while HireTitan runs, and on request; when HireTitan is not running for more than a day, the alerts of the days it was off are not read (the 24-hour window), which Settings makes visible with the last check's time.
- The window is fixed at the last 24 hours (the person's decision, 2026-11-18); alerts older than that are not read, so a person away for days misses them unless they paste the jobs. A longer first-time window is out of scope.
- Alert jobs have no description at first; only the rules judge them until the person pastes one (the existing "Add the job description" action).
- An alert job is tied to a listed company only when the names match after the usual normalisation; otherwise it stands alone.
- Built-in sender addresses are public facts about the sites, not personal data, and may ship with the product.
- Application-update mail (confirmations, rejections, interview invites) is the next feature and is not read here.
- Writing or sending mail is not part of this feature; a later feature that drafts an email needs its own constitution change.
