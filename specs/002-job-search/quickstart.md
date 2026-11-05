# Quickstart: validating Job Search (002)

Runnable checks that prove the feature works end to end. Details live in [data-model.md](data-model.md), [contracts/rest-api.md](contracts/rest-api.md) and [contracts/job-search-workflow.md](contracts/job-search-workflow.md).

## Prerequisites

- Docker Desktop running (tests use Testcontainers; the stack runs in compose).
- Feature 001 set up on this install: confirmed profile, saved preferences.
- For scenario D only: an OpenAI key in `.env`, with a little credit.

## A. Automated journey (scripted AI, synthetic companies, no network)

```bash
docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml up --build -d
cd frontend && npx playwright test e2e/job-search.spec.ts
```

The e2e override uses the synthetic seed (`tests/fixtures/companies/`), a fake career-ops with recorded board output, and the scripted fake LLM. Expected:
1. Home shows the setup checklist with "Approve your search rules" unticked.
2. Search rules → proposed rules with origins → edit one → Approve.
3. Search now → progress per batch, with cost shown → Explore fills after the first batch, before the run finishes.
4. Only relevant jobs are listed, newest first, each with a reason. The summary shows "N skipped" → open them → restore one → it appears in Explore.
5. Open a job → "I applied" → it moves to Applied with today's date → Undo → back in Explore.
6. Paste a job whose link matches a listed job → still one entry, two sources.
7. Search again → no new AI calls for jobs already judged (cost shown as $0.00 for them).

## B. Stop, budget and out of credit (workflow tests)

```bash
cd backend && uv run pytest tests/workflow/search -q
```

Expected:
- The out-of-credit, budget, stop and continuation tests in the [test matrix](contracts/job-search-workflow.md#test-matrix-names-reference-requirement-and-scenario-ids) pass.
- After an out-of-credit stop, the run shows `outcome = out_of_credit` and the provider's message, finished batches are in Explore, and the next run starts with the companies not yet read.

## C. Sources stay within the rules (contract tests)

```bash
cd backend && uv run pytest tests/contract/careerops tests/contract/careers_page tests/contract/openai -q
```

Expected:
- career-ops makes requests only to allowlisted hosts and methods.
- A robots-disallowed careers page is reported `blocked` and never fetched.
- An OpenAI 429 with code `insufficient_quota` becomes "out of credit" and is not retried. A 429 with code `rate_limit_exceeded` is retried.

## D. Relevance eval (real model, costs a few cents)

From the repository root:

```bash
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run judge_relevance --models fast --repeat 3
# shows the maximum cost first; add --yes to run
```

Expected: precision ≥ 0.90 and recall ≥ 0.90 on the 60 labelled postings (SC-003), 0 injection-affected decisions (SC-011), 0 unusable answers, and the cost per full search estimate under $0.25 (SC-006). Commit the report in `backend/evals/reports/`.

## E. Manual check on your own install (real sources)

1. `docker compose up --build`, then open http://127.0.0.1:8000.
2. Approve the rules, press Search now and watch the batches.
3. Check the summary: companies read, skipped, judged, kept, cost, and any company on the check-manually list.
4. Time it: home page to the first relevant jobs in under 5 minutes (SC-001); a full search in under 5 minutes (SC-002).
