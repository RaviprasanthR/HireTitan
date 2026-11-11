# Quickstart: validating navigation and pipeline (002d)

## 1. Automated checks

```bash
cd backend
uv run pytest tests/unit/search tests/api/search tests/workflow/search tests/architecture tests/integration -k "pipeline or inquired or job_state or stops or no_cost or migrations or companies or duplicates"
uv run lint-imports
cd ../frontend && npx tsc --noEmit -p . && npm test
```

Expected: all green. The `no_cost` tests fail if any API field or LLM wrapper still talks about cost or budget.

## 2. Try it by hand (synthetic data only)

Start the demo stack as in 002 (`node frontend/e2e/prepare.mjs`, then `docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml up --build -d`; http://127.0.0.1:8000).

1. **Menu**: exactly Home, Companies, Profile, Settings.
2. **Home**: the Explore tab is selected (address `/`). Run a search: the panel shows batches and jobs, no cost. Open the search summary and history: no cost.
3. **Inquired**: on an Explore job press **I inquired**; it leaves Explore and an Undo notice appears. Press Undo: it is back. Press I inquired again, open **In pipeline** (address `/pipeline`): the job is there as Inquired with today's date. On its page press **I applied**: it shows as Applied with the applied date.
4. **Old links**: open `/applied`, `/preferences`, `/search/rules`: they land on In pipeline, Profile → Preferences, Profile → Search rules. `/review` still opens the review list.
5. **Companies**: the company of the inquired-then-applied job shows **Applied**; mark another company's job inquired: that company shows **Inquired**; Show → In pipeline lists both.
6. **Review notice**: with the AI key file set to `missing` and a resume uploaded, a paused run appears as "1 item needs your review" on Home.
7. **Settings**: only the AI key status (with Check again) and Delete all my data.
8. **Out of credit**: set the fake provider to answer out of credit and run a search: it stops after the batch with the provider's message; Check again continues it.

## 3. Update from an earlier install

Before updating, have a run paused for the budget (in a 002 install, set the cap to 0 and upload a resume). After `docker compose up --build`, the run shows as failed with "Paused by the old AI budget, which HireTitan no longer has. Start it again."; Retry works.
