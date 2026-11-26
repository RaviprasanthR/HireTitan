# UI contract: 003-ui-redesign

The feature exposes no new API. Its interface is the app's UI, which tests and people rely on. This
contract lists what changes on purpose and what must not change.

## Must not change

- Every route in `frontend/src/app/routes.tsx` and its page.
- Every server request (paths, methods, bodies) and every React Query key.
- Every `data-testid`, form field `name`, `id` referenced by a label or `aria-*`, and every event handler.
- Landmarks: one `header`, one `nav` named "Main", one `main`; the Mikasa panel's role and shortcut
  (`Ctrl+/`).
- Copy kept word for word (FR-029): "HireTitan never sends anything" and its sentences, the Settings
  privacy line, the injection warning dialog.

## Changes on purpose

| Where | Before | After | Requirement |
|---|---|---|---|
| Main nav, first item | link "Home" | link "Jobs" (same `/` route) | FR-021a |
| Jobs page tabs label | `nav` "Home tabs" | `nav` "Jobs tabs" | FR-021a |
| Settings › AI, AI banner | button "Check again" | button "Test key" | FR-021 |
| Job page | button "Check again" | button "Re-check fit" | FR-021 |
| Explore row | button "Check again" per row | no row button; one notice with button "Re-check fit" | FR-022 |
| Explore row title | `a[target=_blank]` to the posting | router link to `/jobs/:id` | FR-019 |
| Explore row, job page | (the title was the posting link) | link "Open posting (opens in a new tab)", only with a posting URL | FR-020 |
| Profile (confirmed profile) | upload area | profile summary, link "Edit", button "Update from a new resume" | FR-025 |
| Pipeline overview | flow + donut + legend | flow + one stage bar; legend not focusable | FR-023, FR-024 |
| Explore search summary | flow + donut + legend | funnel once | FR-023 |
| Below 768px | top nav links | the same nav, fixed at the bottom | FR-014 |
| Below 768px | tables | the same tables, laid out as cards | FR-016 |

## Responsive layout

| Width | Navigation | Lists | Container |
|---|---|---|---|
| < 768px | bottom bar, 4 items, 56px + safe area | cards | 16px page edge |
| >= 768px | header links | tables | 24px edge, max 1440px centred |

## Accessible names

- Bottom bar items keep the same accessible names as the header links (one element).
- "Open posting" carries an `ExternalLink` icon (`aria-hidden`) and the text "(opens in a new tab)" for
  screen readers.
- Stage chips render the stage name as text; colour is never the only signal.
- Focus ring: 2px accent outline, 2px offset, no transition, on every interactive element.
