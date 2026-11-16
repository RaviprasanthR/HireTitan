# Relevance evaluation set

Synthetic profiles and postings, with the right answers, for the `judge_relevance` prompt (T027).

- 2 profiles: a mid-level Python backend developer and a junior React frontend developer.
- 60 postings with a label per profile: clear matches, near misses (a Java-only backend role, a
  manager title, the right title in a blocked city), unrelated roles that slip past the title rules,
  injection attempts, and postings with no location or date.

Run it with `PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run judge_relevance --models fast --repeat 3`
from the repository root. It prints the maximum cost first and needs `--yes` to spend. Reports are
saved in `backend/evals/reports/`. Everything here is invented; no real posting or person appears.

## The Python and Go profile and prompt v3 (feature 002i)

A third synthetic profile (a Python and Go back end engineer with 4.5 years, `areas = back_end`,
recent titles) is judged on its own 43 postings in `cases_go.py`: matches, generic titles decided by
their description, front end / mobile / QA / other-stack roles, postings whose text could not be
read, roles far above or below the level, and injection attempts. The report adds two measures
(SC-008): the share of the front end, mobile, QA and other-stack roles left out (at least 95%) and
the recall on the relevant ones (at least 95%).

A new prompt version is evaluated **before it is active**: its files live in
`candidates/judge_relevance/vN/` and the runner loads them with `--prompt-version N --prompt-root
backend/evals/judge_relevance/candidates`. When its report passes, the folder is moved into
`backend/src/hiretitan/prompts/judge_relevance/` (that is what makes it the current version) and the
report is committed with it.

