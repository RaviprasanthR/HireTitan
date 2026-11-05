# Research: Job Search and Home Page List (002)

Date: 2026-11-05 · Inputs: [spec.md](spec.md) (with 4 clarifications), constitution v1.1.0, `docs/architecture.md` (§3 outbound traffic, W3/W3b/W8, ADR-05, §8 companies table), `docs/research/2026-11-03-company-source-feasibility.md`, feature 001 code (`platform/llm`, `platform/runtime`, `platform/untrusted`).

Each item: **Decision**, **Rationale**, **Alternatives considered**.

## R1. How jobs are fetched from company boards

- **Decision**: Use career-ops **v1.38.0**, pinned, as a subprocess (ADR-05). HireTitan writes a `portals.yml` into its **own** career-ops data folder on the data volume, runs `node scan.mjs --json`, and reads the JSON output through a `CareerOpsPort` (an external-CLI port, allowed by constitution VI). The backend runtime image gains Node 22 and career-ops (`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`). Today Node is only in the frontend build stage.
- **Finding while building T013 (2026-11-06), changes the mechanism, not the choice**: `node scan.mjs --json` prints only a receipt (counts and the URLs it added). The jobs themselves go into career-ops' own `pipeline.md` and `scan-history.tsv`, and `scan.mjs` filters by title and location and dedups against that history. So it cannot return postings, and its history would fight HireTitan's own dedup. The providers can: each takes a board entry and returns plain job objects (title, url, location, description, posted date, requisition id). HireTitan therefore ships a small `runner.mjs` that loads the **same pinned providers** and calls them directly (no filters, no history, no file writes), and `CareerOpsAdapter` talks to that. Pinned: tag `career-ops-v1.38.0` = commit `115bc9873e3d43e23883f3c8f16436617facc62c` (MIT, Copyright (c) 2026 Santiago Fernández de Valderrama). Playwright is imported only by `scan.mjs --verify` and two `lib/` helpers, never by a provider, so no browser is needed. The upstream repo has **no lockfile**: T014 must commit HireTitan's own `package-lock.json` for the runtime packages (`undici`, `js-yaml`, `dotenv`) and install with `--ignore-scripts`.
- **Rationale**: career-ops already has providers for Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Recruitee, Zoho Recruit and others. Those use the boards' public job-feed APIs, which is the permitted route (VII). Pinning the version keeps the recorded-output contract tests stable. ADR-05 notes `scan.mjs` makes plain HTTP calls and does not import Playwright, so no browser is needed in the image. **Check this again when pinning (task).**
- **Alternatives**: port the providers to Python (a lot of work, and loses upstream fixes); call the user's own career-ops install (breaks "anyone can clone it" and risks touching personal data); a headless browser (about 300 MB, and only helps a handful of companies, per the feasibility study).

## R2. Which career-ops providers are enabled (permitted-source check)

- **Decision**: Enable a provider only after its request paths have been checked against the target host's robots.txt and recorded in an allowlist (hosts and HTTP methods). A contract test runs career-ops against recorded responses through a recording proxy and fails on any request outside the list (architecture §3). Planned for v1: **Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Recruitee, Zoho Recruit, Amazon**. **Keka is disabled** until its request path is shown to be allowed by Keka's robots.txt (feasibility finding 1). Until then, Keka-hosted companies show as `check_manually`.
- **Rationale**: Constitution VII requires honouring robots.txt and not automating sites against their terms. The allowlist test turns that into something the build enforces.
- **Alternatives**: enable all providers and rely on upstream (it can't be enforced, and the Keka finding shows a real risk); write our own allowlist proxy in production (unnecessary, because career-ops runs only the providers we configure).

## R3. Careers pages without a readable board

- **Decision**: A Python `CareersPageSource` adapter, in order: (1) fetch the page with robots.txt honoured, one request per host at least 2 s apart, an ETag/Last-Modified cache, and the honest User-Agent `HireTitan/<version> (+repo URL)`; (2) parse schema.org `JobPosting` JSON-LD; (3) generic job-link heuristics; (4) only if both find nothing and the AI is available, the quarantined prompt `extract_jobs_from_page` (fast tier, bounded schema: up to 50 `{title, url, location?}`); (5) otherwise the company is marked `check_manually` with `last_checked_at`. Built in the companies story (US3), not in the first slice.
- **Rationale**: The feasibility study puts 6 companies in group D (plain HTML with jobs visible). JSON-LD and heuristics cost nothing; the AI is the last resort, as the baseline says.
- **Alternatives**: a headless browser (rejected, see R1); AI extraction first (costs money on every page).

## R4. Batched search with continuation

- **Decision**: A new LangGraph workflow, **W3 `job_search`**, runs on the existing runtime (Procrastinate + `workflow_runs` + checkpointer). `plan_run` orders the enabled, readable companies (never read first, then oldest `last_checked_at`) and stores that order on the search run. The graph then **loops over batches of 8 companies**: `fetch_batch → normalize → dedup → apply_rules → judge_relevance → store_batch`. After each batch it commits, emits a progress event, and checks a stop flag. The run ends `finished`, `stopped_by_user`, `budget_reached` or `out_of_credit`. The companies not yet read stay on the run, and the next search starts with them (FR-010a). Only one `job_search` run may be active, enforced by a partial unique index on active runs of that workflow.
- **Rationale**: Batches make cost and results visible early without an upfront estimate (clarification 4). Committing per batch means a stop or a credit error never loses finished work (SC-006a). The existing runtime already provides queues, pause and resume, and SSE.
- **Alternatives**: one big fan-out over all companies with LangGraph `Send` (nothing visible until the end, and harder to stop cleanly); a batch size chosen by the user (YAGNI; 8 is a constant in one place and easy to tune).

## R5. Relevance judging (rules, then AI)

- **Decision**:
  - **Rules (pure domain, free)** run first on every job. Skip when: the title matches none of the role words or synonyms; the title contains an avoid word; the location is in the blocked list; or the posting is older than the age limit (default 30 days). A missing fact never skips a job (FR-027), and every skip records the rule.
  - **AI** judges only the jobs that pass the rules and have not been judged before (FR-026), using the new prompt **`judge_relevance` v1** on the **fast** tier.
  - **Input** is one bounded profile card (target roles, seniority, years, key skills, preferred locations and work modes) and up to **10 job cards per call**. A job card holds title, company, location, work mode, rule-extracted skills and years, and a sanitized excerpt of the description of at most **1,200 characters**.
  - **Output** is a strict schema: a list of `{job_ref, relevant: bool, reason ≤ 160 chars}`.
  - **Business checks** on the output: every `job_ref` must be one of the inputs, each input must appear exactly once, and reasons must be non-empty. One repair is allowed. After that, the jobs in that call fall back to rules only and are marked "not checked by AI" (FR-028).
- **Rationale**:
  - Cheap rules remove most of the noise before any tokens are spent.
  - Bounded cards plus an excerpt keep tokens low. This was Ravi's note on the efficient model, recorded as FR-035a.
  - The step has no tools and a strict schema, which satisfies constitution III for raw job text. Its output is a yes/no and a reason, so it cannot add facts about the person (II).
  - The fast tier is the measured default for structured extraction (ADR-11). The relevance eval decides whether it is good enough (R6).
- **Alternatives**:
  - Full job descriptions: about 5 to 10 times more tokens for little gain.
  - One job per call: repeats the profile card on every call.
  - A separate `extract_job_facts` call before judging, as in the architecture's W3b sketch: doubles the calls. The rules extract skills and years deterministically instead.

## R6. Relevance evaluation set and model choice

- **Decision**: `backend/evals/judge_relevance/` holds **2 synthetic profiles** (backend/Python mid-level; frontend/React junior) and **60 synthetic postings** with labels. The postings include true matches, near misses (a Java-only backend role, a senior manager title, the right title in a blocked city), unrelated roles that slip past the title rules, injection attempts, and postings missing a location or date. The eval runner from 001 is extended with a task that scores precision and recall of `relevant` against the labels, cost per job, p95 latency, unusable answers, and **injection-affected decisions (must be 0)**. Gate: precision ≥ 0.90 and recall ≥ 0.90 (SC-003), and cost per full search under $0.25 at the measured cost per job (SC-006). Pick the cheapest tier that passes, as in `docs/how-we-choose-a-model.md`; also run the cheaper model if `models.yaml` gets one with a checked price. Repeat each case 3 times to measure consistency (lesson from 001).
- **Rationale**: Constitution IV: a prompt passes its evaluation set before it becomes active. SC-003 needs a labelled set to measure against.
- **Alternatives**: real postings (they contain recruiters' personal data and break VIII); no eval for v1 (against the constitution).

## R7. Out of credit versus rate limit

- **Decision**: In `platform/llm/openai_adapter.py`, an `openai.RateLimitError` whose error code is `insufficient_quota` becomes `AiUnavailable("out_of_credit", provider_message=...)` and is **not retried**. The message is sanitized and capped at 300 characters. `out_of_credit` is added to `PAUSE_REASONS`, so 001's resume ingest also pauses on it (instead of retrying forever) and resumes on "Check again". All other 429s, 5xx errors and timeouts stay `RetryableLlmError`, with the existing bounded retry. The search workflow turns `out_of_credit` and `budget_reached` into the run's stop reason and shows the message.
- **Rationale**: OpenAI returns HTTP 429 with `error.code = "insufficient_quota"` ("You exceeded your current quota…") when the account has no credit. That is distinct from `rate_limit_exceeded`. Today's adapter maps all 429s to retryable (`openai_adapter.py:81`), which would loop. Covered by the adapter contract tests with a recorded 429 body for each code.
- **Alternatives**: parse the message text (fragile; the code field is stable); treat every 429 as fatal (real rate limits would then stop searches needlessly).

## R8. Dedup

- **Decision**: Exact merge on (a) a canonical URL (lower-case host, tracking parameters and fragment removed, trailing slash dropped) or (b) the ATS vendor plus requisition id. Fuzzy candidates: same company (normalized name) **and** same city (alias-aware) **and** a rapidfuzz `token_set_ratio` on normalized titles ≥ 92. These create a `possible_duplicate` pair for the person to merge or dismiss (FR-021); they are never merged automatically. A pasted job is matched by canonical URL first, then by the fuzzy rule.
- **Rationale**: Exact keys are certain. Similar titles at the same company are often different openings ("Backend Engineer II" vs "Backend Engineer III"), so the person decides (SC-008: no uncertain merges). rapidfuzz is already a dependency.
- **Alternatives**: embedding similarity (costs AI, and is opaque); automatic fuzzy merge (the spec forbids it).

## R9. Proposing search rules

- **Decision**: A **deterministic** proposer (pure domain) builds the first rule set from preferences and the confirmed profile. Target roles become title words, plus synonyms from a shipped synonym table (`backend/seed/title_synonyms.yaml`, for example "backend engineer" → "backend developer", "software engineer (backend)", "SDE backend"). Key skills become stack keywords. Seniority, years, preferred and blocked locations, work modes, and a default age limit of 30 days are copied across. Each rule records its origin (`preference:target_roles[0]`, `profile:skills`, `synonym_table`, `user`). **No AI rule proposal is built in this feature.** FR-003 makes AI optional, the deterministic proposal meets FR-001, and the relevance step already covers wording the rules miss. An AI "suggest more synonyms" button can come later.
- **Rationale**: Free, predictable and testable, and it works without a key (US2 scenario 3). Fewer prompts means fewer evals.
- **Alternatives**: an AI proposal by default (needs another prompt and eval, and costs money before the first search).

## R10. Shipped company list (seed)

- **Decision**: `backend/seed/companies.yaml` holds only company columns: `key` (a stable slug), name, city, website, careers URL, ATS vendor, board id, resolution status (`verified` / `unresolved` / `check_manually`) and `seed_version`. It is built from Ravi's sheet; contacts and notes are never copied (VIII). A seed loader runs at startup after migrations. It inserts new keys and updates rows with `origin = built_in AND user_modified = false AND deleted = false`; it never touches rows the person changed, hid or deleted (FR-018), and deletions by the person are remembered as a tombstone so a built-in company is not re-inserted. **Prerequisite (maintainer)**: Ravi provides the sheet's company columns and, ideally, a resolution pass for groups B, F and J. Without it, unresolved rows ship as `check_manually`. Tests and the e2e journey use a **synthetic** seed (`tests/fixtures/companies/`) with recorded board responses.
- **Rationale**: This is the architecture §8 design. Keeping the seed separate from the migrations makes list updates a data change, not a schema change.
- **Alternatives**: seed inside an Alembic migration (every list update would need a migration, and user edits are harder to respect).

## R11. Spreadsheet import and export

- **Decision**: CSV with a header row: `name,city,website,careers_url,ats_vendor,board_id,hidden`. Import is a two-step preview and confirm. The preview lists rows to add, rows to update and invalid rows with reasons; matching is by careers-URL host plus name; nothing changes until the person confirms (US3 scenario 6). Export writes the same columns, so an export re-imports with no changes. The file is limited to 1 MB and 2,000 rows.
- **Rationale**: A spreadsheet is how the list is maintained today. Round-trip compatibility is testable.
- **Alternatives**: XLSX (an extra dependency for no gain); import without a preview (risky with bulk edits).

## R12. User-added companies (W8)

- **Decision**: When the person adds a company by careers URL, HireTitan runs career-ops `discover-ats.mjs` (read-only) through `CareerOpsPort`, shows the suggested vendor and board with its live job count, and saves it as `user_confirmed` only when the person accepts. If there is no match, the company falls back to the careers-page route (R3), or to `check_manually` if that page can't be read either.
- **Rationale**: FR-017. The same tool supports the maintainer's resolution pass for the seed.
- **Alternatives**: guessing the board from the URL (unreliable for branded pages, per feasibility group B).

## R13. Home page, lists and performance

- **Decision**: Routes: `/` is Explore (with the setup checklist on top until setup is done), `/applied`, `/jobs/:id`, `/search/rules`, `/search/runs/:id` (summary, with the skipped jobs), and `/companies`. Lists use keyset pagination on `(sort_key DESC, id)` with a page size of 25, where `sort_key = coalesce(posted_at, first_seen_at)`. There is an index on `jobs(state, sort_key DESC, id)`. Filters cover source, company, work mode and location. Search progress uses the existing NOTIFY → SSE events.
- **Rationale**: SC-010 (first screen under 2 s with 1,000 jobs) is easy with an index and a 25-row page. Feature 001's review flagged unbounded lists, so every new list is paged from the start.
- **Alternatives**: offset pagination (slower on deep pages, and unstable while a search is adding rows).

## R14. Testing approach

- **Decision**:
  - **Contract tests**: (a) `CareerOpsPort` against recorded `scan.mjs --json` output plus the request-allowlist test through a recording proxy; (b) `CareersPageSource` against recorded HTML pages and robots.txt; (c) the OpenAI adapter against recorded 429 bodies (`insufficient_quota`, `rate_limit_exceeded`).
  - **Workflow tests**: W3 with a fake `CareerOpsPort` and the scripted fake LLM, including stop, budget, out-of-credit and continuation.
  - **Domain unit tests**: rules, dedup, the proposer.
  - **Database**: real Postgres via Testcontainers.
  - **Security**: an injection set for job text.
  - **End to end**: a Playwright journey with the synthetic seed.
  - No live network in CI.
- **Rationale**: Constitution V: fakes only for external job sources, CLIs, the LLM and the clock; contract tests for every adapter.
- **Alternatives**: live calls in CI (flaky, and against the sources' interests).

## R15. Cost check for SC-006

- **Decision**: Expect about 150 jobs to pass the rules on a first full search of about 40 readable companies. At 10 jobs per call, that is about 15 calls of roughly 3,000 input and 600 output tokens. At fast-tier prices ($0.75 per 1M input, $4.50 per 1M output) that is about $0.005 per call, or **about $0.08 per first search**. Later searches judge only new jobs, so they cost cents. The eval measures the real cost per job, and the SC-006 test multiplies it by the job count of the synthetic full run.
- **Rationale**: This shows the $0.25 ceiling is comfortable without relying on an upfront estimate in the product (clarification 4).
- **Alternatives**: none needed.
