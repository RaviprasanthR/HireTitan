# Implementation Plan: UI redesign to the HireTitan design system

**Branch**: `003-ui-redesign` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-ui-redesign/spec.md`; visual system from `DESIGN.md`.

## Summary

Restyle the whole front end to the approved design system (graphite ramp, one flat lavender accent, five
stage colours, Geist plus Geist Mono, one component set, quiet motion) and fix the P0/P1 problems the
reviews found: the app is usable on a phone (one nav that becomes a bottom bar, tables that become cards,
no sideways scroll), colours and links mean one thing, labels are renamed ("Jobs", "Test key",
"Re-check fit"), and Profile shows the confirmed profile. Front end only: the same routes, requests,
handlers and test ids. The work runs screen by screen in DESIGN.md's order, each screen test-first and
then checked in screenshots at 1440, 820 and 390. See [research.md](research.md) for every decision.

## Technical Context

**Language/Version**: TypeScript 5.9 (strict), React 19, CSS (Tailwind 4 with `@theme`)

**Primary Dependencies**: Vite 8, Tailwind CSS 4, shadcn/radix-ui, lucide-react, React Router 7,
TanStack Query 5; new: `@fontsource-variable/geist-mono` (OFL 1.1)

**Storage**: N/A (no data changes)

**Testing**: Vitest 5 + Testing Library (unit and component), Playwright (existing journeys); review tools
for verification: Hallmark `sloplint`, Impeccable `detect` and critique, Chrome DevTools screenshots

**Target Platform**: Evergreen desktop and mobile browsers against the self-hosted app (Docker,
http://127.0.0.1:8000)

**Project Type**: Web application (FastAPI backend untouched; React frontend changed)

**Performance Goals**: No regression: first paint and interaction as today; the mono font adds about
30 KB; removing the donut charts removes SVG work

**Constraints**: No colour literal outside tokens; no new external request; dark theme only; contrast
>= 4.5:1 for text; no layout animation; every existing test id, route and request unchanged

**Scale/Scope**: About 15 page components and 10 shared components in `frontend/src`; 7 screens
(Pipeline tab, Explore, job page, Profile, Companies, Settings, Mikasa panel) plus the shell and setup

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Human in the loop, no outbound actions | No new action sends anything; "Open posting" only opens a page in a new tab; "Re-check fit" reuses the existing AI fit check, which records reasons and stays undoable | Pass |
| II. Truthful profile | Profile page only displays the confirmed profile; updating still goes through review and confirm; no AI output changes | Pass |
| III. Untrusted input is data | Job titles and descriptions keep rendering as text (no `dangerouslySetInnerHTML` added); posting URLs still pass `postingLink` | Pass |
| IV. Validated, provider-agnostic AI | No prompt, model or LLM call change; no cost figures added | Pass |
| V. Test-first | Each task writes its FR/US/SC-named tests first and sees them fail; Playwright journeys stay green | Pass |
| VI. Lean architecture | Additions: `theme/stages.ts`, `StageChip`, `StageBar`, `ProfileSummary`, one CSS table pattern; `Donut` removed. No new abstraction layer | Pass |
| VII. Permitted sources only | No source change | Pass |
| VIII. Self-hosted privacy | Fonts bundled; no telemetry; review tools run locally with telemetry off and are not shipped | Pass |
| Workflow: branch cut from `master` | Cut from the `002m-mikasa-chat` tip by Ravi's decision | Deviation, justified below |
| Workflow: licence gate | `@fontsource-variable/geist-mono` is OFL 1.1, like the installed Geist | Pass |

**Post-design re-check (after Phase 1):** unchanged. The design adds no server interaction, keeps the profile
read-only on display, and the only new dependency is the font. The gate passes with the one recorded deviation.

## Project Structure

### Documentation (this feature)

```text
specs/003-ui-redesign/
├── plan.md              # this file
├── research.md          # Phase 0: decisions R1 to R16
├── data-model.md        # Phase 1: design tokens and the stage table
├── quickstart.md        # Phase 1: validation guide
├── contracts/
│   └── ui.md            # Phase 1: what changes on purpose and what must not
├── checklists/
│   └── requirements.md  # spec quality checklist
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
DESIGN.md                                 # approved design system (input)
frontend/
├── package.json                          # + @fontsource-variable/geist-mono
├── e2e/
│   ├── job-search.spec.ts                # "Home" -> "Jobs"
│   └── setup-and-profile.spec.ts         # "Home" -> "Jobs"
└── src/
    ├── index.css                         # @theme utilities, mono font, .dark block removed, overflow clip
    ├── theme/
    │   ├── theme.css                     # :root tokens rewritten; tables-as-cards; chips; motion
    │   ├── brand.css                     # flat mark and wordmark
    │   ├── tokens.ts                     # mirrored values
    │   ├── stages.ts                     # NEW: the five stages
    │   ├── contrast.test.ts              # new pairs; no gradient or glow anywhere
    │   └── tokens.scan.test.ts           # NEW: no colour literal outside tokens
    ├── app/Shell.tsx                     # one nav, bottom bar below 768px, "Jobs", no overflow-hidden
    ├── app/AiBanner.tsx                  # "Test key"
    ├── components/
    │   ├── ui/button.tsx                 # one button pair, named transitions
    │   ├── FlowChart.tsx, charts.css     # inline icons, muted zero stages, total beside
    │   ├── StageBar.tsx                  # NEW: one stacked stage bar
    │   ├── StageChip.tsx                 # NEW: stage chip
    │   ├── Donut.tsx                     # deleted when unused
    │   └── PageTabs.tsx, ProgressBar.tsx, Logo.tsx, AppName.tsx
    └── features/
        ├── explore/                      # PipelinePage, PipelineChart, ExplorePage, SearchPanel,
        │                                 # SearchFlow, RunSummaryPage, SearchHistoryPage
        ├── jobs/JobDetails.tsx           # "Re-check fit", Open posting, neutral cards
        ├── profile/                      # ProfilePage, NEW ProfileSummary, ProfileTabs
        ├── companies/                    # CompaniesPage, CompanyPanel, AddCompanyDialog
        ├── settings/                     # AiSection ("Test key"), GmailSection, data tab
        ├── assistant/                    # MikasaDock, MikasaAvatar, MikasaPanel, QuickActions, StagedFlow
        └── setup/                        # setup flow restyle
```

**Structure Decision**: The web application layout as it exists; only `frontend/` changes. The backend, API
schema and migrations are not touched.

## Phases of work

[tasks.md](tasks.md) is the order of record: Setup, Foundational, then US1 to US4 and Polish, with the screens below done inside US3 in this order. Each phase ends with Ravi's review (screenshots at 1440, 820 and 390, then a stop).

1. **Foundation:** tokens, `tokens.ts`, `stages.ts`, mono font, token scan test, contrast tests, flat
   `brand.css`, motion tokens, button and focus ring, `overflow-x: clip`.
2. **Shell (US1 core, US2 naming):** one nav with the bottom bar, "Jobs", the Mikasa button offset and flat
   avatar, page bottom padding, tab style.
3. **Pipeline tab:** FlowChart changes, StageBar, Donut removed, stage chips, tables as cards.
4. **Explore:** search panel without stripe or nested card, funnel once, title link, Open posting, the
   Re-check fit notice, meta without dots, tables as cards.
5. **Job page:** neutral cards, stage chip, "Re-check fit", Open posting.
6. **Profile (US4):** ProfileSummary, Update from a new resume, empty tailored-resumes text, full width.
7. **Companies:** contrast, one icon colour, stage chips, cards on phones, dialog without blur.
8. **Settings and setup:** full width, no stripe, "Test key", the uppercase label fix, setup restyle.
9. **Mikasa panel:** surfaces, quick actions, staged flow restyle (behaviour unchanged).
10. **Verification:** full gates, Playwright twice, Hallmark `--kept`, Impeccable critique and polish,
    docs (`docs/architecture.md` §10 links to DESIGN.md, `docs/CONTEXT.md`).

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Branch cut from the `002m-mikasa-chat` tip instead of `master` | The redesign must restyle Mikasa's UI, which exists only on 002m (Ravi, 2026-11-25) | Cutting from `master` would leave Mikasa in the old look and need a second pass; waiting for 002m to merge would block the redesign. The 003 PR opens after 002m merges, so its diff is clean |
