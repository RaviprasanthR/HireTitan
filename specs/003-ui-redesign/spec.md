# Feature Specification: UI redesign to the HireTitan design system

**Feature Branch**: `003-ui-redesign` (cut from the `002m-mikasa-chat` tip; its PR merges after 002m's)

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "003-ui-redesign: Redesign the HireTitan app UI to the approved design system in DESIGN.md (repo root), cut from the 002m-mikasa-chat tip. Scope (Ravi, 2026-11-25): system + P0/P1. One flat lavender accent (orange retired, no gradients or glows), a graphite neutral ramp with three text roles, five stage colours used identically everywhere, Geist plus Geist Mono for figures, one card / button / link / tab / table / chip system, named transitions only. P0: Profile and Settings reachable on phones (bottom tab bar below 768px) and no sideways overflow (tables become stacked cards below 768px). P1: the job title link always opens the HireTitan job page with an explicit 'Open posting' external action; 'Check again' split into 'Re-check fit' and 'Test key'; Profile page shows the confirmed profile with 'Update from a new resume' as secondary; colour literals lifted into tokens; no transition-all or width animation; contrast at least 4.5:1 for all text. Also the generated-look fixes from the Hallmark/Impeccable/Unslop reviews: no uppercase tracked labels, no middle-dot meta strings, no side stripes, no card in card, no duplicate donut charts (one stacked stage bar), Mikasa button and avatar flat. Preserve routes, API contracts, backend, handlers, test ids and every user journey. Redesign screen by screen in the order DESIGN.md lists, each verified with screenshots at 1440, 820 and 390. Out of scope: job detail restructure (single save), Mikasa dialog focus fixes, Explore bulk actions, persistent filters."

**Source material**: `DESIGN.md` (the approved visual system, binding for this feature); the Hallmark audit record in `.hallmark/before.txt` (the baseline this feature is checked against); the Impeccable critique and Unslop review of 2026-11-25 (summarised in the Background section).

## Background

Three independent reviews on 2026-11-25 found the same root problems. The app carries two accent colours (a lavender brand and an orange action colour). Colours mean different things on different pages (green is "Applied" on Home but "Left out" on Explore; about 25 decorative coloured stripes carry no meaning). The same-looking link does two different things. On a phone, Profile and Settings cannot be reached at all and the Explore page runs off the side of the screen. Some text sits at 3.3:1 contrast. The Profile page never shows the profile. A layer of generated-looking detail (tracked capital labels, dot-joined meta lines, gradient and glowing brand marks, duplicate charts) makes the app look templated. Impeccable scored it 24/40 on Nielsen's heuristics, with consistency at 1/4.

This feature fixes the system and the P0/P1 problems without changing what the app does.

## Clarifications

### Session 2026-11-25

- Q: On Explore, should jobs that could not be checked for fit be gathered into one notice with a single "Re-check fit" action for all of them? → A: Yes. One notice above the list with one "Re-check fit" that runs the existing check for each job; Explore rows show a quiet status and no button of their own. The job page keeps its own "Re-check fit".
- Q: What should the first destination be called everywhere, given the nav says "Home" but the page title says "Jobs"? → A: "Jobs" in the top nav, the bottom bar and the page title; the route stays the same.

### Session 2026-11-26

- Q (Ravi): the charts above the Jobs tables push the table below the fold; can the analytics sit in a left section with the table on the right? → A: Yes. From 1280px wide the overview is a left column (about 320px) and the table fills the rest; below 1280px the table comes first and the overview follows it. The table is first in reading order at every width; the overview holds no focusable controls. Explore's actions (Search now, Check job-alert mail, history, summary) stay in a full-width bar above both columns.
- Q (Ravi): "I need a circular graph in the left pane too." → A: The overview shows the flow plus a donut (stages on In pipeline, what happened to the jobs found on Explore), in place of the stage bar. Legend entries are not tab stops.
- Q (Ravi): "In Home the entire page is scrolling, just the table needs to scroll"; "the left pane should not have scroll, size it accordingly." → A: From 1280px the Jobs page fits the window: title, tabs, Explore's action bar and the overview stay put and only the table scrolls, its head row kept in view. The overview is sized to fit (a 112px donut with its legend beside it, a 22rem column) and never scrolls on its own.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use every part of the app on a phone (Priority: P1)

The person opens HireTitan on a phone (390px wide). They can reach Jobs, Companies, Profile and Settings from a bar at the bottom of the screen within thumb reach. Lists of jobs and companies read as stacked cards, one per item, with the title, company, stage, date and actions visible without scrolling sideways. Nothing on any page runs past the right edge.

**Why this priority**: Today half the app is unreachable on a phone (P0). Setting up the AI key needs Settings, so a phone-only person cannot finish setup.

**Independent Test**: Open each top-level page at 390x844 and at 320 wide; tap each destination in the bottom bar; confirm every page loads, no page scrolls sideways, and every job and company row shows its key facts and actions.

**Acceptance Scenarios**:

1. **Given** the app at 390px wide, **When** the person looks at any page, **Then** a bottom bar shows Jobs, Companies, Profile and Settings with icon and label, the current one marked, each at least 44px tall.
2. **Given** the app at 390px wide, **When** the person taps Settings in the bottom bar, **Then** the Settings page opens and its tabs are usable.
3. **Given** the Explore page at 390px wide with several jobs, **When** the page renders, **Then** the page width equals the screen width and each job shows as a card with title, company, location, stage or source, and its actions.
4. **Given** the app at 768px wide or more, **When** any page renders, **Then** the navigation is the top bar and lists are tables, as today.
5. **Given** the Mikasa chat button on a phone, **When** the bottom bar is shown, **Then** the button sits above the bar and covers no row action or bar item.

---

### User Story 2 - Colours and links mean one thing everywhere (Priority: P1)

The person learns once what a colour or a link does and can rely on it on every page. Each pipeline stage (inquired, applied, interview scheduled, round cleared, failed) has one colour, used the same way in chips, charts and the job page. Lavender always means "you can act here or this is selected". Clicking a job title always opens the job's page inside HireTitan; the original posting opens only from an action labelled "Open posting" marked as leaving the app. Buttons say exactly what they do: the job-fit check reads "Re-check fit", the AI key check reads "Test key".

**Why this priority**: Inconsistency is the weakest heuristic (1/4). Clicking a title on Explore today leaves the app in a new tab without warning, while the same-looking title on the Pipeline tab does not.

**Independent Test**: Visit the Pipeline tab, Explore, a job page, Companies and Settings; for each stage, compare its colour in every place it appears; click a job title on the Pipeline tab and on Explore and confirm both open the job page; confirm the posting opens only from "Open posting".

**Acceptance Scenarios**:

1. **Given** a job in the Applied stage, **When** it appears on the Pipeline tab, Explore, Companies or its job page, **Then** its stage is shown in the same applied colour in every place, with its name in text.
2. **Given** the Explore search summary, **When** it shows new, already known and left-out jobs, **Then** none of these uses a stage colour.
3. **Given** a job row on Explore, **When** the person clicks the job title, **Then** the HireTitan job page opens in the same tab.
4. **Given** a job page or job row with a posting link, **When** the person activates "Open posting", **Then** the posting opens in a new tab, and the control shows an external-link icon and tells screen readers it opens a new tab.
5. **Given** Settings › AI, **When** the person wants to check the key, **Then** the button reads "Test key"; **and given** a job whose fit was not checked, **Then** its job page offers "Re-check fit" and Explore offers one "Re-check fit" for all such jobs. No button reads "Check again".
6. **Given** any page, **When** the person looks for interactive elements, **Then** links, the selected tab, the focus ring and the one primary button use the single lavender accent, and nothing is orange.

---

### User Story 3 - A calm, coherent look that belongs to HireTitan (Priority: P1)

Every page uses one visual system: a graphite background and surfaces, three text roles, one card style, one button pair, one tab style, one table style, one chip style, figures in a mono face with aligned digits, sentence-case labels, and quiet motion. The two places that deserve richness, the pipeline flow on the Pipeline tab and the search funnel on Explore, are drawn once and with care; duplicate charts are gone. The brand mark is flat lavender and the wordmark is solid text, with no gradient or glow. All text is readable (at least 4.5:1 contrast).

**Why this priority**: The generated-looking details and the hard-to-read text undermine trust in an app that handles a person's career; the system also makes every later change cheaper.

**Independent Test**: Walk every top-level page and the job page at 1440x900; check against the DESIGN.md component list and the Hallmark baseline list; measure text contrast on each page.

**Acceptance Scenarios**:

1. **Given** any table, **When** it renders, **Then** its column heads are sentence case, not letter-spaced capitals.
2. **Given** any meta line (location and work mode, file type and size and date), **When** it renders, **Then** facts are separated by layout or space, not by dot characters, and no fact repeats in the same line.
3. **Given** any card or panel, **When** it renders, **Then** it has a hairline border on all sides, no coloured side stripe, and no card sits inside another card.
4. **Given** the Pipeline tab with jobs in the pipeline, **When** the overview renders, **Then** the stage counts appear once in the flow, with one slim stacked stage bar, and no donut chart repeats the same numbers.
5. **Given** the Explore page after a search or mail check, **When** the summary renders, **Then** the found / known / left out / new counts appear once.
6. **Given** the header and the Mikasa button, **When** they render, **Then** the logo, wordmark, nav highlight, Mikasa button and Mikasa avatar use flat colours with no gradient, glow or scale-up on hover.
7. **Given** any text on any page, **When** its contrast is measured against what it sits on, **Then** it is at least 4.5:1 (3:1 for icons and large text).
8. **Given** any interactive element, **When** it is reached with the keyboard, **Then** a lavender focus ring appears instantly.
9. **Given** the person's system asks for reduced motion, **When** any page is used, **Then** nothing animates except progress shown as a static state.

---

### User Story 4 - See my profile where I expect it (Priority: P2)

The person opens Profile and sees their confirmed profile (headline, skills, experience) with a way to edit it. Uploading a new resume to update it is offered as a secondary action, not as the whole page. If no profile has been confirmed yet, the page offers the upload and the "fill in by hand" path as it does today.

**Why this priority**: The confirmed profile is the only source of facts the app uses; hiding it behind "Version history" makes people think it was lost. It is P2 because the profile is still reachable today, just not where people look.

**Independent Test**: With a confirmed profile, open Profile and confirm its content shows with Edit and "Update from a new resume"; with no confirmed profile (fresh setup), confirm the upload path still shows.

**Acceptance Scenarios**:

1. **Given** a confirmed profile, **When** the person opens Profile, **Then** they see its headline, skills and experience, an Edit action and a secondary "Update from a new resume" action.
2. **Given** no confirmed profile, **When** the person opens Profile, **Then** the upload area and "Fill in by hand" are shown as the main path.
3. **Given** a confirmed profile, **When** the person chooses "Update from a new resume" and uploads a file, **Then** the existing review-and-confirm flow runs unchanged and nothing is saved until they confirm.
4. **Given** the Tailored resumes list is empty, **When** the page renders, **Then** it says plainly that there are none yet and how to make one.

---

### Edge Cases

- A job with a very long title or company name: it wraps inside its card or cell and never widens the page; buttons never wrap their label.
- A job with no posting URL: no "Open posting" action is shown (never a dead link).
- A stage count of zero: the stage shows muted, never in the accent.
- Pipeline with no jobs at all: the Pipeline tab shows its existing empty state in the new style, with no empty chart.
- Width exactly 768px: one layout applies (top nav and tables from 768px up; bottom bar and cards below).
- Landscape phone (844x390): the bottom bar does not hide content; pages remain scrollable.
- Text zoom at 200%: no text is clipped or overlaps, and bottom bar items keep their accessible names.
- The setup flow (no AI key, no profile yet): it uses the same system and stays reachable on a phone.
- The Mikasa panel open on a phone: it stays usable above the bottom bar; its behaviour is unchanged.

## Requirements *(mandatory)*

### Functional Requirements

**System and tokens**

- **FR-001**: Every colour in the interface MUST come from the named token set in DESIGN.md (neutral ramp, three text roles, one accent with its hover, ink and tint, five stage colours, three states). No component or style rule may use a colour value outside the token set.
- **FR-002**: The single accent MUST be the flat lavender from DESIGN.md. No other hue may be used for links, the selected tab, focus rings or the primary button. Orange MUST NOT appear anywhere.
- **FR-003**: The interface MUST contain no colour gradients, glows or coloured shadows (including the logo, wordmark, nav highlight, Mikasa button and Mikasa avatar).
- **FR-004**: Each pipeline stage MUST have exactly one colour (DESIGN.md "Stage colours"), used identically on every page, always next to the stage's name in text. Stage colours MUST NOT be used for anything other than their stage.
- **FR-005**: Figures (dates, counts, sizes) MUST use the mono face with aligned digits; the interface face stays as today.
- **FR-006**: All labels, table heads, tabs, chips and navigation MUST be sentence case without added letter spacing.
- **FR-007**: Meta lines MUST NOT join facts with dot characters, and MUST NOT repeat a fact within one line.
- **FR-008**: Copy MUST NOT use em or en dashes; empty values read "Not set".

**Components**

- **FR-009**: The interface MUST use one card style (hairline border all round, no side stripe, no shadow on dark) and MUST NOT nest a card inside a card.
- **FR-010**: The interface MUST use one button pair (primary, secondary) plus destructive and ghost variants as defined in DESIGN.md, with at most one primary button per view.
- **FR-011**: Every interactive element MUST show the accent focus ring immediately on keyboard focus.
- **FR-012**: Motion MUST be limited to colour, opacity and transform changes on named properties with the DESIGN.md timing; nothing may animate width, height or position; hover MUST NOT scale elements up; all motion MUST stop under reduced-motion preference.
- **FR-013**: All text MUST reach at least 4.5:1 contrast against its background; icons, large text and input edges at least 3:1.

**Navigation and layout (P0)**

- **FR-014**: Below 768px wide, the app MUST show a bottom navigation bar with Jobs, Companies, Profile and Settings (icon and visible label, current destination marked, targets at least 44px), and MUST NOT show the top navigation links.
- **FR-015**: At every width from 320px to 1920px, no page may scroll sideways.
- **FR-016**: Below 768px wide, job and company lists MUST render as stacked cards showing the same facts and actions as the table row; from 768px up they remain tables.
- **FR-017**: Page content MUST use the full width of a centred container capped at 1440px; Profile and Settings MUST NOT sit in a narrow column with an empty half.
- **FR-018**: Pages MUST reserve space so the Mikasa button never covers a row action, a bottom-bar item or the last item of a list.

**Consistency (P1)**

- **FR-019**: Activating a job title anywhere MUST open that job's HireTitan page in the same tab.
- **FR-020**: Where a job has a posting URL, an "Open posting" action MUST open it in a new tab, carrying an external-link icon and an accessible description that it opens in a new tab. Without a posting URL the action MUST NOT appear.
- **FR-021**: The job-fit re-check action MUST be labelled "Re-check fit" and the AI key check "Test key"; the label "Check again" MUST NOT remain.
- **FR-021a**: The first destination MUST be called "Jobs" in the top nav, the bottom bar and its page title; "Home" MUST NOT be used as its label. Its address does not change.
- **FR-022**: On Explore, jobs that could not be checked for fit MUST be summarised in one notice above the list, stating how many, with one "Re-check fit" action that runs the existing check for each of them. Explore rows MUST show the not-checked state as quiet text without a button of their own. The job page keeps its own "Re-check fit" action.
- **FR-023**: The Pipeline tab's overview MUST show stage counts once (the flow plus one stacked stage bar); the Explore summary MUST show its counts once. Chart legends MUST NOT be keyboard tab stops.
- **FR-023a**: On the Jobs page (In pipeline and Explore), the table MUST be visible without scrolling past charts: from 1280px wide the overview (counts, flow, stage bar or funnel) MUST sit in a left column beside the table; below 1280px it MUST follow the table. The table MUST come first in the reading order, and the overview MUST contain no keyboard tab stops. From 1280px the page MUST NOT scroll on these tabs; only the table scrolls, with its head row in view, and the overview MUST fit without scrolling of its own. The overview shows the flow and a donut.
- **FR-024**: In the pipeline flow, the stage with the largest count MUST be emphasised and a stage with a zero count MUST be shown muted; "In pipeline" MUST be shown as a total beside the flow, not as a stage in it.

**Profile (P1/P2)**

- **FR-025**: With a confirmed profile, the Profile page MUST show the profile's headline, skills and experience, an Edit action, and a secondary "Update from a new resume" action that starts the existing upload-and-review flow.
- **FR-026**: Without a confirmed profile, the Profile page MUST keep the current upload and "Fill in by hand" path as its main content.
- **FR-027**: An empty Tailored resumes list MUST say there are none yet and how to make one.

**Preservation**

- **FR-028**: Routes, server contracts, data, handlers and existing test ids MUST be unchanged; every existing user journey MUST still complete.
- **FR-029**: The honest product copy ("HireTitan never sends anything", the Settings privacy line, the injection warning) MUST be kept word for word.
- **FR-030**: The redesign MUST NOT add any outbound action, any new data collection or any new external request (fonts are served by the app).

### Key Entities

- **Design token**: a named colour, size, radius or timing value from DESIGN.md that every screen reads; the single place a visual value is defined.
- **Pipeline stage**: one of inquired, applied, interview scheduled, round cleared, failed; carries a name and its one stage colour.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At 390px and 320px wide, all four top-level destinations are reachable in one tap from every page, and 0 pages scroll sideways at any width from 320 to 1920px.
- **SC-002**: 0 text elements below 4.5:1 contrast on the Pipeline tab, Explore, Companies, a job page, Profile, Settings and the Mikasa panel (today: 64 on Companies alone).
- **SC-003**: Each of the five stages shows the same colour in 100% of the places it appears; 0 decorative coloured stripes remain (today about 25).
- **SC-004**: 0 colour values outside the token set (today about 170), 0 catch-all transitions and 0 width animations, as reported by a re-run of the Hallmark checks against the baseline record.
- **SC-005**: Every Floor finding in the Hallmark baseline (`.hallmark/before.txt`) is resolved, except findings recorded as kept with their reason.
- **SC-006**: A re-run of Impeccable's critique scores Consistency and Standards at 3 or more (today 1) and the total at 28/40 or more (today 24).
- **SC-007**: 100% of existing automated tests and end-to-end journeys pass without changing their assertions about behaviour (wording updates are limited to the labels renamed by FR-021 and FR-021a).
- **SC-008**: With a confirmed profile, the profile's content is visible on Profile within the first screen at 1440x900 and 390x844.
- **SC-009**: Every redesigned screen has been reviewed in screenshots at 1440, 820 and 390 wide before the next screen starts.

## Assumptions

- Dark theme only, as today; a light theme stays out of scope.
- The Geist mono family is added as a locally served font, like the current interface font; no font is loaded from a third-party server.
- The confirmed profile is already available to the front end (it is shown today on the edit and version pages), so FR-025 needs no new server data.
- "Re-check fit" for many jobs (FR-022) reuses the existing per-job check action, run for each job in turn; no new server endpoint.
- The mobile breakpoint is 768px, matching DESIGN.md.
- Companies' table follows the same mobile card rule (FR-016) as the jobs tables.
- Renaming "Check again" changes test wording only where those buttons are found by their text.

## Out of Scope

- Restructuring the job page (one save action, description first, collapsed forms).
- Mikasa panel focus handling, scoped Escape and live-region announcements.
- Bulk actions on Explore, saved or persistent filters, keyboard shortcuts for lists.
- A light theme.
- Any change to server behaviour, AI prompts or data.
