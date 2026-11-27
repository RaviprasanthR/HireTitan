# Research: 003-ui-redesign

All decisions below are front-end only. The backend, API contracts and data are unchanged (FR-028).
Inputs: `DESIGN.md`, `spec.md`, the Hallmark record (`.hallmark/before.txt`, `.hallmark/before.json`)
and the code as of the `002m-mikasa-chat` tip.

## R1. Where tokens live

- **Decision:** Keep the existing three-place token setup and rewrite its values: `frontend/src/theme/theme.css`
  `:root` holds every `--ht-*` value from DESIGN.md; `frontend/src/theme/tokens.ts` mirrors them for tests
  and charts; `frontend/src/index.css` `@theme` maps Tailwind utilities (`text-link`, `bg-surface`, ...) to
  the variables. The shadcn variables in `theme.css` point at the new tokens. The unused shadcn `.dark`
  block in `index.css` (46 literals) is deleted: the app is dark only and never sets `.dark`.
- **Rationale:** Components already read these names; changing values, not names, keeps the diff small.
  New names are added only for the new roles (`--ht-raised`, `--ht-hairline*`, `--ht-text-secondary`,
  `--ht-accent-*`, `--ht-stage-*`). Old names that no longer have a role (`--ht-slate`, `--ht-primary` as
  navy, `--ht-on-primary` orange, `--ht-hover-tint` rust) are removed and their users moved.
- **Guard:** a Vitest test scans `src/**/*.{css,tsx,ts}` (excluding `theme.css :root`, `tokens.ts` and
  tests) for hex, `rgb(`, `oklch(` and Tailwind arbitrary colour classes (`-[#`), failing on any hit
  (FR-001, SC-004). Hallmark's `sloplint` is the second, independent check at the end.
- **Alternatives:** CSS-in-JS theme object (rejected: new dependency, rewrites every component);
  Tailwind config palette only (rejected: charts and tests need the values in TS too).

## R2. One stage palette

- **Decision:** New module `frontend/src/theme/stages.ts`: the five stages in order, each with its
  label, CSS variable name and `tokens.ts` key. `PipelineChart` (`STATUS_COLOURS`), `PipelinePage`
  (`STATUS_TONE`), the `Pill` tones, `CompaniesPage` pipeline chips and the job page read from it. A
  `StageChip` component renders the chip from DESIGN.md.
- **Rationale:** Today three files hold three different stage palettes (FR-004, SC-003). One table is
  the smallest change that makes drift impossible; a test asserts every stage colour passes 4.5:1 on
  surface and raised, and that no stage colour is used by the Explore search summary.
- **Alternatives:** Colour per component kept in sync by convention (rejected: that is today's bug).

## R3. Mono face for figures

- **Decision:** Add `@fontsource-variable/geist-mono` (SIL OFL 1.1, same publisher as the installed Geist
  package), imported in `index.css`, exposed as `--font-mono` and a `.ht-figure` utility with
  `font-variant-numeric: tabular-nums`.
- **Rationale:** Served from the app's own bundle (FR-030, constitution VIII: no third-party request).
  OFL passes the licence gate. About 30 KB of woff2.
- **Alternatives:** System `ui-monospace` (rejected: differs per OS, breaks the type pairing);
  `tabular-nums` on Geist alone (kept as a fallback for figures in running text).

## R4. Phone navigation without duplicating links

- **Decision:** One `<nav aria-label="Main">` list in `Shell.tsx`, styled by CSS: at `>= 768px` it sits in
  the header as today; below 768px the same element is `position: fixed` at the bottom as a four-item tab
  bar (icon over label, 56px, `env(safe-area-inset-bottom)` padding). The header keeps only the logo on
  phones. The Shell root's `overflow-hidden` is removed.
- **Rationale:** One set of links means tests that query `getByRole('link', { name })` keep finding exactly
  one match, and screen readers meet one navigation landmark (FR-014, FR-028).
- **Alternatives:** A second `BottomNav` component shown below 768px (rejected: duplicate links in the DOM
  break `getByRole` queries and double the landmarks); a hamburger menu (rejected: hides destinations,
  worse for one-handed use).

## R5. Tables become cards below 768px

- **Decision:** CSS-only responsive tables. Tables that list jobs or companies get the class
  `ht-table-cards`; below 768px `thead` is visually hidden (kept for screen readers), each `tr` becomes a
  grid card, and each `td` shows its column name from a `data-label` attribute when the value needs one.
  Expandable detail rows stay directly under their card.
- **Rationale:** Same DOM at every width, so handlers, test ids and test queries are untouched (FR-016,
  FR-028); no JS media queries.
- **Alternatives:** Render a separate card list on phones (rejected: two markups to keep in step, tests
  would need both); horizontal scroll (rejected by FR-015).

## R6. No sideways scroll anywhere

- **Decision:** `overflow-x: clip` on `html` and `body`; `min-width: 0` on flex and grid children that hold
  text; long titles wrap (`overflow-wrap: anywhere` only inside table cells, `break-word` elsewhere); fixed
  `max-w-[22rem]` truncation on titles kept only at `>= 768px`. Widths checked at 320, 390, 768, 820,
  1024, 1440, 1920.
- **Rationale:** The 959px Explore overflow came from the table's intrinsic width and the nav width
  (Impeccable B). Clip plus the card layout removes both causes; clip, unlike `hidden`, keeps sticky
  elements working.

## R7. Charts shown once

- **Decision:** Remove `Donut` from `PipelineChart` and from the Explore search panel (`SearchPanel`,
  `SearchFlow`, `RunSummaryPage`). Add a small `StageBar` component (one horizontal bar split by stage
  share, labels once beside it, legend items not focusable). The `FlowChart` keeps the sequence, drops the
  icon rings for inline icons, mutes zero stages, and shows "In pipeline" as a total beside it (FR-023,
  FR-024). `Donut.tsx` is deleted once unused.
- **Rationale:** The same counts appeared twice on both pages (Impeccable, Unslop); a share is better read
  as one stacked bar.

## R8. Job title link and "Open posting"

- **Decision:** On Explore the title becomes a router `Link` to `/jobs/:id` (the job page already handles
  Explore jobs: it shows the fit status and the re-check). A ghost icon button "Open posting" with
  `ExternalLink` and visually hidden text "(opens in a new tab)" sits in the row's action cell when
  `postingLink(source.url)` is present. The job page's existing posting link gets the same treatment.
- **Rationale:** FR-019, FR-020; reuses `postingLink`, so its URL safety checks stay.

## R9. One "Re-check fit" notice on Explore

- **Decision:** `ExplorePage` counts jobs where `isNotChecked(job)`; when the count is above zero it shows
  one notice ("N jobs could not be checked for fit: no description yet") with one "Re-check fit" button
  that calls the existing re-check mutation for each job in turn (`mutateAsync` in sequence), then
  invalidates the list once. Rows show the reason as muted text without a button. The button is disabled
  while running and reports partial failures in the notice.
- **Rationale:** Clarification of 2026-11-25 (FR-022). Sequential calls reuse the existing endpoint
  without load spikes or a new server route.
- **Alternatives:** A new batch endpoint (rejected: a backend change, out of scope).

## R10. Profile shows the confirmed profile

- **Decision:** `ProfilePage` adds the existing `['profile']` query (`GET /profile`, used today by
  `ProfileEditor`). When `current` is present it renders a `ProfileSummary` (headline, skills,
  experience, the same fields `VersionView` shows) with an "Edit" link to `/profile/edit` and a secondary
  "Update from a new resume" button that reveals the existing upload area. With `current: null` the page
  is unchanged. The empty Tailored resumes text says how to make one (FR-025 to FR-027).
- **Rationale:** No new server data (confirmed: `ProfileOut { current: VersionDetailOut | null }`). The
  upload and review flow is reused untouched (constitution II: nothing saved until confirmed).

## R11. Motion

- **Decision:** Replace the six `transition-all` uses (`button.tsx`, `Shell.tsx`, `MikasaDock.tsx` x2,
  `QuickActions.tsx`, `StagedFlow.tsx`) with named transitions; the progress fill animates
  `transform: scaleX()` instead of `width`; `hover:scale-110` on the Mikasa button becomes a colour step
  and `active:scale-[0.96]`. One curve `--ht-ease: cubic-bezier(0.2, 0, 0, 1)`, durations
  `--ht-dur-fast: 120ms` and `--ht-dur-enter: 200ms`. The logo's turn while work runs stays: it is an
  activity indicator that stops when the work ends and under reduced motion.

## R12. Brand mark

- **Decision:** `brand.css` loses the gradient, `background-clip: text`, both drop-shadow glows and the
  rust edge fill: the mark is `--ht-accent`, its 3D edge a darker accent step from the tokens, and the
  wordmark solid `--ht-text`. The nav underline becomes a flat 2px accent bar. The existing test that
  confines gradients to `brand.css` becomes "no gradient or glow anywhere" (FR-003).

## R13. Mikasa on phones

- **Decision:** The Mikasa button and panel offset their bottom by `--ht-bottom-bar` (56px plus the safe
  area) below 768px. Pages add bottom padding equal to the button's footprint so it never covers a row
  action (FR-018). The panel's behaviour, focus and Escape handling are unchanged (out of scope).

## R14. Renamed labels and the tests that use them

- **Decision:** "Check again" becomes "Test key" in `AiBanner.tsx` and `settings/AiSection.tsx`, and
  "Re-check fit" in `JobDetails.tsx` and `ExplorePage.tsx`; the out-of-credit copy in `ProfilePage.tsx`
  says "press Test key". The nav and the page title say "Jobs"; the tab strip's label becomes
  "Jobs tabs". Tests that find these by text are updated in the same task as the rename
  (`AiBanner.test.tsx`, `JobDetails.test.tsx`, `Shell.test.tsx`, `ReviewNotice.test.tsx`,
  `ExplorePage.test.tsx`, `PipelinePage.test.tsx`, `e2e/job-search.spec.ts`,
  `e2e/setup-and-profile.spec.ts`). No `data-testid` changes (SC-007).

## R15. How we verify

- **Decision:** Per screen: Vitest tests first (named after FR, US and SC ids), then the change, then
  screenshots at 1440x900, 820x1180 and 390x844 through Chrome DevTools against the rebuilt dev stack on
  :8000. End of feature: the full frontend gates (vitest, tsc, eslint, build), all Playwright journeys,
  `sloplint --kept` against `.hallmark/before.json` (SC-004, SC-005 and the kept-wiring check),
  Impeccable's critique re-run (SC-006) and `impeccable polish`, run with `IMPECCABLE_NO_TELEMETRY=1`.
- **Rationale:** The same tools that set the baseline measure the result; screenshots catch what tests
  cannot (SC-009).

## R16. Branch base

- **Decision:** `003-ui-redesign` is cut from the `002m-mikasa-chat` tip, not from `master` (Ravi,
  2026-11-25), because the redesign restyles Mikasa's UI, which exists only on 002m. The 003 pull
  request is opened against `master` after 002m merges, so its diff then shows only 003's changes.
  Recorded in the plan's Complexity Tracking.
