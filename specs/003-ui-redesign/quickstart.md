# Quickstart: validate 003-ui-redesign

## Prerequisites

- Branch `003-ui-redesign`; Docker Desktop running; `docker compose up -d --build` from the repo root, app
  on http://127.0.0.1:8000 with a confirmed profile, at least two pipeline jobs and a few Explore jobs
  (one without a description).
- Node 22 in `frontend/` (`npm ci`).

## 1. Automated gates

```bash
cd frontend
npm run test        # vitest: FR/US/SC-named tests incl. token scan, stages, contrast, nav, tables
npm run typecheck
npm run lint
npm run build
npx playwright test # every existing journey, twice at the end of the feature
```

Expected: all green; the only test wording changes are those listed in `contracts/ui.md`.

## 2. Phone (US1, SC-001)

At 390x844 and 320x640 open `/`, `/explore`, `/companies`, `/profile`, `/settings`:
- A bottom bar shows Jobs, Companies, Profile, Settings; each opens its page.
- `document.documentElement.scrollWidth === innerWidth` on every page.
- Job and company rows are cards with title, company, stage or source, date and actions.
- The Mikasa button sits above the bar and covers nothing.

## 3. Meaning (US2, SC-003)

- Each stage chip has the same colour on the Pipeline tab, Explore, Companies and the job page.
- Clicking a job title on the Pipeline tab and on Explore opens `/jobs/:id` in the same tab.
- "Open posting" opens a new tab and is announced as such; it is absent for a job without a URL.
- Settings shows "Test key"; the job page shows "Re-check fit"; Explore shows one notice with
  "Re-check fit"; no "Check again" anywhere.

## 4. Look (US3, SC-002, SC-004, SC-005)

- Screenshots at 1440x900, 820x1180, 390x844 of every top-level page, a job page and the Mikasa panel.
- Contrast: no text below 4.5:1 (DevTools or the Impeccable detector over CDP).
- Hallmark: `node "$HALLMARK_DIR/scripts/sloplint.mjs" frontend/src --genre modern-minimal --scope app --kept`
  with `--url` for each page: 0 Floor FAIL except findings recorded as kept, and no `FAIL kept`.
- Impeccable: `IMPECCABLE_NO_TELEMETRY=1 impeccable detect --json frontend/src` reports no
  gradient-text, side-tab or nested-cards; the critique re-run scores Consistency >= 3 and total >= 28.

## 5. Profile (US4, SC-008)

- With a confirmed profile, `/profile` shows headline, skills and experience in the first screen at 1440
  and 390, with "Edit" and "Update from a new resume".
- "Update from a new resume" reveals the upload area; an upload goes through review and saves nothing
  until confirmed.

## 6. Reduced motion

With `prefers-reduced-motion: reduce` emulated, nothing animates on hover, panel open or progress.
