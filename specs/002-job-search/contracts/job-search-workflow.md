# Contract: W3 `job_search` workflow, `CareerOpsPort`, `judge_relevance` prompt

## W3 `job_search` (LangGraph, on the 001 runtime)

Started by `POST /search/runs`. Workflow name `job_search`, one active at a time. State is checkpointed in schema `lg`. The run row is `workflow_runs`, with `search_runs` holding the search-specific counts.

```text
plan_run ─▶ next_batch ─┬─▶ fetch_batch ─▶ normalize ─▶ dedup ─▶ apply_rules ─▶ judge_relevance ─▶ store_batch ─┐
                        │                                                                                         │
                        └──(no companies left, stop requested, budget_reached, out_of_credit)──▶ finish ◀──────────┘ (loop back to next_batch)
```

| Node | Type | Input → Output | Rules |
|---|---|---|---|
| `plan_run` | D | approved rule set, companies → `company_order`, `next_index` | Continues a previous run's leftover companies first (FR-010a); then readable companies never read, then oldest `last_checked_at`. Hidden, deleted and unreadable companies are excluded |
| `next_batch` | D | → the next 8 company ids, or the end | Checks `stop_requested` and the last batch's stop reason |
| `fetch_batch` | S | companies → raw postings per company | Board companies go through `CareerOpsPort.scan`; `careers_page` companies through `CareersPageSource` (US3). **Each company is isolated**: an error is recorded in `search_run_companies` and the rest continue (FR-011) |
| `normalize` | D | raw → `Posting` | Sanitize (001 `platform/untrusted`), screen for injection and store the flags, parse city, country, work mode and date by rules (never guessed), canonical URL, `skills_found`, `years_found` |
| `dedup` | D | postings → new jobs and seen-again jobs | Exact (canonical URL; vendor + requisition id) → merge and update `last_seen_at` and sources; fuzzy (R8) → `possible_duplicates`. Seen-again jobs keep their state and decision (FR-026) |
| `apply_rules` | D (pure domain) | new jobs + rules → `skip(reason)` or `pass` | Skip rules from data-model `SearchRules`; a missing fact never skips (FR-027) |
| `judge_relevance` | L fast | passed jobs → `relevant`/`not relevant` + reason | Batches of up to 10 job cards per call; only jobs never judged. In `rules_only` mode, or when the AI is unavailable, jobs go to Explore as "not checked by AI". `AiUnavailable("budget_reached" \| "out_of_credit")` stops the run after this call; the jobs in the failed call are stored as "not checked by AI" |
| `store_batch` | D | decisions → rows | One transaction per batch: jobs, sources, decisions, counts, `next_index`, `ai_cost_usd`; then emits `search.batch_done` (FR-008) |
| `finish` | D | → `outcome`, `stop_message` | `finished`, `stopped_by_user`, `budget_reached`, `out_of_credit`. An unexpected error → `failed`, with finished batches kept |

Notes:
- **No interrupt.** Results go straight to Explore. Every decision is visible and reversible (restore, applied, delete), as constitution I requires.
- **No outbound actions.** The only network calls are career-ops (allowlisted hosts), careers pages (robots.txt) and the LLM provider.

## `CareerOpsPort` (external CLI)

```text
scan(companies: list[BoardRef]) -> ScanResult        # BoardRef = {company_id, ats_vendor, board_id}
discover(careers_url: str) -> DiscoveryResult | None # vendor, board_id, live_jobs
```

- The adapter writes `portals.yml` into HireTitan's own career-ops data folder (`<data>/career-ops/`, never the maintainer's), runs `node scan.mjs --json` with a timeout of 120 s per batch, and parses the JSON into `ScanResult {per_company: {company_id: ok(postings) | error(message)}}`.
- A provider not in the enabled list (R2) is never written to `portals.yml`.
- **Contract tests** (constitution V):
  - recorded `scan.mjs --json` outputs, one per enabled provider plus an error case, parse correctly;
  - the request-allowlist test runs the real pinned career-ops against recorded responses through a recording proxy and fails on any host or method outside the list.
- `FakeCareerOps` (in tests) returns scripted results per company. It is used in workflow and API tests.

## `CareersPageSource` (job source, US3)

`read(company) -> PageResult(ok(postings) | blocked | unreadable(message))`. It honours robots.txt, keeps at least 2 s between requests to the same host, uses an ETag/Last-Modified cache and an honest User-Agent. It tries JSON-LD, then link heuristics, then (with AI available) `extract_jobs_from_page` v1. Contract tests use recorded pages: JSON-LD, plain list, JavaScript-only (→ unreadable), and robots-disallowed (→ blocked).

## Prompt `judge_relevance` v1

`backend/src/hiretitan/prompts/judge_relevance/v1/{system.md, user.md.j2, schema.py, meta.yaml}`, tier `fast`, `max_output_tokens` 1,200.

- **Input (rendered, delimited as untrusted)**:
  - **profile card**: target roles, seniority, years, key skills (≤ 30), preferred locations, work modes. Built from the confirmed profile and preferences only.
  - **job cards** (≤ 10): `{ref, title, company, location, work_mode, skills_found, years_found, excerpt ≤ 1,200 chars}`.
- **Output schema**: `{decisions: [{ref: str, relevant: bool, reason: str (1–160)}]}`.
- **Business checks**: the refs exactly match the input refs, each once; reasons are not empty and contain no URLs. One repair, then fallback to rules only for that call (FR-028).
- **Never**: tools, follow-up instructions from job text, facts about the person not on the profile card.

## Test matrix (names reference requirement and scenario IDs)

| Test | Covers |
|---|---|
| `test_US1_AS1_search_adds_relevant_jobs_per_batch` | US1 AS1, FR-008, SC-006 (first jobs before the end) |
| `test_US1_AS3_unrelated_titles_are_skipped_with_reason` | US1 AS3, FR-022, FR-024 |
| `test_US1_AS4_blocked_location_skipped` | US1 AS4, SC-004 |
| `test_US1_AS5_restore_keeps_job_in_explore_on_next_search` | US1 AS5, FR-025 |
| `test_US1_AS6_seen_again_job_is_not_judged_again` | US1 AS6, FR-026, SC-007 |
| `test_US1_AS7_no_key_runs_rules_only_and_says_why` | US1 AS7, FR-033 (AI unavailable), FR-028 |
| `test_US1_AS8_out_of_credit_stops_keeps_batches_and_shows_message` | US1 AS8, FR-010a, SC-006a |
| `test_US1_AS8_budget_reached_stops_and_next_search_continues` | US1 AS8, FR-010a |
| `test_US1_AS9_stop_after_current_batch` | US1 AS9, FR-010 |
| `test_FR009_second_search_conflicts` | FR-009 |
| `test_FR011_failing_company_does_not_stop_others` | FR-011, SC-009 |
| `test_FR027_missing_location_never_skips` | FR-027 |
| `test_FR028_unusable_ai_answer_falls_back_to_rules` | FR-028 |
| `test_FR035a_job_card_is_bounded` | FR-035a (excerpt ≤ 1,200, ≤ 10 per call) |
| `test_SC011_injected_postings_do_not_change_decisions` | SC-011, FR-038, FR-039 |
| `test_R7_insufficient_quota_is_not_retried` (adapter contract) | FR-010a, R7 |
| `test_R2_careerops_requests_stay_in_allowlist` (contract) | FR-012, FR-013, constitution VII |
