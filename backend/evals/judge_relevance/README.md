# Relevance evaluation set

Synthetic profiles and postings, with the right answers, for the `judge_relevance` prompt (T027).

- 2 profiles: a mid-level Python backend developer and a junior React frontend developer.
- 60 postings with a label per profile: clear matches, near misses (a Java-only backend role, a
  manager title, the right title in a blocked city), unrelated roles that slip past the title rules,
  injection attempts, and postings with no location or date.

Run it with `PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run judge_relevance --models fast --repeat 3`
from the repository root. It prints the maximum cost first and needs `--yes` to spend. Reports are
saved in `backend/evals/reports/`. Everything here is invented; no real posting or person appears.
