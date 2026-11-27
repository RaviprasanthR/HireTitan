# Quickstart: check Mikasa end to end

**Feature**: `002m-mikasa-chat` · Endpoints and events: [contracts/rest-api.md](contracts/rest-api.md) · Actions: [contracts/actions.md](contracts/actions.md)

## Prerequisites

- Dev stack as usual: Postgres in Docker, `uv` backend and `npm` frontend, the app on `http://127.0.0.1:8000`, migrations at `0026_assistant`.
- Setup finished with a confirmed profile (the synthetic demo resume is fine).
- For the scripted runs: `HIRETITAN_LLM=fake` with the Mikasa script in `backend/tests/fixtures/assistant/`. For a real run: an AI key saved in Settings.

## Automated checks

```bash
# backend: everything Mikasa touches, then the full gate
backend/.venv/Scripts/python.exe -m pytest backend/tests -k "assistant or actions or converse or R12" -q
backend/.venv/Scripts/python.exe -m pytest backend/tests --cov  # coverage gate as in CI
cd backend && uv run lint-imports && uv run mypy --strict src && uv run ruff check

# frontend
cd frontend && npm run test -- assistant PasteJobDialog && npm run typecheck && npm run lint && npm run build
npx playwright test e2e/mikasa.spec.ts
```

Expected: all green; `test_SC010_no_private_value_in_any_llm_request` and `test_FR020_description_never_in_model_context` pass; import-linter reports `hiretitan.assistant` inside `contacts-stay-out-of-ai-paths`.

## Manual walk-through (real model)

1. **Open** (US1): on Companies, press the Mikasa button (or `Ctrl+/`). The panel opens on the right; the table stays usable. The note under the composer says what is sent to the AI.
2. **Ask** (US1): "What did I apply to this week?" The answer streams in, names the jobs and each name opens the job. Nothing changes.
3. **Small change** (US2): "I applied to https://jobs.example.com/acme/123, Backend Engineer at Acme." The job is added and marked applied at once; a notice with **Undo** appears; In pipeline shows it without a reload. Press **Undo**: the job is gone and the same link can be added again.
4. **Ask for missing details** (US2 scenario 3): "I applied to https://www.linkedin.com/jobs/view/1" with no role. Mikasa asks for the title and company; nothing is fetched (no request to LinkedIn in the API log).
5. **Risky change** (US2 scenario 4): "Delete the Acme backend job." A confirm card appears; nothing is deleted until **Confirm**. Try **Cancel** on a second card: nothing changes.
6. **Private data** (FR-022): "Who is my contact at Acme?" A contact card with the name appears; in the LLM call log the request holds only `contact:<id>` and "a contact at Acme". "Summarise my Zoho interview notes" is declined with a link to the job.
7. **Drafts** (US3): "Write a connection request to my Acme contact for the backend job." A card asks to confirm the AI work; after it, the draft is on the job's page with the same checks as before. "Send it" is declined.
8. **Limits** (US4): "Delete all my data" and "change my AI key" are declined with links to Settings. Remove the key: the panel shows that a key is needed, and the rest of the app works.
9. **Conversations** (US5): reload the page; the conversation is still there. Clear it. Run **Delete all my data**; no conversation remains.

## Eval (before merge, on Ravi's key)

```bash
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run mikasa --models fast,strong --yes
```

The report goes to `backend/evals/reports/mikasa-<date>.md` and must show SC-002 to SC-006 passing on the `fast` tier.
