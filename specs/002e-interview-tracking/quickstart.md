# Quickstart: Interview tracking (002e)

How to see the feature work end to end. Details of the data and endpoints: [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md).

## Prerequisites

- The stack running from this branch: `docker compose up --build -d` (applies migration `0018_interview_tracking`), app at http://127.0.0.1:8000.
- At least one job marked **I applied** or **I inquired** (Explore → the button on a job).

## Scenarios

1. **Contact and source (US1).** Home → **In pipeline** → expand a row. Under Contact type a name only, choose **Through a hiring firm**, type a firm name, **Save**. Reload: the row shows the contact and the firm. Choose **Direct**, Save: the firm name is gone. Type `not-an-email` as the email: Save is refused on that field only.
2. **Rounds and status (US2).** In the same panel **Add round** (Technical, a date and time, an interviewer). The Status column reads **Round 1 scheduled**. Set Round 1 to **Cleared**, add Round 2: **Round 2 scheduled**. Set Round 2 to **Failed**: **Failed in round 2**, and **Add round** is disabled with the reason. Set it back to Scheduled: Add round works again. Delete Round 2: the status reads **Round 1 cleared**.
3. **Questions and feedback (US3).** On Round 1 add three questions (one with no answer), a multi-paragraph answer and a feedback note. Reload: order and line breaks are kept. Edit one, delete one: the rest are unchanged.
4. **Job page.** Open the job's own page: the same panel, same data, editable.
5. **Undo keeps details (FR-011).** On Explore or the job page, Undo the mark, then mark it again: contact, source and rounds are all there.
6. **Delete all (SC-004).** Settings → **Delete all my data**: In pipeline is empty and none of the details remain.

## Automated checks

- Backend: `uv run pytest tests -k "interview or FR0 or SC00"` then the full suite with the coverage gate; `uv run lint-imports` (the privacy contract); `ruff`, `mypy --strict`.
- Frontend: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`.
- E2E: `node frontend/e2e/prepare.mjs`, the e2e compose stack, `npx playwright test` (the job-search journey has the interview step).

No step calls the AI, and no step shows a cost.
