# Verification (T029), 2026-11-27

## Hallmark `sloplint` (`--genre modern-minimal --scope app --kept`)
Baseline `.hallmark/before.txt`: 187 FAIL, 1 REFLEX. Now: 6 FAIL, 0 REFLEX; kept links 43/43, fields 27/27, test hooks 11/11.

Remaining FAILs, all kept:
- **2a purple-to-blue gradient** (`theme.css` :27-28): kept by Ravi (2026-11-26). Allowed only through `--ht-accent-gradient` on the primary and Mikasa buttons and within donut slices; a test forbids it elsewhere.
- **20 no Hallmark stamp** (`charts.css`, `index.css`, `brand.css`): the stamp is for pages Hallmark generates; this is an existing app styled from `DESIGN.md`.
- **kept handlers** (3 of 299): `onClick={() => recheck.mutate(job.id)}` was replaced by the one batch "Re-check fit" notice (FR-020); the donut legend `onFocus` / `onBlur` were removed because legend entries are no longer tab stops (FR-023).

## Impeccable `detect`
- Source scan: regex rules only, no findings.
- Running pages (`/`, `/explore`, `/companies`, `/profile`, `/settings`): found a light-on-light "Add company" button (the accent gradient showed through its raised fill, 1.7:1) and over-long lines on Profile. Fixed (secondary variant; `max-w-[50ch]` on the summary and bullets, `p.text-muted-small` capped at 75ch). Re-scan: no findings except the kept purple-gradient advisory.
- Not re-run: the LLM critique score (SC-006) and `/impeccable polish`; before: 24/40, Consistency 1/4.
