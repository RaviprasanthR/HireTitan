# Quickstart: validate 002k

How to prove the feature works end to end. Contracts: [contracts/rest-api.md](contracts/rest-api.md). Data: [data-model.md](data-model.md).

## Prerequisites

- Docker Desktop running (tests use Testcontainers).
- Backend: `cd backend && uv sync`. Frontend: `cd frontend && npm ci`.
- For the manual check, the dev stack on `:8000` (`docker compose up -d --build`) with a confirmed profile, at least one job in Explore with a description, and one contact on that job's company.

## 1. Automated gates

```bash
cd backend
uv run pytest                     # unit, integration (real Postgres), API, workflow, architecture
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src
uv run lint-imports               # drafts layers; drafts.workflow may not import contacts code
cd ../frontend
npm test -- --run && npx tsc --noEmit && npx eslint . && npm run build
npx playwright test               # the job-search journey gains the draft and resume steps
```

Expected: all green. `tests/architecture/test_no_send.py` scans `hiretitan.drafts` too. The recorded-call test proves no contact name, role or link, and none of the person's contact details, appear in any request.

## 2. Evaluations (real model, Ravi approves the run)

```bash
cd backend
uv run python -m evals.outreach_drafts --models fast,strong   # side by side; picks the message tier
uv run python -m evals.tailor_resume --models default
```

Expected (spec SC-003 to SC-005): 0 fabrications, 100% of seeded fabrications caught, 100% of connection requests ≤ 200 characters, ≥ 95% of referral messages pass the tone rules first time. Reports land in `backend/evals/reports/`.

## 3. Manual check on :8000

1. **Explore row (US1)**: open Home → Explore. Each row has only **I applied** and **I inquired**. Expand a row: **Resume used** and **Pick a date** are there. Mark the job applied with a resume and an earlier date; In pipeline shows both.
2. **Connection request (US2)**: expand a job → **Connection request** → pick the contact → **Write**. A draft appears with a count of 200 or less, the contact's first name filled in and the profile facts it used listed. Edit it past 200: the count turns to a warning. **Copy** puts it on the clipboard. Nothing opens LinkedIn.
3. **Referral message (US3)**: same job → **Referral message** → type a name and role → **Write**. The message names the role and company, offers an easy decline and has no pressure.
4. **Tailored resume (US4)**: same job → **Tailor my resume**. A full preview appears with the keyword match (matched, missing with reasons). Edit a bullet and save; the match updates. **Download PDF** and **Download DOCX** open as single-column documents with the same text. The resume is listed on Profile under **Tailored resumes**.
5. **Failures**: stop the network or set a bad key, try a draft: a plain reason is shown and the rest of the app keeps working. On a job with no description, Tailor my resume asks for one.
6. **Clean-up**: delete the job: its drafts and resume are gone. Delete all my data: nothing of this feature is left.
