# Data model: 003-ui-redesign

No server data, table, migration or API shape changes (FR-028). The "entities" of this feature are the
front end's design values. Their values are defined in `DESIGN.md`; this file defines their shape and rules.

## Design token

A named visual value, declared once in `frontend/src/theme/theme.css` `:root` and mirrored in
`frontend/src/theme/tokens.ts`.

| Field | Rule |
|---|---|
| name | `--ht-<role>` in CSS, camelCase key in `tokens.ts`; one name per role |
| value | colour as `#rrggbb` or `rgb(r g b / a)`; size in px; timing in ms; curve as `cubic-bezier()` |
| role | one of: neutral ramp, text role, accent, stage, state, radius, space, motion |

Rules:
- Every colour used anywhere in `frontend/src` resolves to a token (FR-001); enforced by a scan test.
- `theme.css` and `tokens.ts` hold identical values; a test compares them.
- Each text token passes 4.5:1 on `background`, `surface` and `raised`; `accent-ink` passes 4.5:1 on
  `accent`; `hairline-strong` passes 3:1 as an input edge (FR-013).

Groups (values in DESIGN.md): neutral ramp (`background`, `surface`, `raised`, `hairline`,
`hairline-strong`), text roles (`text`, `text-secondary`, `text-muted`), accent (`accent`, `accent-hover`,
`accent-ink`, `accent-tint`), stages (five), states (`success`, `warning`, `danger`, aliases of stage
colours), radius (`control` 8, `card` 12, `dialog` 16, `chip` 6), motion (`ease`, `dur-fast`, `dur-enter`).

Removed tokens: `slate`, `primary` (navy), `on-primary` (orange), `muted-small`, `heading`, `hover-tint`.
Every use is moved to its new role in the same task.

## Pipeline stage

The stages a job moves through, in order.

| key | label | colour token |
|---|---|---|
| `inquired` | Inquired | `--ht-stage-inquired` |
| `applied` | Applied | `--ht-stage-applied` |
| `scheduled` | Interview scheduled | `--ht-stage-interview` |
| `cleared` | Round cleared | `--ht-stage-cleared` |
| `failed` | Failed | `--ht-stage-failed` |

Rules:
- Declared once in `frontend/src/theme/stages.ts`; every chip, chart and page reads it (FR-004).
- A stage colour is always shown with its label in text (never colour alone).
- The key `scheduled` and the token `--ht-stage-interview` name the same stage on purpose: the key matches the API, the token matches the label.
- Keys match the existing API values (`usePipelineSummary`, job `state`), so no mapping layer is added.
- Explore's search outcomes (new, already known, left out) are not stages and use the accent and
  neutral text roles.

## Not-checked job (Explore notice)

Derived, not stored: the Explore jobs for which `isNotChecked(job)` is true. The notice shows their count;
its action re-checks each one with the existing per-job request (FR-022). No new field.
