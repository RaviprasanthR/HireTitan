# Quickstart: validate Setup and Profile (first slice)

How to prove the feature works end to end. Contracts: [rest-api.md](contracts/rest-api.md), [profile-ingest-workflow.md](contracts/profile-ingest-workflow.md). Data: [data-model.md](data-model.md).

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux).
- For development: Python 3.12 + `uv`, Node 22 + npm.
- Optional: an OpenAI API key. Everything except real extraction works with `HIRETITAN_LLM=fake`.
- Synthetic resumes: `backend/tests/fixtures/resumes/` (never real ones).

## A. End-user path: `docker compose up`

```bash
cp .env.example .env          # leave OPENAI_API_KEY empty for the first check
docker compose up --build
# open http://127.0.0.1:8000
```

| Step | Expected | Covers |
|---|---|---|
| 1. Open the app with no key | Dark dashboard, sidebar Home · Profile · Preferences · Review · Settings. Banner: "OpenAI key missing: add OPENAI_API_KEY to .env and restart". Checklist shows the key step not done. | US3-AS1, FR-027/028 |
| 2. Preferences → check defaults → set a role, Chennai/IN, hybrid, 18–24 LPA → Save | Saved time shown; values survive a reload and `docker compose restart` | US2-AS1/2/5, FR-026 |
| 3. Save with min pay > target | Refused; error next to the pay field | US2-AS4 |
| 4. Profile → upload `synthetic-mid-2page.pdf` | Run is queued, then shows "Paused: key missing" in Review | US3-AS2, FR-030 |
| 5. Put a valid key in `.env`, then `docker compose restart api worker` | Banner gone, status "found, working"; the paused extraction continues by itself and the review opens | US3-AS3 |
| 6. In review: check contact (email/phone filled in), edit a title, delete a skill → Confirm | Version 1 created, linked to the file; Home checklist shows "profile confirmed" | US1-AS1/2, FR-008a/017 |
| 7. Preferences again | Suggestions offer the latest title and the profile's skills | US2-AS3 |
| 8. Upload `synthetic-mid-2page-v2.docx` | Review opens pre-filled; changed fields marked with their current values | US1-AS8, FR-014 |
| 9. Leave the review, reopen it from Review | Edits still there | US1-AS9 |
| 10. Settings → cap $0.00 → upload again | Run paused "monthly AI budget reached"; raise the cap → it continues | US3-AS4/5 |
| 11. Settings → Delete all my data → type DELETE | Back to the first-run checklist; no files remain in `data/files` | US4-AS2, SC-008 |

## B. Security fixtures (fake LLM, no key needed)

```bash
cd backend
uv run pytest tests/security -q
```

Expected: all pass. The planted fixtures cover hidden white text, tiny text, off-page text, "ignore previous instructions", `<|im_start|>system`, and a fake skill planted in hidden text. All are flagged (SC-005). None reach the prompt (prompt-recording fake). No ungrounded item reaches a review (SC-004). No email or phone appears in any prompt (SC-009).

## C. Full test suite and gates

```bash
docker compose up -d db                 # dev Postgres; tests use Testcontainers anyway
cd backend && uv sync && uv run ruff check . && uv run mypy --strict src && uv run lint-imports && uv run pytest --cov
cd ../frontend && npm ci && npm run typecheck && npm run lint && npm test -- --coverage
npx playwright test e2e/setup-and-profile.spec.ts   # stack started with HIRETITAN_LLM=fake
```

Expected: everything green; coverage ≥ 90% on `*/domain` + `*/application`, ≥ 80% overall; Playwright journey A1–A11 passes with the fake LLM.

## D. Extraction eval (real key, costs money, run on demand)

```bash
cd backend && uv run python -m evals.run extract_profile --models fast,strong
```

Expected report (`evals/reports/extract_profile-<date>.md`): field-level precision/recall ≥ 0.90 on the fast model (SC-003), p95 latency ≤ 60 s (SC-002), mean cost < $0.05 per resume (SC-007). The report decides the default `fast` model (ADR-11) and goes in the PR.
