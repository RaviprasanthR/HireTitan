# Quickstart: Resume picker

How to check the feature end to end. Endpoints and shapes are in [contracts/rest-api.md](contracts/rest-api.md); the stored data is in [data-model.md](data-model.md).

## Prerequisites

- Docker Desktop running (tests use Testcontainers; the app runs with `docker compose`).
- Backend: `cd backend && uv sync`. Frontend: `cd frontend && npm ci`.

## Automated checks

```bash
# backend: rules, constraints, file removal, API, merge, undo, privacy, delete-all
cd backend
uv run pytest tests/unit/search/test_resume_choice.py tests/integration/search/test_resume_choice_repo.py tests/api/search/test_resume_choice_api.py tests/security -q
uv run ruff check . && uv run mypy --strict src && uv run lint-imports

# frontend
cd ../frontend
npx vitest run src/features/jobs src/features/explore src/features/profile
npm run build          # runs tsc -b, which catches more than tsc --noEmit
```

Playwright (after `node frontend/e2e/prepare.mjs` and the e2e compose stack, as in `docs/CONTEXT.md`): `npx playwright test e2e/job-search.spec.ts` in `frontend/`.

## Manual walk-through (dev stack on http://127.0.0.1:8000)

1. Profile: make sure two resume files are stored (upload a second synthetic resume if needed).
2. Explore: on a job, open the **Resume used** choice beside the date; it lists both files newest first and **None**, starting on None the first time. Choose the older file and press **I applied**. Expected: the job is in In pipeline with that file in the **Resume** column.
3. Mark a second job: the choice starts on the file you chose last. Press **I applied** without touching it. Expected: one click, same file recorded.
4. In pipeline: expand a job; the details show the file's name and the day it was added. A job marked before this feature shows a dash.
5. Edit card (pencil): change the resume, then set it to None and save; the list follows. Change it and try to close without saving: you are asked first.
6. Profile: remove the file used in steps 2-3. Expected: the confirmation says it is used on 2 jobs and that the name stays as a note. After confirming, both jobs show "name (removed)"; the next **Resume used** choice starts on None.
7. Edit card on one of those jobs: **Clear** the removed note. Expected: the job shows a dash.
8. Settings: Delete all my data. Expected: no resume choice or note remains (check In pipeline after re-adding a job).
