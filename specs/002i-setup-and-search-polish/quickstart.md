# Quickstart: Setup and search polish

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

How to check the feature by hand once it is built. Automated tests are listed in [contracts/rest-api.md](contracts/rest-api.md) and the task list.

## Prerequisites

- Docker Desktop running.
- Dev stack rebuilt from the branch: `docker compose up --build -d` (project `job-agent`, http://127.0.0.1:8000).
- For US6 with real data: an OpenAI key in `.env` (the AI check runs). For the scripted run: the e2e stack (`node frontend/e2e/prepare.mjs`, then `docker compose -p hiretitan-e2e -f docker-compose.yml -f docker-compose.e2e.yml up --build -d`).

## 1. First rules approved automatically (US1)

1. Settings → Delete all my data → type `DELETE`.
2. Go through setup with a synthetic resume: name, resume, review, preferences, **Finish setup**.
3. Expect Explore (Home → Explore) to show **Search now**, not "Finish setup first".
4. Profile → Search rules: approved rules and the line "HireTitan set these up from your profile and preferences. Change anything you like."
5. Restart the API (`docker compose restart api`): still one approved rule set (the version number has not changed).

Existing install that finished setup without rules (Ravi's state on 2026-11-16): rebuild the stack; after the API starts, Search rules shows approved rules.

## 2. Searching state (US2)

1. Explore → **Search now**.
2. Within a second: a moving bar and "Searching your companies…"; no "0 of 0", no "Batch".
3. Later: "Checked 8 of 44 companies · 3 new jobs so far" and a bar that matches.
4. Press **Stop**: "Stopping… jobs found so far are kept."
5. Turn on "reduce motion" in the OS: the bar stops moving, the message stays.

## 3. Search rules page (US3)

1. Profile → Search rules: three groups (jobs kept, jobs left out, what helps rank a job), no "Skips jobs", "Guides the AI", "Similar title" or "From your profile" tags.
2. **Edit** → change a job title → **Save** → "Rules saved."; the version goes up by one.
3. **Edit** → remove every job title → **Save** → an error next to Job titles; nothing saved.
4. **Edit** → change something → click Companies in the menu → you are asked before leaving.
5. Change a preference and come back: the notice and **Update from my profile**.

## 4. Preferences step (US4)

Run setup again (Delete all) at 1280 × 800: the Preferences step shows the groups in two columns. Narrow the window to phone width: one column, no sideways scroll. Take screenshots before and after for SC-005.

## 5. Explore rows (US5)

1. Explore: click a row → details open under it; click again → closed.
2. Click a title → the posting opens in a new tab; HireTitan stays on Explore.
3. Tab to a row's expand button, press Enter → it opens; the screen reader says "expanded".

## 6. Relevant jobs only (US6)

Scripted (e2e stack): the job-search journey seeds front-end, Java, generic and back-end Python postings for a back-end Python and Go profile; only the back-end Python jobs and the generic ones whose description fits reach Explore; the summary's skipped list shows "needs Java, which is not in your skills" and the area reason.

Real data (dev stack, costs a little AI use):

1. Clear the jobs from the 2026-11-16 search (delete them in Explore, or Delete all and run setup again). Stored jobs are not re-judged automatically (research R11).
2. Profile → Search rules: check **Areas** shows back end and **Words to avoid** has the front-end, mobile and QA words.
3. Explore → **Search now** (AI check on).
4. Expect no front-end or Java roles in Explore; open a kept job's row and see its description; the search summary lists the skipped jobs with reasons; record how many kept jobs had a description (SC-009).

## 7. Evaluation (before v3 goes live)

From the repo root, with the key in `.env`:

```bash
PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run judge_relevance --models fast --repeat 3 --yes
```

The report in `backend/evals/judge_relevance/reports/` must pass the gate (precision and recall ≥ 90%, the SC-008 rows, 0 unusable) and is committed with the PR.
