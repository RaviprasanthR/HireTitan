# HireTitan design system

Approved by Ravi on 2026-11-25. This file is the visual source of truth for the app UI. It replaces the
orange-on-navy look of 2026-11-12 and the gradient brand of 2026-11-15. Built from the Hallmark
audit, Impeccable's critique and Unslop's review of the same date. Taste set the art direction, adapted
to an app (see Waivers).

## Direction

- **Product.** A private desk where one person runs their job search, and nothing leaves without them.
- **Character.** Steady, exact, discreet.
- **World.** A case file at night: dark graphite paper, index-card rows, a stamp for each stage.
- **Mode.** Operate. People scan, compare and act, for long sessions. Familiar app patterns win over
  expression; the brand lives in precise details.
- **Signature.** The stage colours. Each pipeline stage has one muted colour, defined once and used the
  same way everywhere (chips, flow chart, funnel, job page). Colour on this app always means a stage
  or a state, never decoration.
- **Moments.** The pipeline flow on the Jobs page (In pipeline tab) and the search funnel on Explore. Each is drawn once, with care.
  Everything around them is quiet.

## Colour

Dark only. Every colour is a token in `frontend/src/theme/theme.css` `:root` (mirrored in `tokens.ts`).
No colour literal outside the token block.

### Neutral ramp (graphite, very slightly cool)

| Token | Value | Use |
|---|---|---|
| `--ht-background` | `#12151b` | page |
| `--ht-surface` | `#181c23` | cards, panels, table body |
| `--ht-raised` | `#1f242c` | table head, hover row, inputs, popovers |
| `--ht-hairline` | `rgb(230 232 236 / 0.08)` | every border and divider |
| `--ht-hairline-strong` | `rgb(230 232 236 / 0.14)` | secondary button borders, stronger dividers |

### Text roles (three, no more)

| Token | Value | Contrast on surface |
|---|---|---|
| `--ht-text` | `#e6e8ec` | 13.9:1, body and headings |
| `--ht-text-secondary` | `#a8aeb8` | 7.7:1, supporting text |
| `--ht-text-muted` | `#8b929d` | 5.5:1, meta, captions, placeholders |

Headings use `--ht-text`; hierarchy comes from size, not from a brighter white.

### Accent (one)

| Token | Value | Use |
|---|---|---|
| `--ht-accent` | `#a99ce6` | links, selected tab, focus ring, primary button fill, the one figure that matters |
| `--ht-accent-hover` | `#bbb0ef` | hover on accent fills and links |
| `--ht-accent-ink` | `#16121f` | text on an accent fill (7.5:1) |
| `--ht-accent-tint` | `rgb(169 156 230 / 0.12)` | selected row, active nav item background |

Lavender is flat except in two places (Ravi, 2026-11-26): the primary button, the Mikasa button (open)
and her greeting bubble fill with `--ht-accent-gradient` (135deg, `#c2a8f8` to `#82aef7`; hover `#d0bbfa` to `#9dc0fa`;
`--ht-accent-ink` text stays 7:1 or better), and each chart slice is a soft gradient of its own colour
(the colour to 65% of itself mixed with white). No other gradient, no gradient text, no glow, no
coloured shadow. Orange is retired.

Hover takes the accent: secondary and ghost buttons, icon buttons, tabs and nav links turn
`--ht-accent` on `--ht-accent-tint`. The row buttons "I applied" and "I inquired" wear their stage
colour (text and a 40% edge, a 14% tint on hover), since they move the job into that stage.

### Stage colours (the signature)

Text-on-surface contrast in brackets. Chips use the colour as text on `--ht-raised` with a hairline in
the same colour at 30% opacity; charts use it as a fill.

| Stage | Token | Value |
|---|---|---|
| Inquired | `--ht-stage-inquired` | `#7fa8d8` (6.9:1) |
| Applied | `--ht-stage-applied` | `#6fc08d` (7.8:1) |
| Interview scheduled | `--ht-stage-interview` | `#d6b25e` (8.5:1) |
| Round cleared | `--ht-stage-cleared` | `#5ec4b6` (8.2:1) |
| Failed | `--ht-stage-failed` | `#e2837a` (6.3:1) |

Search outcomes on Explore reuse neutral steps plus the accent ("New jobs" is the accent; "Already
known" and "Left out" are secondary and muted). A stage colour never stands for anything but its stage.

### States

`--ht-success` = applied green, `--ht-warning` = interview amber, `--ht-danger` = failed red. Errors
always carry text, never colour alone.

## Type

- **Interface:** Geist Variable (already installed), weights 400 and 500; 600 only for the page title.
- **Figures and meta:** Geist Mono Variable with `font-variant-numeric: tabular-nums` for dates, counts,
  sizes, salaries and IDs.
- **Scale:** 12 (meta), 13 (labels, table heads), 14 (body in tables and forms), 16 (running text),
  20 (card titles), 24 (page titles), 32 (the one big figure in a moment).
- **Case:** sentence case everywhere. No uppercase or letter-spaced labels; table heads are 13px
  secondary text.
- **Meta:** no middle-dot strings. Meta sits in its own column, on its own line, or separated by space
  in mono. Never repeat a fact in one line ("Remote · remote").
- Typographic quotes in copy; `text-wrap: balance` on page titles.

## Spacing and shape

- 4px grid. Steps: 4, 8, 12, 16, 20, 24, 32, 48. Page edge 24 (16 on phones). Card padding 20.
  Space inside a group is smaller than space between groups.
- **Radius:** controls 8, cards 12, dialogs 16, chips 6. Inner radius = outer minus padding, minimum 4.
- **Elevation:** depth from surface steps and hairlines. No shadows on dark, except dialogs and the
  Mikasa panel (one neutral shadow, offset and blur, no colour).
- **Container:** content capped at 1440px and centred; pages use the full width of that container (no
  700px column with an empty right half).

## Components

- **Card:** `--ht-surface`, 1px `--ht-hairline`, radius 12. No side stripe, no coloured border. One
  containment level: no card inside a card.
- **Buttons:** one pair.
  - Primary: `--ht-accent` fill, `--ht-accent-ink` text, 500 weight, height 36 (44 hit area on touch).
    At most one per view.
  - Secondary: transparent, `--ht-hairline-strong` border, `--ht-text`.
  - Destructive: secondary shape with `--ht-danger` text; confirmation before it acts.
  - Ghost (icon buttons, table actions): no border, `--ht-text-secondary`, hover to `--ht-raised`.
- **Links:** `--ht-accent`, underline on hover and focus only. A link to another site carries an
  external-link icon and says so to screen readers.
- **Job title link:** always opens the HireTitan job page. The posting opens from an explicit
  "Open posting" action with the external icon.
- **Tabs:** text in `--ht-text-secondary`; the selected tab in `--ht-text` with a 2px `--ht-accent` bar.
- **Tables:** head on `--ht-raised`, 13px secondary sentence case; rows 48px, hairline between rows;
  hover `--ht-raised`; selected `--ht-accent-tint`. Below 768px a row becomes a stacked card (title,
  company, stage chip, date, actions), never a sideways-scrolling table.
- **Stage chip:** stage colour text, `--ht-raised` fill, 1px stage colour at 30%, radius 6, 12px 500.
- **Inputs:** `--ht-raised` fill, 1px `--ht-text-muted` edge (5:1, so the field's boundary meets the
  3:1 rule for controls; `hairline-strong` is too faint for that), radius 8, height 36; focus is the
  ring, not a border change. Disabled: opacity, `not-allowed` cursor and the native attribute.
- **Focus ring:** 2px `--ht-accent` outline, 2px offset, appears instantly, on every interactive element.
- **Nav (desktop):** wordmark left, links right, active link `--ht-text` with the accent bar, no glow.
- **Nav (below 768px):** a bottom tab bar with Jobs, Companies, Profile, Settings (icon and label, 56px
  tall, in the thumb zone). The Mikasa button sits above it.
- **Logo:** the existing mark, flat, in `--ht-accent`; the wordmark in solid `--ht-text`. The hover turn
  of the mark stays (reduced motion respected). No gradient, no drop-shadow glow.
- **Mikasa button:** `--ht-accent-gradient` circle with `--ht-accent-ink` icon; hover steps to
  `--ht-accent-gradient-hover`, press scales to 0.96. Pages reserve bottom padding so it never covers a row action.
- **Mikasa avatar and button:** her cut-out face (local art, `frontend/public/local/`, gitignored),
  floating gently and tilting on hover; without the file, a flat accent disc with a spark. Her
  greeting bubble (no buttons) springs out of the face once per visit, types for a moment, opens the
  chat on a click and fades away by itself; all motion stops for reduced motion.

## Data display

- **Pipeline flow (Jobs › In pipeline):** the stage sequence with counts, each node in its stage colour, the current
  largest stage emphasised, empty stages muted (never accent at 0). Icons sit inline, not in rings.
  "In pipeline" is a total shown beside the flow, not a stage in it.
- **Search funnel (Explore):** found, then known / left out / new, counts in mono. Shown once.
- **No duplicate charts:** the donut and its legend are replaced by one slim stacked stage bar under the
  flow, labelled once. Legend items are not tab stops.
- One accent per chart; every other colour is a stage colour or a neutral step.

## Motion

- Name the properties: `transition-colors`, `transition-[transform,opacity]`. Never `transition-all`,
  never animate width, height, top or left (progress fills use `transform: scaleX`).
- One curve, `cubic-bezier(0.2, 0, 0, 1)`; 120ms for feedback, 200ms for things that enter.
- Hover is a colour or surface step; press scales to 0.98 on buttons. No hover scale-up, no lift, no glow.
- The Mikasa panel fades and rises 8px from the button. Progress rings and the logo turn remain.
- Everything rests under `prefers-reduced-motion: reduce`.

## Copy

- Plain verbs and the app's own nouns. Buttons are a verb and an object ("Re-check fit", "Test key",
  "Open posting", "Add a job").
- One word per meaning: "Check again" is retired (job fit is "Re-check fit"; the AI key is "Test key").
- No exclamation marks; no trailing periods on labels, buttons or headings; status lines may be
  sentences.
- No em or en dashes in copy. An empty cell reads "Not set" in muted text.
- Keep the honest lines ("HireTitan never sends anything", the Settings privacy line) word for word.

## Screens (redesign order and intent)

1. **Tokens and shell:** the ramp, accent, stage colours, type, focus, nav, bottom tab bar, logo, Mikasa
   button.
2. **Jobs › In pipeline:** the destination is called "Jobs" everywhere (nav, bottom bar, title); flow moment plus stacked bar, then the jobs table; stage chips; mobile cards.
3. **Jobs › Explore:** compact search panel (no side stripe, no nested card), funnel once, filters, jobs table
   with one "Re-check fit" banner for jobs missing a description instead of a button per row.
4. **Job detail:** neutral cards (no rainbow), stage chip at the top, the posting action explicit.
5. **Profile:** shows the confirmed profile; "Update from a new resume" is secondary; full width.
6. **Companies:** contrast fixes (no text under 4.5:1), one icon colour (secondary), stage chips.
7. **Settings:** full width, no side stripe, "Test key".

## What stays

Routes, API calls, data, handlers, test ids, the page order and every user journey. The honest copy, the
keyboard shortcut for Mikasa, real tables with `scope`, descriptive row labels, Lucide as the only icon
set, the progress rings, the logo's turn.

## Waivers (on the record)

- **Taste, marketing house rules** (one section per screen, hero entrance, photographs, card hover lift,
  dealt moments): not applied. This is an Operate app; Impeccable's Operate guidance governs layout.
  Taste's app-relevant checks still apply: one system, button and link consistency, copy, contrast, tap
  size, keyboard, motion discipline.
- **Taste, no violet or lavender:** waived. Lavender is the owner's chosen brand colour (2026-11-15),
  kept as a single accent; its only blend is the button gradient above, never text or a glow.
- **Hallmark 2a and 2b, Unslop gradient-logo sign:** resolved, not waived: the wordmark and nav gradients
  and glows are removed.
