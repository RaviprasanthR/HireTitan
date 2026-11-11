# Quickstart: validating company contacts, notes and the applied flag (002b)

A run-through that proves the feature works end to end. Prerequisites: feature 002 merged into the branch (see the dependency note in [plan.md](plan.md)), Docker Desktop running (tests use Testcontainers), a confirmed profile and approved search rules (the 002 quickstart sets these up). Contracts: [rest-api.md](contracts/rest-api.md). Tables: [data-model.md](data-model.md).

## 1. Automated checks

```bash
cd backend
uv run pytest tests/unit/search tests/integration/search tests/api/search tests/security -k "contacts or sheet or company_match"
uv run lint-imports
cd ../frontend && npm run typecheck && npm test
```

Expected: all green. `lint-imports` fails if the workflows, prompts or LLM port import the contacts modules.

## 2. Try it by hand (synthetic data only)

1. Start the app with the 002 demo stack (`docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml up --build -d`, then open http://127.0.0.1:8000). It runs the scripted AI and a synthetic company list.
2. Companies page → **Import sheet** → choose `backend/tests/fixtures/sheets/product_companies_sample.csv` (synthetic, same shape as the maintainer's sheet: empty rows and columns above the header, contacts with `[High]` tags and links on their own line).
   - The preview lists the columns it used and ignored (the two openings columns appear as ignored).
   - It shows companies matched and to add, contacts to add, notes to set, and the rows it will skip with reasons (one with no company name, one that matches two companies).
3. **Confirm**. The result shows matched, companies added, contacts added, notes set, and the skipped rows. A company that was on the shipped list keeps its name, city, careers link and job board.
4. Import the same file again. The preview says nothing to add or update (SC-002).
5. On the Companies page, check each company row: contact count, the note preview and the Applied chip. Filter by "has contacts" or "has an application"; click a column header to sort (a second click reverses it); type in the search box to find a company by name or city.
6. Open a company: see its contacts (name, role, confidence, LinkedIn link) and note. Add a contact with only a name; edit one; type a bad link (`not a link`) and see the error; delete one and confirm. Edit the note, then re-import the sheet: your edited note stays and the result says so.
7. In Explore, mark a job as applied (**I applied**): that company shows **Applied** on the Companies page. Undo it and the chip goes away.
8. Open a job in Explore: its company's contacts and note are shown with it.
9. Export the company list. The file has no contact data. Export again with **Include contacts and notes**: the `contacts` and `notes` columns appear. Settings → Delete all my data → the company list is back to the shipped state with no contacts or notes. Import the opt-in export: contacts are back.

## 3. Privacy spot-checks

- With contacts present, run a search with `HIRETITAN_LLM=fake`; the fake's recorded requests (`.e2e/fake_llm/calls.jsonl` in the demo stack) contain no contact name, link, email, phone or note text (SC-006).
- `git grep -n "linkedin.com/in/"` in the repo returns only obvious placeholders (`example`, `jane-example`); no real person appears in any fixture (FR-026).

## 4. Done when

- Every success criterion SC-001 to SC-007 has its test passing (the matrix at the end of [rest-api.md](contracts/rest-api.md) maps them).
- The Playwright journey passes locally and the e2e CI job is green on the PR.
