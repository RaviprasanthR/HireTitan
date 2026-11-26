---
description: "Task list for 003-ui-redesign"
---

# Tasks: UI redesign to the HireTitan design system

**Input**: Design documents from `specs/003-ui-redesign/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/ui.md](contracts/ui.md), [quickstart.md](quickstart.md), and `DESIGN.md` at the repo root (binding visual values).

**Tests**: **Mandatory** (constitution V). Every test name carries the FR, US, SC or R id it verifies. Every task is one red → green → refactor cycle and **one commit** (made when Ravi says so, with the commit skill): write the listed tests first, watch them fail for the right reason, write the minimum code, refactor, keep the whole suite green. Visual checks (screenshots) are part of each phase's review, not a substitute for tests.

**Organization**: Setup, then the Foundational design system every story needs (tokens, stages, font, components, motion). Then US1 (phone), US2 (meaning), US3 (look, screen by screen), US4 (profile), Polish (verification and docs). Implementation pauses for Ravi's review at the end of every phase, with screenshots at 1440x900, 820x1180 and 390x844 of the screens the phase touched.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: US1 to US4 from spec.md; Setup, Foundational and Polish tasks have no story label
- Paths are under `frontend/` unless they start with `DESIGN.md`, `docs/` or `specs/`
- Frontend files have no prettier config: format new code with `--no-semi --single-quote --print-width 100`; never run plain `prettier --write` on existing files.
- Values (colours, radii, timings, sizes) come from `DESIGN.md`; never type a colour outside `src/theme/theme.css :root` and `src/theme/tokens.ts`.
- Preserve every route, request, React Query key, handler, `data-testid`, field `name` and the copy listed in contracts/ui.md "Must not change". Test wording changes only where contracts/ui.md "Changes on purpose" says so.
- After each phase rebuild the dev stack (`docker compose up -d --build`) and take the review screenshots on :8000 with Chrome DevTools. All test data is synthetic.

---

## Phase 1: Setup

- [x] T001 Record the baseline on this branch: frontend `npm run test` (count), `npm run typecheck`, `npm run lint`, `npm run build`, `npx playwright test` (count); keep `.hallmark/before.txt` and `.hallmark/before.json` as the visual baseline and add `.hallmark/` to `.gitignore`. Write the counts under a new 003 entry in `docs/CONTEXT.md`. The commit also carries `DESIGN.md` and `specs/003-ui-redesign/`. No code change.
- [x] T002 Add `@fontsource-variable/geist-mono` to `package.json` (R3), import it in `src/index.css` next to Geist, and run the licence gate (OFL 1.1) and `npm audit --omit=dev` (no new high or critical advisory). Test first in `src/theme/fonts.test.ts`: `test_R3_mono_face_bundled_locally` (the import exists and no `@import url(http` or font URL to another host appears in `src/**/*.css`; FR-030).

---

## Phase 2: Foundational (the design system; blocks every story)

**Purpose**: the tokens, stage table, components and motion every screen uses.

**⚠️ CRITICAL**: No story work starts until this phase is reviewed.

- [x] T003 Tokens (R1, data-model "Design token"). Rewrite `src/theme/theme.css :root` and `src/theme/tokens.ts` to DESIGN.md: neutral ramp `background #12151b`, `surface #181c23`, `raised #1f242c`, `hairline rgb(230 232 236 / 0.08)`, `hairline-strong rgb(230 232 236 / 0.14)`; text roles `text #e6e8ec`, `text-secondary #a8aeb8`, `text-muted #8b929d`; accent `#a99ce6`, `accent-hover #bbb0ef`, `accent-ink #16121f`, `accent-tint rgb(169 156 230 / 0.12)`; stages `inquired #7fa8d8`, `applied #6fc08d`, `interview #d6b25e`, `cleared #5ec4b6`, `failed #e2837a`; states as aliases (`success` = applied, `warning` = interview, `danger` = failed); radius `control 8`, `card 12`, `dialog 16`, `chip 6`; motion `--ht-ease cubic-bezier(0.2, 0, 0, 1)`, `--ht-dur-fast 120ms`, `--ht-dur-enter 200ms`. Point the shadcn variables at them; map Tailwind utilities in `src/index.css @theme`; delete the unused `.dark` block in `src/index.css`. Remove `slate`, navy `primary`, orange `on-primary`, `muted-small`, `heading`, `hover-tint` and move every use to its new role. Tests first: rewrite `src/theme/contrast.test.ts` pairs to `test_FR013_text_roles_meet_AA` (each text role ≥ 4.5:1 on background, surface, raised), `test_FR013_accent_ink_on_accent` (≥ 4.5:1), `test_FR013_input_edge_3_to_1`, `test_FR002_no_orange_token`; new `src/theme/tokens.parity.test.ts`: `test_FR001_css_and_ts_tokens_match`.
- [x] T004 [P] Stage table (R2, data-model "Pipeline stage"). New `src/theme/stages.ts`: the five stages in order, keys `inquired`, `applied`, `scheduled`, `cleared`, `failed` (the API's values), labels "Inquired", "Applied", "Interview scheduled", "Round cleared", "Failed", and their token names. New `src/components/StageChip.tsx` (stage text in its colour on `raised`, 1px stage colour at 30%, radius 6, 12px 500; always renders the label). Tests first in `src/theme/stages.test.ts` and `src/components/StageChip.test.tsx`: `test_FR004_five_stages_in_order`, `test_FR004_each_stage_meets_AA_on_surface_and_raised`, `test_FR004_chip_shows_label_text`.
- [x] T005 Colour guard (R1). New `src/theme/tokens.scan.test.ts` scanning `src/**/*.{css,ts,tsx}` (except `theme.css :root`, `tokens.ts` and test files) for hex colours, `rgb(`, `hsl(`, `oklch(` and Tailwind arbitrary colour classes (`-[#`, `-[rgb`): `test_FR001_no_colour_literal_outside_tokens`, plus `test_FR003_no_gradient_or_glow_anywhere` (no `linear-gradient(` except the progress bar's `repeating-linear-gradient`, no `radial-gradient(`, `conic-gradient(`, `drop-shadow(`, `bg-gradient-`, zero-offset coloured `shadow-[0_0`). Then lift every literal the scan finds into tokens (theme.css about 106, charts.css 3; brand.css is already clean after T006; the 10 component classes in `Shell.tsx`, `PageTabs.tsx`, `ProfileTabs.tsx`, `PipelinePage.tsx`, `CompaniesPage.tsx`, `QuickActions.tsx`, `MikasaDock.tsx`, `MikasaAvatar.tsx`) and replace the Tailwind stock palette classes in `CompaniesPage.tsx` and `CompanyPanel.tsx`.
- [x] T006 Brand mark flat (R12). `src/theme/brand.css`: the mark in `--ht-accent`, its 3D edge a darker accent step token, the wordmark solid `--ht-text`; no gradient, no `background-clip: text`, no drop-shadow. Update `src/components/AppName.test.tsx` and the old "brand gradient confined" test to `test_FR003_wordmark_is_solid_text` and `test_FR003_logo_has_no_glow`. Keep the logo turn (reduced motion respected).
- [x] T007 [P] Type (R3, DESIGN.md "Type"). In `src/index.css`: `--font-mono` and a `.ht-figure` utility (`font-family: var(--font-mono); font-variant-numeric: tabular-nums`); the type scale 12/13/14/16/20/24/32 as tokens; `text-wrap: balance` on page titles; weights 400/500 (600 only for the page title). Tests first in `src/theme/type.test.ts`: `test_FR005_figure_utility_uses_mono_tabular`, `test_FR006_no_uppercase_or_tracking_in_theme` (no `text-transform: uppercase` and no `letter-spacing` above 0.01em in `theme.css`, and no `uppercase` / `tracking-` classes in `src/**/*.tsx`; fixes `theme.css` `.ht-thead` and `.ht-detail-heading` and the `GmailSection.tsx` label).
- [x] T008 Buttons, focus and motion (R11). `src/components/ui/button.tsx`: one primary (accent fill, accent-ink text), secondary (hairline-strong border), destructive (danger text), ghost; height 36 with a 44px hit area on touch; named transitions (`transition-colors`, `transition-[transform,opacity]`) with the motion tokens; `active:scale-[0.98]`. One primary per view (FR-010): Jobs › In pipeline none; Explore "Search now"; job page "Re-check fit" when shown, else none; Companies "Add a company"; Profile "Edit" (or the upload when no profile); Settings none; dialogs their confirm action. Global focus ring in `theme.css`: 2px accent outline, 2px offset, no transition, on `:focus-visible`. Replace `transition-all` in `Shell.tsx`, `MikasaDock.tsx` (x2), `QuickActions.tsx`, `StagedFlow.tsx`; make `.ht-progress-fill` animate `transform: scaleX()` in `theme.css`; all motion off under `prefers-reduced-motion: reduce`. Tests first in `src/components/ui/button.test.tsx` and `src/theme/motion.test.ts`: `test_FR010_button_variants`, `test_FR012_no_transition_all`, `test_FR012_no_width_or_position_animation`, `test_FR011_focus_ring_has_no_transition`, `test_FR012_reduced_motion_stops_animation`, and in `src/components/ProgressBar.test.tsx` `test_FR012_progress_uses_scale`.
- [x] T009 Cards, chips and table base (R5, R6, DESIGN.md "Components"). In `theme.css`: one card recipe (surface, 1px hairline, radius 12, no shadow, no side stripe); remove the side stripes on `.ht-detail-card` and `.ht-search-panel` and the ~25 per-section accent border rules (`theme.css` lines 470 to 508); the table recipe (head on raised, 13px secondary sentence case, 48px rows, hairline between rows, hover raised); the `ht-table-cards` pattern (below 768px: `thead` visually hidden, each `tr` a card, `td[data-label]` shows its label); `overflow-x: clip` on `html` and `body`; `::selection` and `scrollbar-color` from tokens; container max 1440px centred, page edge 24 (16 below 768px). Tests first in `src/theme/surfaces.test.ts`: `test_FR009_no_side_stripe_rules`, `test_FR009_one_card_recipe`, `test_FR015_overflow_clip_on_root`, `test_FR016_table_cards_pattern_defined`.
- [x] T010 [P] Charts once (R7). New `src/components/StageBar.tsx` (one horizontal bar split by stage share from `stages.ts`, labels and counts once beside it in `.ht-figure`, no focusable legend items, `role="img"` with a text summary). Update `src/components/FlowChart.tsx` and `charts.css`: icons inline (no rings), zero-count steps muted, accent only on the step the caller marks, an optional total shown beside the flow. Tests first in `src/components/StageBar.test.tsx` and `src/components/FlowChart.test.tsx`: `test_FR023_stage_bar_labels_each_stage_once`, `test_FR023_legend_not_tab_stops`, `test_FR024_zero_step_is_muted`, `test_FR024_total_beside_not_a_step`.

**Checkpoint**: Review the design system on :8000 (every screen picks up the new tokens; layout unchanged yet). Screenshots of the Pipeline tab, Explore and Settings at 1440, 820, 390.

---

## Phase 3: User Story 1 - Use every part of the app on a phone (Priority: P1) 🎯 MVP

**Goal**: every destination reachable on a phone, no sideways scroll, lists as cards (FR-014 to FR-018).

**Independent Test**: at 390x844 and 320x640, open every top-level page, use the bottom bar to reach each, confirm `scrollWidth === innerWidth` and each row is a card with its facts and actions (quickstart §2).

- [x] T011 [US1] One nav, bottom bar below 768px (R4). `src/app/Shell.tsx`: keep the single `<nav aria-label="Main">`; below 768px it is fixed at the bottom (four items, icon over visible label, 56px plus `env(safe-area-inset-bottom)`, current item marked with the accent and `aria-current`), the header shows only the logo; remove the root `overflow-hidden`; a flat 2px accent bar for the active link on desktop (no gradient, no glow). Tests first in `src/app/Shell.test.tsx`: `test_US1_AS1_one_main_nav_with_four_links`, `test_FR014_nav_has_bottom_bar_class_below_md`, `test_FR015_shell_root_not_overflow_hidden`; e2e in `e2e/mobile.spec.ts` (new): `US1_AS1_bottom_bar_on_phone`, `US1_AS2_settings_reachable_on_phone`, `SC001_no_sideways_scroll_on_any_page` (390 and 320, every top-level route), `EC_landscape_phone_content_not_hidden` (844x390), `EC_zoom_200_no_clipping` (1280 at 200% zoom, nav names kept).
- [x] T012 [US1] Mikasa above the bar (R13, FR-018). `src/features/assistant/MikasaDock.tsx` and `MikasaPanel.tsx`: offset by `--ht-bottom-bar` below 768px; `src/app/Shell.tsx` main gets bottom padding equal to the button's footprint. Tests first in `src/features/assistant/MikasaDock.test.tsx`: `test_US1_AS5_dock_uses_bottom_bar_offset`, `test_FR018_main_reserves_space_for_the_dock`.
- [x] T013 [P] [US1] Pipeline table as cards. `src/features/explore/PipelinePage.tsx`: `ht-table-cards` on the table, `data-label` on cells that need a label (Date, Resume, Source), titles wrap below 768px (truncation only from 768px). Tests first in `src/features/explore/PipelinePage.test.tsx`: `test_FR016_pipeline_table_uses_card_pattern`, `test_FR016_cells_carry_labels`.
- [x] T014 [P] [US1] Explore table as cards. `src/features/explore/ExplorePage.tsx`: the same pattern; the expandable detail row stays under its card; filters wrap to one column below 768px. Tests first in `src/features/explore/ExplorePage.test.tsx`: `test_US1_AS3_explore_rows_are_cards`, `test_FR016_detail_row_follows_its_card`.
- [x] T015 [P] [US1] Companies list as cards. `src/features/companies/CompaniesPage.tsx`: the same pattern for its table. Tests first in `src/features/companies/CompaniesPage.test.tsx`: `test_FR016_companies_rows_are_cards`.

- [x] T015b [US1] Overview beside the table (FR-023a, clarification 2026-11-26). New `src/components/OverviewLayout.tsx`: a grid with the table slot first in the DOM and the overview slot placed in a left column (about 320px) from 1280px, after the table below it. `src/components/FlowChart.tsx` lays out by its container's width (`@container`), so it is vertical in the column; `charts.css` link rule to a container query. `src/features/explore/PipelinePage.tsx`: `PipelineChart` in the overview slot; `ExplorePage.tsx` and `SearchPanel.tsx`: the action bar stays on top, the counts and funnel go in the overview slot. Tests first in `src/components/OverviewLayout.test.tsx`: `test_FR023a_table_first_in_reading_order`, `test_FR023a_overview_has_no_tab_stops`; plus a check in `PipelinePage.test.tsx` that the chart renders in the overview slot.
  - Done notes (2026-11-26): T012 tests live in `src/app/Shell.test.tsx` (it renders the dock with its providers). Companies is a list, so it uses `ht-list-card` beside `ht-table-cards`. T015b pulled the Pipeline-tab part of T021 forward (FlowChart with the "In pipeline" total and the largest stage marked, StageBar, no Donut) and the Explore donut removal from T022, because the narrow column needs them; the overview is shown only when it has content (`:has(> .ht-overview:not(:empty))`). Profile tabs now wrap (they were cut off at 320px). The e2e overflow check also fails on any visible element past the right edge, since `overflow-x: clip` hides overflow from `scrollWidth`.
- [x] T015a [US1] Story review (constitution, Quality Gates): React, TypeScript and accessibility reviewers over this story's diff (Shell, MikasaDock, the three tables, e2e/mobile); fix findings with tests; rebuild the dev stack; mark the story done only after this.

**Checkpoint**: Phone review at 390 and 320 of every top-level page and the Mikasa button; desktop unchanged at 1440 and 820.

---

## Phase 4: User Story 2 - Colours and links mean one thing everywhere (Priority: P1)

**Goal**: one stage palette everywhere, one accent, consistent links and labels (FR-002, FR-004, FR-019 to FR-022, FR-021a).

**Independent Test**: quickstart §3: the same stage colour in every place, titles open `/jobs/:id`, "Open posting" only for postings, renamed buttons, no orange.

- [ ] T016 [US2] "Jobs" (FR-021a). `src/app/Shell.tsx` nav label and the Jobs page title "Jobs"; the tab strip's `aria-label` "Jobs tabs" (in `src/components/PageTabs.tsx` or its caller). Update wording in `src/app/Shell.test.tsx`, `src/features/home/ReviewNotice.test.tsx`, `src/features/explore/ExplorePage.test.tsx`, `src/features/explore/PipelinePage.test.tsx`, `e2e/job-search.spec.ts`, `e2e/setup-and-profile.spec.ts`. Tests first: `test_FR021a_nav_says_jobs` in `Shell.test.tsx` and `test_FR021a_no_home_label` (no link or heading named "Home").
- [ ] T017 [US2] "Test key" and "Re-check fit" (FR-021, R14). `src/app/AiBanner.tsx` and `src/features/settings/AiSection.tsx` say "Test key"; `src/features/jobs/JobDetails.tsx` says "Re-check fit"; the out-of-credit copy in `src/features/profile/ProfilePage.tsx` says "press Test key". Update `src/app/AiBanner.test.tsx` and `src/features/jobs/JobDetails.test.tsx`. Tests first: `test_US2_AS5_ai_key_button_says_test_key`, `test_US2_AS5_job_page_says_recheck_fit`, and `test_FR021_no_check_again_label` in `src/theme/copy.test.ts` (new: no "Check again" string in `src/**/*.tsx`), plus `test_FR029_honest_copy_unchanged` there (the "HireTitan never sends anything" lines, the Settings privacy line and the injection warning appear word for word).
- [ ] T018 [US2] Stage colours everywhere (FR-004). Replace `STATUS_COLOURS` in `src/features/explore/PipelineChart.tsx`, `STATUS_TONE` in `src/features/explore/PipelinePage.tsx`, the stage tones of `Pill`, the pipeline chips in `src/features/companies/CompaniesPage.tsx` and the job page status with `stages.ts` and `StageChip`. Explore's search outcomes (new, known, left out) use the accent and text roles, never a stage token. Tests first: `test_US2_AS1_applied_same_colour_everywhere` in `src/theme/stages.test.ts` (each consumer resolves the applied stage to the same token), `test_US2_AS2_search_summary_uses_no_stage_colour` in `src/features/explore/SearchPanel.test.tsx`.
- [ ] T019 [US2] Title link and "Open posting" (FR-019, FR-020, R8). `src/features/explore/ExplorePage.tsx` `JobCardItem`: the title is a router `Link` to `/jobs/:id`; an "Open posting" ghost icon link (`ExternalLink` icon `aria-hidden`, visually hidden "(opens in a new tab)", `target="_blank" rel="noreferrer noopener"`) in the actions cell only when `postingLink(source.url)` returns a URL. The same "Open posting" treatment for the job page's posting link in `src/features/jobs/JobDetails.tsx`. Tests first in `ExplorePage.test.tsx` and `JobDetails.test.tsx`: `test_US2_AS3_title_opens_job_page`, `test_US2_AS4_open_posting_new_tab_and_announced`, `test_FR020_no_open_posting_without_url`.
- [ ] T020 [US2] One "Re-check fit" notice on Explore (FR-022, R9). `src/features/explore/ExplorePage.tsx`: count `isNotChecked` jobs; above zero, one notice "N jobs could not be checked for fit: no description yet" with one "Re-check fit" button that runs the existing re-check mutation for each job in turn (`mutateAsync`, sequential), disabled while running, then one list invalidation; partial failures reported in the notice. Rows show the reason as muted text without a button. Tests first in `ExplorePage.test.tsx`: `test_FR022_one_notice_with_count`, `test_FR022_recheck_runs_each_job_in_turn`, `test_FR022_rows_have_no_recheck_button`, `test_FR022_partial_failure_reported`.

- [ ] T020a [US2] Story review (constitution, Quality Gates): React, TypeScript and accessibility reviewers over this story's diff (renames, stages, Explore row, notice); fix findings with tests; rebuild the dev stack; mark the story done only after this.

**Checkpoint**: Review the Pipeline tab, Explore, a job page and Companies for stage colours and link behaviour at 1440 and 390.

---

## Phase 5: User Story 3 - A calm, coherent look (Priority: P1), screen by screen

**Goal**: every screen in the system, charts once, no generated-look tells, contrast ≥ 4.5:1 (FR-003, FR-005 to FR-013, FR-017, FR-023, FR-024).

**Independent Test**: quickstart §4: screenshots of every screen at 1440, 820, 390; the Hallmark and Impeccable detectors clean for the screens touched.

- [ ] T021 [US3] Pipeline tab. `src/features/explore/PipelineChart.tsx`: `FlowChart` with "In pipeline" as a total beside it and the largest stage marked, plus `StageBar`; no `Donut`. `PipelinePage.tsx`: dates and counts in `.ht-figure`, empty cells "Not set" (no dash), sentence-case heads. Tests first in `src/features/explore/PipelineChart.test.tsx`: `test_US3_AS4_counts_shown_once`, `test_FR024_in_pipeline_is_a_total`, `test_FR008_empty_cell_says_not_set`.
- [ ] T022 [US3] Explore. `src/features/explore/SearchPanel.tsx`, `SearchFlow.tsx`, `RunSummaryPage.tsx`: no side stripe, no card inside a card, the funnel once (no `Donut`); `ExplorePage.tsx` meta line without dots and without repeating the work mode (`where` built from distinct values, separated by layout); `SearchHistoryPage.tsx` meta string without dots; delete `src/components/Donut.tsx` once unused. Tests first in `src/features/explore/SearchPanel.test.tsx` and `ExplorePage.test.tsx`: `test_US3_AS5_summary_counts_once`, `test_US3_AS3_no_nested_card`, `test_US3_AS2_meta_without_dots_or_repeats`, `test_FR007_search_history_meta_without_dots`, `test_FR010_one_primary_per_view` (Explore).
- [ ] T023 [US3] Job page. `src/features/jobs/JobDetails.tsx` and its cards: the neutral card recipe (no per-section accent), the stage chip at the top, figures in `.ht-figure`, "Not set" for empty values. Layout and save behaviour unchanged (out of scope). Tests first in `JobDetails.test.tsx`: `test_US3_AS3_job_cards_have_no_stripe`, `test_FR004_job_page_shows_stage_chip`, `test_FR010_one_primary_per_view` (job page).
- [ ] T024 [US3] Companies. `src/features/companies/CompaniesPage.tsx`, `CompanyPanel.tsx`, `AddCompanyDialog.tsx`: the low-contrast badge text and the search placeholder to `text-muted` or better; icons one colour (`text-secondary`); the dialog backdrop solid (no blur); the hover tint from tokens; the dash in copy replaced. Tests first in `src/features/companies/CompaniesPage.test.tsx`: `test_SC002_companies_text_uses_text_roles`, `test_US3_AS6_dialog_backdrop_has_no_blur`.
- [ ] T025 [US3] Settings and setup. `src/features/settings/*`: full container width (no narrow column), the AI card without stripe; `src/features/setup/*` and the `src/index.css` setup card: the same system (no border-plus-shadow, accent links). `src/features/profile/VersionView.tsx` dash in copy replaced. Tests first in `src/features/settings/AiSection.test.tsx` and `src/features/setup/SetupGate.test.tsx`: `test_FR017_settings_uses_full_width`, `test_US3_setup_uses_accent_links`.
- [ ] T026 [US3] Mikasa panel and avatar. `src/features/assistant/MikasaDock.tsx` (flat accent circle, accent-ink icon, hover colour step, `active:scale-[0.96]`, no `hover:scale-110`, no glow shadow), `MikasaAvatar.tsx` (flat accent disc), `MikasaPanel.tsx` (one neutral shadow, no border-plus-soft-shadow), `QuickActions.tsx` and `StagedFlow.tsx` (tokens, named transitions); straight quotes in prose replaced by typographic quotes there and in `src/features/jobs/PasteJobDialog.tsx`. Behaviour unchanged. Tests first in `src/features/assistant/MikasaDock.test.tsx` and `MikasaPanel.test.tsx`: `test_US3_AS6_dock_is_flat`, `test_US3_AS6_avatar_is_flat`, `test_FR012_dock_does_not_scale_up_on_hover`.

- [ ] T026a [US3] Story review (constitution, Quality Gates): React, TypeScript and accessibility reviewers over this story's diff (the six screens); fix findings with tests; rebuild the dev stack; mark the story done only after this.

**Checkpoint**: Full visual review of every screen at 1440, 820, 390.

---

## Phase 6: User Story 4 - See my profile where I expect it (Priority: P2)

**Goal**: Profile shows the confirmed profile (FR-025 to FR-027).

**Independent Test**: quickstart §5.

- [ ] T027 [US4] Profile summary (R10). `src/features/profile/ProfilePage.tsx`: add the existing `['profile']` query (`GET /profile`); with `current` present render new `src/features/profile/ProfileSummary.tsx` (headline, skills, experience, the fields `VersionView` shows) with an "Edit" link to `/profile/edit` and a secondary "Update from a new resume" button that reveals the existing upload area; with `current: null` the page is unchanged; the empty Tailored resumes text says "None yet. Open a job and choose Tailor my resume."; full container width. Tests first in `src/features/profile/ProfilePage.test.tsx`: `test_US4_AS1_confirmed_profile_shown`, `test_US4_AS2_no_profile_shows_upload`, `test_US4_AS3_update_reveals_existing_upload_flow`, `test_US4_AS4_empty_tailored_resumes_text`.

- [ ] T027a [US4] Story review (constitution, Quality Gates): React, TypeScript and accessibility reviewers over this story's diff (ProfilePage, ProfileSummary); fix findings with tests; rebuild the dev stack; mark the story done only after this.

**Checkpoint**: Profile review at 1440 and 390 with a confirmed profile, and on a fresh setup.

---

## Phase 7: Polish and verification

- [ ] T028 Full gates: `npm audit --omit=dev`, `npm run test`, `npm run typecheck`, `npm run lint`, `npm run build`; every Playwright journey twice, including the new `e2e/mobile.spec.ts`. Fix what fails, with tests.
- [ ] T029 Visual verification against the baseline (R15). Hallmark (`$HALLMARK_DIR` = the installed Hallmark skill folder; the render tier needs `puppeteer-core` or `HALLMARK_PUPPETEER`): `node "$HALLMARK_DIR/scripts/sloplint.mjs" frontend/src --genre modern-minimal --scope app --render --kept` with `--url` for `/`, `/explore`, `/companies`, `/profile`, `/settings`: 0 Floor FAIL except findings recorded as kept with their reason, no `FAIL kept` (SC-004, SC-005). Impeccable (`IMPECCABLE_NO_TELEMETRY=1`): `detect` over source and over CDP at 1440 and 390 shows no gradient-text, side-tab, nested-cards or low-contrast (SC-002); re-run the critique (Consistency ≥ 3, total ≥ 28, SC-006); then `/impeccable polish` and fix its findings with tests. Record the before and after in `specs/003-ui-redesign/verification.md`.
- [ ] T030 Final review: React, TypeScript, accessibility and security reviewers over the whole branch's frontend diff; fix findings with tests; rebuild the dev stack.
- [ ] T031 [P] Docs: `docs/architecture.md` §10 points to `DESIGN.md` as the visual source of truth; `specs/003-ui-redesign/success-criteria-map.md` (SC-001 to SC-009 → tests and checks); `docs/CONTEXT.md` (history, next steps). After 002m has merged, rebase `003-ui-redesign` onto `master` (constitution: features are cut from `master`), rerun T028, then open the PR against `master`.

---

## Dependencies & Execution Order

### Phase dependencies

- Setup (T001, T002) → Foundational (T003 to T010) → stories. T003 first in Foundational; T004, T007, T010 can follow in parallel; T006 after T003; T005 after T006 (its scan covers `brand.css`); T008 and T009 after T003.
- US1 (Phase 3) after Foundational. US2 after US1's T011 (it renames the nav T011 builds). US3 after US2's T018 (stage chips) and T019 (Explore row). US4 after Foundational only.
- Polish after every story.

### User story dependencies

- **US1**: needs T003, T008, T009 (tokens, button, table pattern).
- **US2**: needs T004 (stages) and T011 (nav).
- **US3**: needs T010 (StageBar, FlowChart), T018, T019.
- **US4**: needs T003, T008; independent of US1 to US3.

### Within each task

Tests first and failing for the right reason → minimum code → refactor → whole suite green → one commit when Ravi asks.

### Parallel opportunities

- Foundational: T004, T007, T010 (different files) after T003.
- US1: T013, T014, T015 (different pages) after T011.
- US4 (T027) can run beside US3.
- Polish: T031 beside T029.

## Parallel Example: User Story 1

```text
After T011 and T012:
  T013 Pipeline table as cards   (src/features/explore/PipelinePage.tsx)
  T014 Explore table as cards    (src/features/explore/ExplorePage.tsx)
  T015 Companies list as cards   (src/features/companies/CompaniesPage.tsx)
```

## Implementation Strategy

### MVP first

Setup, Foundational and US1: the app on the new system and fully usable on a phone (the P0). Stop and review.

### Incremental delivery

1. Foundational: the whole app changes colour, type and motion at once (review).
2. US1: phone (review).
3. US2: meaning and labels (review).
4. US3: each screen finished (review).
5. US4: profile (review).
6. Polish: gates, detectors, critique, docs, PR after 002m merges.

## Notes

- Out of scope (do not start): the job page restructure, Mikasa focus handling, Explore bulk actions beyond the one notice, persistent filters, a light theme.
- The Mikasa journeys in `e2e/mikasa.spec.ts` must stay green throughout; they find controls by role and name, so restyling must not change those names.
- If a Hallmark or Impeccable finding contradicts DESIGN.md, DESIGN.md wins; record it in `verification.md` with the reason.
