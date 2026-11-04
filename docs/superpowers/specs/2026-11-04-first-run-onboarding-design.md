# First-run onboarding: design

Date: 2026-11-04 · Feature: `001-setup-and-profile` (added before its pull request) · Status: DRAFT, for Ravi's review

## 1. Intent

A new user who opens HireTitan for the first time currently lands on the full app: a sidebar with Home, Profile, Preferences, Review and Settings, most of them empty. That is confusing. Instead, a first-time user gets a short guided setup of centred cards, one step at a time, with no sidebar. The usual app appears only once setup is complete.

**Why:** the app is useless until there is a confirmed profile and preferences, so the first visit should lead straight to those and nothing else.

**Success:** a fresh user can go from "open the app" to "usual app with a confirmed profile and saved preferences" without seeing an empty page or needing to know where to click.

## 2. The flow (decided by Ravi)

Four cards, in order. Each shows "Step N of 4" and a progress bar. The mockup is `onboarding-flow.html` from the brainstorm session (not committed); the layout follows it.

1. **Welcome.** Greets the user, then asks "What should we call you?" (name), then **Continue**.
2. **Add your resume.** Upload a PDF or DOCX (5 MB limit, as today), **Paste text**, or **Type it in myself**. While the AI reads the resume, the card shows the existing progress steps. When the review is ready it moves to step 3 on its own.
3. **Check your profile.** The review editor (extracted profile, editable, autosaved) inside the card, then **Confirm profile**. "Type it in myself" leads to the same card with an empty profile.
4. **What are you looking for?** The preferences form with suggestions from the profile, then **Finish setup**.

After **Finish setup**, the usual app (sidebar + Home) opens and the cards never appear again.

**Coming back mid-way (decided by Ravi):** a user who closes the tab and comes back returns to the card they left.

## 3. Goals, non-goals, anti-goals

Goals:
- A fresh install shows only the onboarding cards, on any URL, until setup is complete.
- Every step reuses the existing features (upload and progress, review editor, preferences form). No second copy of their logic.
- Setup is never a dead end: a missing or rejected AI key, or an exhausted budget, still lets the user finish by typing the profile in by hand.

Non-goals:
- No job list. The "Jobs" item in the mockup's sidebar belongs to feature 002, so the sidebar after setup stays as today (Home, Profile, Preferences, Review, Settings).
- No account, login or email (single local user, unchanged).
- No changes to how extraction, review or preferences work. Only where they are shown. The one exception is that a review can now start empty, without a resume (section 4.4).

Anti-goals (a failure even if it works):
- A user losing a typed name, an upload or review edits by refreshing or closing the tab.
- A user stuck on a card with no way forward (for example waiting forever on extraction with no key).
- The sidebar or other sections showing before setup is complete.

## 4. Behaviour

### 4.1 Which card to show (server state, not browser state)

The card comes from saved data, so it survives closing the tab, a different browser, or a restart:

| Saved state | Shows |
|---|---|
| No name saved | Step 1 |
| Name saved, no profile import running, no open review, no confirmed profile | Step 2 |
| A profile import is queued, running, paused, or waiting for the injection decision | Step 2, showing that run's progress, pause message or decision dialog |
| An open profile review | Step 3, on that review |
| Confirmed profile, preferences never saved | Step 4 |
| Confirmed profile and saved preferences | The usual app |

"Setup complete" means a confirmed profile **and** saved preferences. That is also the rule the app already uses for "show Preferences only after a profile", which onboarding replaces.

**Once complete, it stays complete (my call).** Finishing step 4 stores a "setup completed" time on the server. From then on the usual app always shows, even if the user later uploads a new resume, which opens a review as normal on the Profile page. Only "Delete all my data" clears it. The table above applies only while setup is not complete, checked top to bottom: the first matching row wins. Installs that already have a confirmed profile and saved preferences when this ships are marked complete by the migration. They are not sent back to step 1 for a name.

**Preferences without a profile (my call).** The API keeps allowing preferences to be saved without a profile (FR-026 stays true for the API), but in the cards preferences come after the profile, as Ravi decided earlier. A user who has saved preferences but has no profile lands on step 2. Step 4 then shows their saved values.

### 4.2 The name

- Step 1 saves the name on the server (my call: a new nullable `display_name` on the `app.settings` singleton; the builder may choose another place in the setup module).
- The name pre-fills the profile's contact name: in a manual ("Type it in myself") profile, and in an extracted review whose name came back empty. If the resume has a different name, the review shows the resume's name. The user decides in the review, as today.
- The pre-fill is a default value in the form only (my call). It is the user's own typed name, never AI output, so it does not change extraction provenance (FR-022). Once autosave stores the draft, it is simply part of what the user saved.
- After setup, Home greets the user by name.

### 4.3 Missing key, rejected key, budget

- Step 2 checks the AI status (`GET /status`). If the key is missing or rejected, the card says so ("Reading a resume needs an AI key. Add OPENAI_API_KEY to .env and restart, or type your profile in yourself.") and **Type it in myself** stays available. Uploading still works: the run pauses as today and continues after the key is fixed.
- A run paused on the budget shows the existing pause message. The onboarding layout has a small footer link to **Settings** (my call) so the cap can be raised without the sidebar. Settings opens inside the onboarding layout, with a "Back to setup" link.

### 4.4 "Type it in myself" autosaves (decided by Ravi)

- Choosing **Type it in myself** opens an empty profile review with no resume file, which autosaves like an extracted review (FR-016). Closing the tab and coming back lands on step 3 with what was typed. **Confirm profile** creates the first version as `manual`.
- This is the one backend change to how reviews work. A review with no resume file and no AI provenance, created by the user, alongside the existing extraction reviews. The existing "manual entry" choice after an injection warning already opens an empty review, so the builder should reuse that path where possible.
- The one-shot `POST /profile/versions` stays for editing an already-confirmed profile (Profile → Edit).
- If a profile import is still queued, running, paused or waiting for the injection decision when the user picks **Type it in myself**, the app asks "Stop reading the resume and type your profile in yourself?" and on yes cancels that run (my call). A refresh never bounces back to the old import.

### 4.5 Back links (my call)

- Step 2 has **Back**, which returns to step 1 to change the name.
- Step 3 has **Back to upload**, which discards the open review after a confirmation ("Discard this profile and upload a different resume?"), using the existing discard.
- Step 4 has no Back: the profile is already confirmed. It can be edited later from Profile.

### 4.6 After setup

- The usual shell, as today. With onboarding in place, the "Preferences hidden until a profile is confirmed" rule (commit `8fc4e3f`) is no longer needed and can be removed.
- Home keeps its checklist, which will be all done except a key that later goes missing or rejected, and gains the greeting.
- "Delete all my data" (FR-035, Phase 6) also clears the name and the "setup completed" time, so the app returns to step 1.

## 5. Constraints

- Constitution and existing rules apply: TDD with tests named after requirement IDs, no personal data in fixtures, AI never invents profile facts, nothing is sent anywhere.
- Same palette (Deep Obsidian / Titan Blue with gradients) and WCAG AA contrast. Cards stay usable at phone width and by keyboard only.
- The spec changes: FR-027 (sidebar) applies only after setup; new requirements cover the onboarding flow, resume-at-card and the name. These go into `specs/001-setup-and-profile/spec.md`, `plan.md` and new tasks in `tasks.md` (Spec Kit flow) before any code.

## 6. Left to the builder

- Where onboarding state comes from in the API: extend `GET /status`, or add a small `GET /onboarding` endpoint.
- How the existing upload, review and preferences components are split so they render inside a card and on their own pages.
- Routing details (for example a `/setup` route, or one guard around the shell that renders the cards instead).
- Wording on cards, beyond the texts quoted above.
