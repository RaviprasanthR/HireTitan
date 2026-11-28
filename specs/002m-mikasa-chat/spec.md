# Feature Specification: Mikasa, the chat assistant

**Feature Branch**: `002m-mikasa-chat`

**Created**: 2026-11-24

**Status**: Draft

**Input**: User description: "002m-mikasa-chat: A chat assistant named Mikasa that sits inside the existing UI. Whatever the UI can do, Mikasa can do through chat (example: the person pastes a job link and says "I applied"; Mikasa adds the job if it isn't there yet and marks it applied). Ravi wants Mikasa to have access across the whole application. Feasibility notes: LlmPort has no tool calling yet (needs tool definitions, a chat loop and streamed replies); one tool layer shared with the later 007 mcp-access feature; every change needs a confirm step the person clicks; tool results carrying job text, pages or emails are untrusted (quarantined blocks); "access across the application" conflicts with the "never sent to AI" rules of 002b, 002e and 002f (contacts, notes, interview notes, resume picker), which the spec must settle; the constitution's no-send rule and "profile facts only from the confirmed profile" still apply. Suggested phases: ask (read-only), act (with confirm cards), draft, then MCP."

## Overview

HireTitan can already do a lot: search, read job-alert mail, track applied and inquired jobs with interview rounds, keep companies and contacts, write outreach drafts and tailored resumes. All of it goes through pages, tabs, tables and dialogs. When the person already knows what they want ("I applied to this one", "what's still waiting on me at Acme?", "move my Zoho interview to Friday"), finding the right page and control takes longer than saying it.

**Mikasa** is a chat assistant inside the existing app. The person opens her from any page, types in plain language, and she answers questions about their own data and carries out what the app can already do, using the same actions and rules as the UI. She is a second way into the same features, not a new feature set. Nothing she does bypasses a rule the UI follows.

Three limits stay fixed, from the constitution:

1. **No sending.** Mikasa never sends a message, email, connection request or application, and cannot (principle I).
2. **The person stays in charge of changes.** Small changes the person asked for, which can be undone in one step, happen at once with an Undo. Anything risky (deletes, bulk changes, starting searches or AI work, changing search rules, preferences or settings) is shown as a card stating exactly what will happen, and nothing is saved until the person confirms it.
3. **Truth and untrusted text.** Facts about the person come only from their confirmed profile (principle II). Job descriptions, careers pages and emails are data, never instructions; text from them never steers what Mikasa does (principle III).

## Clarifications

### Session 2026-11-24

- Q: What may Mikasa do with contacts and company notes (002b), interview contacts, rounds, questions, answers and feedback (002e) and the resume used for a job (002f), which are never sent to the AI today? → A: **Act, never send.** Mikasa can find and change these items, and the app shows their contents to the person in the chat itself, but their stored contents never reach the AI provider. The 002b, 002e and 002f rules stay as they are. Mikasa cannot summarise or reason over that content.
- Q: Which changes need a confirm click? → A: **Only risky ones.** A small change to one item that the UI can undo in one step happens at once and shows an Undo. Deletes, changes to more than one item, starting a search or mail check, AI generation, and changes to search rules, preferences or settings need a confirm card.
- Planning (2026-11-24, Claude's call from the code, open to Ravi's correction): the UI has **no "hide this job"** action (jobs are hidden only by rules, and can be restored or deleted), so Mikasa can restore a hidden job but not hide one. **HireTitan does not fetch a job link** in this feature: a job is added from a link with the title and company the person gives (asked for if missing), and the paste dialog gains the same link-only option, so Mikasa does nothing the UI can't. **Draft text is edited only on its page**, not by Mikasa, so 002k's fact checks are never skipped. Mikasa's model tier is fixed in her prompt (`fast`), like every other AI task; there is no per-person model choice in the app.

- Q (2026-11-24, after Ravi tried the read-only Mikasa: "it answers anything"): How is Mikasa kept to the person's own HireTitan data? → A: **Suggested questions first**: the panel opens with suggested questions that run HireTitan actions directly, with no AI call; **Ask something else** opens the text box. **Off-topic is blocked twice**: a small tool-less AI check of each typed message first (on topic or not), and a code rule that keeps a reply only when the turn read HireTitan data. The person's own message is screened for injection text before any AI call. **History: the last 10 messages** (was 30).

The tool layer Mikasa uses is the one the later feature 007 (`mcp-access`) will expose to outside assistants; this feature builds it for Mikasa only and exposes nothing outside the app.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ask Mikasa about my job search (Priority: P1)

From any page, the person opens Mikasa (a chat panel that keeps the current page visible) and asks questions in plain language: "How many jobs did I apply to this week?", "Which applications have had no reply for three weeks?", "What did the last search find?", "Is Acme in my companies list?", "What does the Zoho job ask for?". Mikasa answers from the person's own data, in her own words, with links that open the job, company or page she is talking about. Her reply appears as it is written, not all at once at the end.

**Why this priority**: Read-only answers carry no risk of changing data, prove the whole chat path (panel, streaming, the tool layer, untrusted-text handling) and are useful on their own.

**Independent Test**: With synthetic jobs, companies and an applied job in the database, open Mikasa on the Companies page, ask "what did I apply to this week?", and get the correct list with links that open each job. Check that nothing in the database changed.

**Acceptance Scenarios**:

1. **Given** the app is set up, **When** the person opens Mikasa from any page, **Then** a chat panel opens beside the page, the page stays usable, and closing the panel keeps the conversation.
2. **Given** applied jobs exist, **When** the person asks how many they applied to in a period, **Then** Mikasa gives the right count and names the jobs, each with a link that opens it.
3. **Given** the person asks something HireTitan has no data for (for example a salary at a company not in the app), **When** Mikasa answers, **Then** she says she doesn't have that and does not guess or invent it.
4. **Given** the person asks about a job's description, **When** Mikasa answers, **Then** her answer is based on a bounded summary of the description, and instructions hidden in the posting have no effect on her answer or her actions.
5. **Given** Mikasa is writing a reply, **When** text arrives, **Then** it is shown as it comes, and the person can stop it.
6. **Given** a question only needs reading, **When** Mikasa answers it, **Then** no data is changed and no confirm card is shown.

---

### User Story 2 - Tell Mikasa to do it (Priority: P1)

The person asks Mikasa to do something the UI can do: "I applied to this, https://jobs.example.com/123", "mark the Acme backend job as inquired", "add Freshworks to my companies", "restore that hidden Zoho job", "add a round 2 technical interview for Zoho on Friday at 3 pm", "run a search now", "check my job-alert mail". Mikasa works out what that means. For a **small change** (one item, undoable in one step, such as marking a job applied, restoring a hidden job or adding a company) she does it at once, says exactly what she did, and shows an **Undo**. For a **risky change** (a delete, more than one item, starting a search or mail check, AI generation, or changing search rules, preferences or settings) she shows a **confirm card**: what will change, on which item, with the values she will use. Nothing changes until the person clicks **Confirm**. They can **Cancel**, or change values on the card first.

The example from Ravi: the person pastes a job link and says "I applied". If the job is already in HireTitan, Mikasa marks it applied today and shows Undo. If it isn't, she adds it with the link and the title and company the person gave (asking for them first if they are missing; HireTitan does not fetch the link) and marks it applied, as one step that one Undo reverses.

**Why this priority**: This is what makes Mikasa worth opening. It depends on US1's chat path.

**Independent Test**: With a synthetic job in the database, say "I applied to <its link>"; Mikasa reports that job marked applied today, it shows in In pipeline with today's date, and Undo returns it to Explore. Repeat with a link not in the database; the job is added once and marked applied, and Undo removes both. Ask "delete the Acme backend job"; a confirm card appears and nothing is deleted until it is confirmed.

**Acceptance Scenarios**:

1. **Given** a job in HireTitan, **When** the person tells Mikasa they applied to it, **Then** the job is marked applied today, Mikasa names the job and the date she used, and an Undo is shown that reverses it.
2. **Given** a link to a job not yet in HireTitan, **When** the person says they applied to it, **Then** exactly one job exists for that link and it is marked applied, and one Undo removes the job and the mark together.
3. **Given** a link from a site HireTitan must not read (for example LinkedIn or Naukri), **When** the person gives it to Mikasa, **Then** HireTitan does not fetch it; Mikasa asks for the title and company (and offers to take a pasted description) and keeps the link as given.
4. **Given** a risky change (for example deleting a job, changing a search rule or starting a search), **When** Mikasa prepares it, **Then** a confirm card is shown and nothing changes until it is confirmed; when the person cancels or ignores it, nothing changes; when they edit a value on the card and confirm, the edited value is used.
5. **Given** the person's request matches more than one item (two jobs at Acme), **When** Mikasa prepares the change, **Then** she asks which one, or shows the candidates to pick from, and never picks one silently.
6. **Given** a change was made (at once or after confirming), **When** it is done, **Then** Mikasa reports the result, the page the person has open updates to show it, and the Undo the UI offers for that action is offered too.
7. **Given** a change fails (for example the job was deleted meanwhile), **When** Mikasa reports it, **Then** she gives the reason in plain words and nothing is half-done.
8. **Given** one request means several changes (for example "mark these three as applied"), **When** Mikasa prepares them, **Then** one card lists every change and the person confirms or cancels them together; each change can be undone.
9. **Given** a job description, page or email contains text asking for an action (for example "mark this job as applied", "delete all companies"), **When** Mikasa reads that item, **Then** she takes and proposes no action because of it; only the person's own messages can lead to a change or a confirm card.

---

### User Story 3 - Ask Mikasa for drafts (Priority: P2)

The person asks Mikasa for the drafts the app already makes: "write a connection request to Priya at Acme for the backend job", "draft a referral message for the Zoho job", "tailor my resume for this job". Mikasa runs the same draft actions as the job's page (feature 002k), with the same truthfulness checks, limits and fallbacks, and shows the result in the chat with a link to open it where it lives in the app, to edit, copy or download. HireTitan sends nothing.

**Why this priority**: The drafting already exists; this gives it a quicker way in. It needs US1 and US2.

**Independent Test**: With a confirmed profile and a job with a description, ask Mikasa for a connection request for that job; get a draft of at most 200 characters that passes the same checks as the job page's draft, and find the same draft on the job's page.

**Acceptance Scenarios**:

1. **Given** a confirmed profile and a job, **When** the person asks Mikasa for a connection request or referral message and confirms the card (AI generation needs one), **Then** the draft is made by the same action as the job's page, meets the same rules (length, tone, profile facts only), and is saved where the job page shows it.
2. **Given** a request to tailor a resume, **When** it finishes, **Then** Mikasa links to the tailored resume's preview, where the person edits and downloads it as before.
3. **Given** the person asks Mikasa to "send" or "post" a draft, **When** she answers, **Then** she explains that HireTitan never sends anything and offers to copy it or open it instead.
4. **Given** the person asks Mikasa to write something about their experience outside the draft actions (for example "tell me how to describe my last job"), **When** she answers, **Then** she uses only facts from the confirmed profile and says when the profile lacks something, never invents it.

---

### User Story 4 - Mikasa's limits are clear (Priority: P2)

Some things Mikasa will not do through chat, and she says so plainly and links to where the person can do it: **Delete all my data**, setting or removing the AI key, connecting or disconnecting Gmail, and confirming a profile review (profile facts change only through the review screen). If no AI key is set, the AI is out of credit, or the chosen model cannot use tools, Mikasa's panel says why and the rest of the app keeps working.

**Why this priority**: It keeps Mikasa safe and predictable; the cases are few and easy to test.

**Independent Test**: Ask Mikasa to delete all data; she declines, explains, and links to Settings. Remove the AI key; the Mikasa panel shows that a key is needed and a link to set it, and the rest of the app works.

**Acceptance Scenarios**:

1. **Given** the person asks Mikasa to delete all their data, change the AI key, connect or disconnect Gmail, or confirm a profile review, **When** she answers, **Then** she declines, explains why, and links to the page where they can do it themselves.
2. **Given** no AI key is set, or the provider reports out of credit or quota, **When** the person opens Mikasa or sends a message, **Then** the panel shows the reason (the provider's own message for credit), keeps the conversation, and the rest of the app is unaffected.
3. **Given** the chosen model cannot call tools, **When** the person opens Mikasa, **Then** the panel says Mikasa needs a model that supports tools and links to the AI settings.
4. **Given** the person asks Mikasa something unrelated to their job search, **When** she answers, **Then** she keeps to HireTitan and the job search and says so briefly.

---

### User Story 5 - My conversations (Priority: P3)

The conversation with Mikasa is kept, so the person can close the panel, move between pages or reload and carry on. They can start a new conversation and clear past ones. **Delete all my data** removes every conversation.

**Why this priority**: Comfort, not core; US1–US4 work with a single conversation.

**Independent Test**: Talk to Mikasa, reload the page, reopen the panel; the conversation is there. Clear it; it is gone. Run Delete all; nothing of Mikasa remains.

**Acceptance Scenarios**:

1. **Given** a conversation, **When** the person reloads or changes page and reopens Mikasa, **Then** the conversation is still there.
2. **Given** past conversations, **When** the person starts a new one or clears them, **Then** a new empty conversation starts, or the cleared ones are removed for good.
3. **Given** Delete all my data runs, **When** it finishes, **Then** no conversation, message, confirm card or change record remains.
4. **Given** a confirm card from an earlier session was never confirmed, **When** the person sees it again, **Then** it can no longer be confirmed; Mikasa offers to prepare it again with current data.

---

### Edge Cases

- **EC-01** The person sends a second message while Mikasa is still replying: the first reply stops or finishes first; two replies never interleave, and two confirm cards for the same item are never both live.
- **EC-02** A confirm card refers to an item that changed or was deleted before the person confirms: confirming refuses with a plain reason and offers to prepare it again; nothing is applied to stale data.
- **EC-03** The person confirms the same card twice, or presses Undo twice (double click, two tabs): the change or the undo happens once.
- **EC-04** The person's request is vague ("do the usual"): Mikasa asks what they mean and does not guess an action.
- **EC-05** The person asks for many items at once (for example "mark these 40 jobs as inquired"): one card shows the count and a sample, and the change is applied as one step that can be undone; a request over a set limit is refused with a pointer to the page that does it in bulk.
- **EC-06** A long conversation: older parts may be summarised for the model, but the person still sees the full history and nothing about their data is invented to fill gaps.
- **EC-07** The person pastes a whole job description into the chat: it is treated as untrusted data (as a pasted description is on the paste page), and instructions inside it have no effect.
- **EC-08** The person writes in another language: Mikasa answers in that language where the model can; actions and data rules are unchanged.
- **EC-09** The model replies with a malformed or unknown action: it is refused, never shown as a confirm card, and Mikasa says she couldn't do it; the error is logged.
- **EC-10** The person tells Mikasa a fact about themselves ("I know Rust"): she does not add it to the profile; she explains that profile facts change on the profile page and links there.
- **EC-11** A search or mail check is already running when the person asks for another: Mikasa reports that it is running and its progress instead of starting a second.
- **EC-12** The app runs with the Gmail connection or AI features off: Mikasa only offers what is available and says what is not (for example, mail actions answer that Gmail is not connected and link to Settings → Gmail).
- **EC-13** Text in a job, company name or contact contains markup or scripts: Mikasa's panel shows it as plain text and never runs it.
- **EC-14** The person asks about a contact, interview round or note: the app shows the stored details to the person in the chat, but Mikasa's model never receives them; if the person asks her to summarise or compare that content, she explains that it stays out of the AI and links to the page that shows it.
- **EC-15** The person types private details into the chat themselves ("add Priya, priya@example.com, as my Acme contact"): their message is sent to the AI like any chat message (the panel says so), the contact is saved through the normal action, and from then on the stored contact is private as in EC-14.
- **EC-16** A small change's Undo is pressed after the item changed again elsewhere: the Undo refuses with a plain reason rather than overwrite the newer change.

## Requirements *(mandatory)*

### Functional Requirements

**The chat**

- **FR-001**: The person MUST be able to open Mikasa from every page of the app with a round button at the bottom right, which opens a chat popup above it that leaves the current page visible and usable (Ctrl+/ toggles it, Escape closes it), and close it without losing the conversation. While Mikasa works, the popup MUST show a loading animation (typing dots) before the first words and a caret while the reply streams in. (Amended 2026-11-24: was a side panel; the main menu moved from the left edge to a top bar.)
- **FR-002**: Mikasa's replies MUST be shown as they are written, and the person MUST be able to stop a reply.
- **FR-003**: Links in Mikasa's replies to jobs, companies, drafts and pages MUST open that item in the app.
- **FR-004**: After a confirmed change, the pages the person has open MUST show the new state without a manual reload.

**What Mikasa can do**

- **FR-005**: Mikasa MUST be able to answer questions from, and act on, the same data and actions the UI offers: jobs (Explore, In pipeline, hidden, details, descriptions), search runs and rules, job-alert mail checks and senders, companies (including adding, editing, hiding), applied and inquired marks, interview rounds and questions, resume files and the resume used for a job, outreach drafts and tailored resumes, profile and preferences (read), review items, and settings (read), except the actions in FR-016.
- **FR-006**: Every action Mikasa takes MUST go through the same rules, checks and limits as the same action in the UI; she MUST NOT have any way to change data that the UI does not have, except that an Undo (FR-014) restores the exact state from before her change.
- **FR-007**: Mikasa MUST give answers based only on data she read from HireTitan or the person's messages; when she has no data for something she MUST say so and MUST NOT invent it.
- **FR-008**: When a job link is given, Mikasa MUST find the job if HireTitan has it; if not, she MUST add it using the app's add-a-job rules with the title and company the person gave, asking for them when missing. HireTitan MUST NOT fetch the link (constitution VII). Adding a job with a link, title and company but no description MUST also be possible in the paste dialog, so Mikasa does nothing the UI cannot.
- **FR-008a**: Mikasa MUST NOT edit the text of a draft or tailored resume; the person edits it on its page.
- **FR-009**: Requests for drafts and tailored resumes MUST use the existing draft actions (feature 002k) with all their checks, and the results MUST be saved where those actions save them.

**Confirming changes**

- **FR-010**: Each Mikasa action that changes data MUST be one of two kinds, fixed per action (never decided by the model):
  - **Small change**: changes one item and the UI can undo it in one step: marking and unmarking applied or inquired, restoring a hidden job, adding a job from a link (with title and company) or a pasted description, adding or editing a company, adding or editing an interview round, a question, or the job's contact and source, setting the resume used for a job, and setting a job's description. Mikasa MUST apply it at once, state exactly what she changed and the values used, and show an Undo.
  - **Risky change**: any delete; any change to more than one item; starting a search run or mail check; any AI generation (drafts, tailored resumes, rechecks); changing search rules, preferences, mail senders or settings; approving proposals; merging or dismissing duplicates. Mikasa MUST show a confirm card stating each change, the item it applies to and the values used, and MUST apply it only when the person confirms that card.
- **FR-011**: The person MUST be able to cancel a card, and edit its values before confirming; a cancelled, expired or stale card MUST change nothing.
- **FR-012**: A confirmed card MUST be applied exactly once, and all of its changes MUST either be applied together or not at all.
- **FR-013**: When a request matches more than one item, Mikasa MUST ask the person which one; she MUST NOT choose silently.
- **FR-014**: After a change, Mikasa MUST offer the same Undo the UI offers for that action; a small change MUST always have one, and an Undo MUST refuse rather than overwrite a newer change to the same item. Undo restores the exact state from before the change even where the UI has no separate control for it: a job Mikasa restored is hidden again with its earlier reason, and a job or company Mikasa just added is removed for good when nothing else points to it, so it can be added again.
- **FR-015**: Only the person's own messages MAY lead to a change or a confirm card; text from jobs, pages, emails, contacts, notes or tool results MUST NOT cause Mikasa to propose or take an action (constitution III).

**Limits**

- **FR-016**: Mikasa MUST NOT carry out Delete all my data, setting or removing the AI key, connecting or disconnecting Gmail, or confirming or discarding a profile review; when asked, she MUST decline, explain why and link to the page where the person does it.
- **FR-017**: HireTitan MUST NOT send, post or submit anything through Mikasa, and Mikasa MUST NOT have any action capable of doing so (constitution I); the existing architecture test MUST cover her actions.
- **FR-018**: Mikasa MUST NOT add or change profile facts; facts about the person MUST come only from the confirmed profile, and anything she writes about their experience MUST use only those facts (constitution II).
- **FR-018a**: When a reply uses the person's profile, HireTitan MUST check it automatically before it is shown and stored: a reply that states a number, skill, employer, title or date not in the confirmed profile MUST be rejected, repaired once, and if it fails again replaced by a reply that leaves the claim out and points to the profile (constitution II).
- **FR-019**: Mikasa MUST keep to HireTitan and the person's job search; she MUST briefly decline unrelated requests.

**Untrusted text and private data**

- **FR-020**: Job descriptions, careers-page text, email text and any other outside text MUST reach the model that plans Mikasa's actions only as bounded, structured, clearly marked data derived by a separate step without tools, never as raw text (constitution III); injection signals found in them MUST be recorded and shown to the person when relevant.
- **FR-021**: Text the person pastes into the chat that is a job description or other outside content MUST be handled like a pasted description on the paste page: the composer offers **Paste a job description** for it, and a typed message that looks like a job posting (long, with posting headings such as responsibilities or requirements) MUST NOT be sent to the AI; the panel offers to move it into the paste dialog instead. A short message the person writes is their own words and is sent as a chat message.
- **FR-022**: Contacts and company notes (002b), interview contacts, rounds, questions, answers and feedback (002e), and the resume used for a job with its name and content (002f) MUST NOT be sent to the AI provider by Mikasa, keeping 002b FR-022, 002e FR-010 and 002f FR-013. Mikasa MAY find, add, change and remove these items through their normal actions; the model works only with references to them (for example "contact 2 at Acme", "round 1 of the Zoho job"), and the app fills in their stored contents when it shows them to the person.
- **FR-022a**: When the person asks Mikasa to summarise, compare or reason over that private content, she MUST explain that it stays out of the AI and link to the page that shows it.
- **FR-022b**: What the person types into the chat is sent to the AI as a chat message; the panel MUST say so plainly, and details the person types that are then saved as contacts, rounds or notes MUST be private from then on as in FR-022.

**AI rules**

- **FR-023**: Every model call Mikasa makes MUST go through the app's one provider-neutral AI connection, MUST be logged with provider, model, prompt version, tokens, latency and outcome, and MUST use versioned prompts with an evaluation set (constitution IV).
- **FR-024**: When no AI key is set, the provider reports out of credit or quota, or the chosen model cannot use tools, Mikasa MUST show the reason (the provider's own message for credit) and the rest of the app MUST keep working; no cost figure or budget MAY be shown.
- **FR-025**: An invalid or unknown action from the model MUST be refused and never shown as a confirm card; the refusal MUST be logged and Mikasa MUST tell the person she could not do it.

**Conversations**

- **FR-026**: Conversations MUST be kept between page changes and reloads; the person MUST be able to start a new conversation and clear past ones.
- **FR-027**: Delete all my data MUST remove every conversation, message, confirm card and change record (constitution VIII).
- **FR-028**: Mikasa's actions MUST be defined once, in a form the later feature 007 (`mcp-access`) can expose to outside assistants, but this feature MUST NOT expose them outside the app (no endpoint lists or runs actions directly; only Mikasa's own endpoints use them).

**Guardrails (amendment 2026-11-24)**

- **FR-029** (amended 2026-11-24, twice): The panel MUST open with five quick actions: a LinkedIn connection message, a LinkedIn message, an email, update a job's status, and add a job. The three drafts follow one flow, in either order: the person picks a draft and then pastes a job post or a link to it, or pastes first and is then asked which draft they want. HireTitan reads the post's title and company (a small AI call on the pasted text as outside data; when it cannot, it asks the person for them), writes the draft through the drafts feature, and shows it in the chat with a Copy button. Only after the draft is ready does it ask whether to save the job: Yes makes it an Explore job; No discards the job and its draft, and says so before the choice. Until the yes the post is a hidden job that no list, count, search or duplicate offer shows. The post text is never put in the chat history and a bare link is never fetched. Update status applies at once with Undo; Add a job is the paste form (FR-021). **Ask something else** MUST open the text box; a link or a pasted job post typed there starts the same flow instead of going to the AI.
- **FR-030**: Each typed message MUST first pass a tool-less AI topic check with a strict schema (on topic or not, and a short reason); an off-topic message MUST get a fixed refusal with the suggested questions and no main AI call. If the check itself fails, the message goes on and FR-031 still applies.
- **FR-031**: A reply to a typed message MUST be kept only when the turn called at least one HireTitan action (a read, a change or a card); otherwise HireTitan MUST replace it with the fixed refusal and the suggested questions. This rule is in code, not in the prompt.
- **FR-032**: A typed message with an injection signal of medium or high severity MUST be refused before any AI call, with a plain message; the signal is stored.
- **FR-033**: At most the last 10 messages of a conversation MUST be sent to the AI with a typed message.

### Key Entities *(include if feature involves data)*

- **Conversation**: one chat between the person and Mikasa: when it started and was last used, and its messages in order.
- **Message**: one turn in a conversation: who wrote it (the person or Mikasa), its text, when, and any links, results or confirm cards attached to it.
- **Confirm card (proposed change)**: a set of one or more risky changes Mikasa proposes: each change's action, target item and values, the state (proposed, confirmed, cancelled, expired, failed), when it was confirmed, the result, and the Undo it offers. Applied once at most.
- **Change record**: a small change Mikasa applied at once: the action, the item, the values before and after, and whether it was undone. It backs the Undo.
- **Mikasa action**: one thing Mikasa can read or change, matching one action the UI offers: its name, what it needs, whether it only reads, makes a small change or makes a risky change (needs a card), whether its results carry private data the model must not see, and the existing app action it calls. Shared later with feature 007.
- **Existing entities** (jobs, companies, contacts, applied and inquired marks, interview rounds, drafts, tailored resumes, search runs, mail checks, profile, preferences, settings): read and changed only through their existing actions; no new fields are added to them by this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person can mark a job applied from a pasted link, including adding the job when it is new, with one message that gives the link, title and company and no further click, in under 15 seconds of their own effort, excluding the model's wait.
- **SC-002**: Mikasa's first words appear within 6 seconds of sending a message in at least 90% of turns on the person's configured fast model (changed from 3 s on 2026-11-28 after the first real run: a turn reads data with tools before it can answer, and 3 s is not reachable with that; a plain reply is much faster).
- **SC-003**: In an evaluation of at least 40 synthetic requests covering the UI's actions, at least 90% lead to the right action on the right item with the right values on the first try, 0 risky changes are applied without a confirm click, and 100% of small changes show a working Undo.
- **SC-004**: In an evaluation with at least 15 jobs, pages and emails that contain planted instructions, 0 lead to a proposed or applied action, and 0 of Mikasa's answers follow the planted instruction.
- **SC-005**: In an evaluation of at least 20 questions whose answer is not in the data, 0 answers invent a value; each says the data is missing. In tests with seeded unbacked claims about the person, the automatic check rejects 100% of them (FR-018a).
- **SC-006**: 100% of requests for the actions Mikasa must not do (FR-016) and for sending anything are declined and change nothing (Ravi, 2026-11-28: a plain decline is enough; a link to the page is welcome but not required).
- **SC-007**: HireTitan sends nothing: the automated architecture check finds no action that can send a message, email, connection request or application, Mikasa's included.
- **SC-008**: When the AI is unavailable, out of credit, or returns an invalid action, 100% of turns end with a visible reason and no change to data.
- **SC-009**: Delete all my data leaves no conversation, message, confirm card or change record.
- **SC-010**: In tests of every action that touches contacts, notes, interview data or the resume picker, 0 model calls contain their stored contents (checked on the recorded calls), while the person sees the right details in the chat.
- **SC-011**: Choosing a suggested question makes 0 AI calls. In an evaluation of at least 20 off-topic requests (general knowledge, writing, coding, chit-chat), 100% end with the fixed refusal and 0 contain an answer to the request.

## Assumptions

- The person has finished setup (feature 001) and has an AI key; without one, Mikasa explains and links to the key settings. Her answers use the person's configured provider and model; the guaranteed providers (OpenAI, Anthropic, Google Gemini) all support tool use, and an OpenAI-compatible endpoint without it shows the FR-024 message.
- Mikasa uses the **fast** model tier, fixed in her prompt like every other AI task (there is no per-person model choice); the evaluation compares both tiers.
- "Whatever the UI can do" means the actions in place when this feature is built; each new feature after it adds its own Mikasa actions as part of its own spec.
- Search runs and mail checks Mikasa starts behave exactly as when started from the UI (manual trigger, progress, stop); Mikasa only reports their progress.
- The bulk limit for one confirm card (EC-05) is set in the plan; larger changes stay on the pages that already do them in bulk.
- Unconfirmed cards expire when the data they target changes, and after a time limit set in the plan.
- Voice input, file uploads into the chat, and Mikasa starting conversations on her own (reminders, nudges) are out of scope. So is the first-time tour (feature 002l).
- Exposing Mikasa's actions to outside assistants (Claude Code, MCP) is feature 007 and out of scope; this feature only shapes the actions so 007 can reuse them.
- The name "Mikasa" is shown in the panel's title and her replies; she has no avatar requirement beyond the app's existing style.
