# Careers-page extraction evaluation set

Ten synthetic careers pages, with the jobs each one really lists, for the `extract_jobs_from_page`
prompt (T053). The AI is asked only when a page has no JSON-LD job data and no job-shaped links,
so the pages here put their jobs in tables, cards, plain rows and grouped lists.

- 3 pages with traps: instructions aimed at an AI (visible and hidden), partner links to other
  sites, and an events list next to the real roles.
- 1 page with no openings, 1 with jobs that have no link of their own (they must be left out).

**Gate before the prompt goes into the search:** precision and recall of at least 90%, no unusable
answers, no link outside the page's own site, no job added because of injected text.

Run it with
`PYTHONPATH=backend backend/.venv/Scripts/python.exe -m evals.run extract_jobs_from_page --models fast`
from the repository root. It prints the maximum cost first (up to about $0.15; the real cost is usually under $0.05) and needs `--yes` to
spend. Reports are saved in `backend/evals/reports/`. Everything here is invented; no real page
or company appears.
