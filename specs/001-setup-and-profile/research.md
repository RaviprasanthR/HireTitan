# Research: Setup and Profile (first slice)

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Date**: 2026-11-03

Most technology choices were made and approved in [`docs/architecture.md`](../../docs/architecture.md) (ADR-01…11). This file settles what was left open for feature 001 and records the version/licence checks the architecture asked for. Format: **Decision · Rationale · Alternatives**.

Versions and licences were checked on PyPI and npm on 2026-11-03. They are **floors**: implementation pins the exact versions in `uv.lock` / `package-lock.json` in the setup task, and the licence gate re-checks them on every PR.

---

## R1. Dependency versions and licences

| Package | Version seen | Licence | Note |
|---|---|---|---|
| Python | 3.12+ | — | Constitution. All packages below support it. |
| fastapi | 0.162 | MIT | |
| pydantic / pydantic-settings | 2.14 / 2.16 | MIT | |
| SQLAlchemy (async) | 2.1 | MIT | |
| alembic | 1.20 | MIT | |
| psycopg (3, binary) | 3.3 | **LGPL-3.0** | Used unmodified as a library, which is compatible with shipping HireTitan under MIT. The licence gate allows LGPL for runtime libraries. Required by Procrastinate and the LangGraph checkpointer. |
| procrastinate | 3.10 | MIT | **ADR-03 check done**: MIT, asyncio, psycopg 3. |
| langgraph | 1.2 | MIT | |
| langgraph-checkpoint-postgres | 3.2 | MIT | Uses schema `lg`. |
| openai | 3.43 | Apache-2.0 | Responses API + structured outputs. |
| tiktoken | 0.14 | MIT | Token estimate for the budget guard. |
| pdfplumber (+ pdfminer.six) | 0.11 | MIT | ADR-06. Per-character colour/size for hidden-text detection. |
| pypdf | 6.21 | BSD-3 | Encryption check, page count. |
| python-docx | 1.2 | MIT | ADR-06. |
| phonenumbers | 9.0 | Apache-2.0 | Phone detection for contact masking (R4). |
| rapidfuzz | current | MIT | Near-verbatim bullet matching in the grounding check (R5). |
| sse-starlette | 3.6 | BSD-3 | SSE endpoint (ADR-08). |
| testcontainers | 4.15 | Apache-2.0 | Real PostgreSQL 16 in tests. |
| import-linter | 2.15 | BSD-2 | Layer and module contracts. |
| react | 19.3 | MIT | ADR-10. |
| vite | 8.3 | MIT | |
| tailwindcss | 4.3 | MIT | v4 CSS-variable theme; shadcn/ui (copied components, MIT). |
| @tanstack/react-query | 5.105 | MIT | |
| react-router | 8.5 | MIT | |
| react-hook-form + zod | 7.91 + 4.6 | MIT | |
| openapi-typescript | 7.13 | MIT | Typed client from FastAPI's OpenAPI. |
| vitest / @playwright/test | 5.1 / 1.64 | MIT / Apache-2.0 | |

**Rationale**: everything is permissive (or LGPL used unmodified), as constitution VIII and the MIT release need. **Alternatives**: none needed; PyMuPDF is still excluded (AGPL, ADR-06).

## R2. Default OpenAI models per tier and the price table

- **Decision**: `fast` = **`gpt-5.4-mini`**, `strong` = the current OpenAI flagship, set in the price table at implementation time. Both are **fixed defaults** in this slice (clarification Q2) and live in a versioned data file, `platform/llm/models.yaml` (tier → model per provider, plus price per 1M input, cached input and output tokens). The prices are checked by hand against OpenAI's official pricing page during implementation; the file records the date they were checked.
- **Rationale**: third-party price lists (Nov 2026) agree on the mini tier (≈ $0.75 in / $4.50 out per 1M tokens) but disagree on the flagship. A two-page resume is ≈ 1.5k tokens, plus ≈ 1k of prompt and schema, with ≈ 2k tokens of output. That's ≈ $0.011 per extraction on mini, or ≈ $0.022 with one repair attempt, well under SC-007's $0.05. The ADR-11 eval (R10) compares mini with the strong model on the synthetic set and may change the `fast` default.
- **Alternatives**: nano (≈ $0.20 / $1.25), which is cheaper but riskier for nested extraction, so the eval tests it as a candidate; hard-coding the price in code (rejected, because prices change).

## R3. Checking the AI key

- **Decision**: check the key at worker start-up, when the user clicks "Check again" (an API request that enqueues a `check_provider_key` task), and whenever an AI call gets 401/403. The check uses **`GET /v1/models`** (models list): it costs nothing, uses no tokens, and still proves the key is accepted. The result goes into `app.provider_status` (status `working | missing | rejected | unreachable`, checked_at, message). **The key is never stored.** A missing key (`OPENAI_API_KEY` empty) is detected without a network call. `unreachable` (network down) is shown as a warning and doesn't pause tasks; the task's own retries handle it.
- **Rationale**: the spec asks for "a test call" (FR-029); listing models proves the key without spending budget. Keeping the status in the database lets the api (which never calls the LLM) show what the worker found.
- **Alternatives**: a 1-token completion (costs a little and touches budget logs); checking in the api process (breaks "api never calls an LLM", architecture §2).

## R4. Contact masking before AI calls (clarification Q1, FR-008a)

- **Decision**: a deterministic `mask_contacts` step after sanitizing:
  - emails: an RFC-5322-lite regex;
  - phones: `phonenumbers.PhoneNumberMatcher` with region taken from the preferences country (default `IN`), plus a leniency fallback for international formats;
  - links: `http(s)://` URLs and bare profile-host links (`linkedin.com/in/…`, `github.com/…`, `gitlab.com/…`).

  Each match is replaced with `[[EMAIL_1]]`, `[[PHONE_1]]` or `[[LINK_1]]`. The originals are kept in the run state (never sent) and go straight into the review's contact section. The AI output schema has **no fields** for email, phone or links, so it can't return them. Any placeholder that shows up in the AI output is removed before review.
- **Rationale**: removes the most sensitive identifiers at almost no cost to extraction quality. SC-009 is testable by inspecting the prompt the fake LLM receives.
- **Alternatives**: no masking (rejected by Ravi); masking the name too (unreliable without NER, rejected by Ravi).

## R5. Grounding check algorithm (FR-011, SC-004)

- **Decision**: pure domain code, `profile/domain/grounding.py`. The source is the sanitized, unmasked visible text, normalized (NFKC, casefold, whitespace collapsed, punctuation except `+#.` turned into spaces).
  - **Skills, employers, titles, institutions, qualifications, certification names, project names**: the normalized value must appear as a substring of the normalized source.
  - **Dates**: each extracted date (year, or month + year) must match a date token found in the source by the same date parser ("Jan 2021", "01/2021", "2021"). "Present" / "Current" must appear for `current = true`.
  - **Bullets**: must match a source line with rapidfuzz `token_set_ratio ≥ 92`, and **every number** (digit sequence, %, ₹/$ amounts, "10x") in the bullet must appear in the source.
  - **Summary**: kept only if it matches source text (`partial_ratio ≥ 90`); otherwise it's dropped with the reason "summary not found in your resume" (the extraction prompt asks for verbatim copying).

  Every failure becomes a `DroppedItem(path, value, reason)`.
- **Rationale**: deterministic and explainable; no "LLM judging an LLM". Thresholds are tuned against the synthetic set and recorded in the eval report.
- **Alternatives**: embedding similarity (non-deterministic, opaque); exact matching for bullets (too brittle for line-wrapped PDFs).

## R6. Hidden-text detection in PDFs (FR-005)

- **Decision**: in `platform/untrusted/hidden_text.py`, using pdfplumber's character objects. A character is **hidden** if any of these hold:
  - its fill colour (`non_stroking_color`) is within ΔE < 8 of the background (white, unless a filled rectangle under the character says otherwise);
  - its size is < 4 pt;
  - its bounding box lies outside the page's crop box;
  - it uses render mode 3 (invisible), read from the pdfminer graphic state where available.

  Hidden characters are grouped into runs (strings) with their page numbers, **removed from the extraction input**, and reported. Hidden runs are also screened for injection (R7) but never cause a pause, because they are already excluded.
- **Rationale**: these cover the common white-text and tiny-text tricks. A planted-text test set (SC-005) proves it.
- **Alternatives**: rendering pages and comparing OCR (heavy, needs OCR, which is out of scope).

## R7. Injection screening and severity (FR-006, FR-007)

- **Decision**: a rule list in `platform/untrusted/screen.py` (versioned, test-covered). Each rule has an id, a matcher and a severity:
  - **high**: instructions addressed to an AI ("ignore (all|previous) instructions", "you are now …", "system prompt", "as an AI"), role/turn markup (`<|im_start|>`, `### system`, `[INST]`), tool or function-call syntax, and requests to output links or contact data;
  - **medium**: "rate this candidate", "rank this resume first" and similar text aimed at a reader-model, base64-looking blobs > 200 chars;
  - **low**: unusual Unicode (bidi controls removed by sanitizing), excessive repetition.

  Any **high** signal in the *visible* text interrupts W1 before `extract_profile` (`awaiting_review`, kind `injection_decision`). The user chooses "Continue extraction" or "Fill in by hand".
- **Rationale**: simple, explainable rules matching constitution III; the attack set guards against regressions.
- **Alternatives**: an LLM classifier (costs money, can itself be injected).

## R8. Parsing details (FR-001, FR-004, FR-008)

- **Decision**:
  - **Type sniffing** by magic bytes: `%PDF-` means PDF; a ZIP with `word/document.xml` means DOCX. The extension alone is never trusted.
  - **Encrypted PDF**: `pypdf.PdfReader.is_encrypted`, rejected.
  - **Size**: ≤ 10 MB, checked while streaming the upload. Page limit: 20.
  - **PDF text**: pdfplumber text from visible characters only, with bullet glyphs (•, ▪, –, *) kept as line starts.
  - **DOCX**: body paragraphs in order, tables (row by row), headers/footers, and text boxes (`w:txbxContent`, read via the XML tree).
  - **No readable text**: fewer than 200 visible characters means "no readable text" (scanned PDF), and the user is offered the paste or manual options.
  - **Length cap** for AI input: 30,000 characters after sanitizing. Anything beyond is cut, and the review says from where.
- **Rationale**: matches ADR-06, catches disguised files, and keeps cost bounded.
- **Alternatives**: python-magic (needs libmagic on Windows; rejected for portability).

## R9. Pausing for key and budget problems (FR-030, FR-032)

- **Decision**: `workflow_runs.status` gains **`paused`** with `pause_reason ∈ {key_missing, key_rejected, budget_reached}`. When the budget guard or adapter reports `budget_blocked`, or the key is rejected or missing, the node raises `AiUnavailable(reason)`. The task runner catches it, marks the run `paused`, and **doesn't fail the Procrastinate job** (it ends normally). The LangGraph checkpoint keeps the state before the failed node.
  - **Resuming**: on worker start-up after a successful key check, and right after the budget cap is raised in Settings, a `resume_paused_runs` task re-defers every paused run whose reason is cleared. Each re-deferred run continues from its checkpoint.
  - **Budget**: the period is a calendar month in UTC; spend = sum of `llm_calls.cost_usd` for the month; estimate = input tokens (tiktoken) × input price + `max_output_tokens` × output price (worst case).
- **Rationale**: no lost work and no wasted retries. Checkpoints already provide durable state.
- **Alternatives**: keep retrying with backoff (wastes calls and hides the cause); fail and ask the user to restart the upload (loses work, which the spec forbids).

## R10. Extraction evals (SC-003, SC-007, ADR-11)

- **Decision**: `backend/evals/extract_profile/` holds 12 synthetic resumes (PDF and DOCX; single- and two-column; fresher, mid and senior; one non-English, one with tables, one with text boxes), each with an expected-facts YAML file. A runner computes field-level precision and recall (employers, titles, dates, skills, education), cost and latency per model. It's run on demand with Ravi's key, counted against the budget, and its report goes in the PR. v1 doesn't gate (the eval gate applies from v2), but the report decides the `fast` default (ADR-11).
- **Rationale**: SC-003 needs measurement, and the same set seeds future v2 gating.
- **Alternatives**: real resumes (forbidden: no personal data in the repo).

## R11. Pending review and unsaved edits (FR-016, US1-AS9)

- **Decision**: the W1 interrupt payload (the extraction, dropped items, flags and the current profile for comparison) is copied into **`app.profile_reviews`**, one row per run. The user's in-progress edits are **autosaved** to `profile_reviews.draft` through `PUT /api/v1/profile/reviews/{id}/draft` (debounced 1 s). This doesn't resume the graph. Confirm sends the final values, and the api enqueues `resume_run(run_id, decision)`. At most one review can have `status = open` (partial unique index).
- **Rationale**: keeps drafts queryable without touching LangGraph internals, and the Review list reads from the same row.
- **Alternatives**: storing drafts in the checkpoint (each autosave would mean a graph update); browser-only drafts (lost on another browser or after a cache clear).

## R12. Manual profile creation and edits (FR-019, FR-020)

- **Decision**: no workflow. `POST /api/v1/profile/versions` with the full profile body creates a version with `created_by = manual` (or `manual_edit` when a current version exists). The same validation applies (FR-018 rules), but no grounding check, because the user's own entries are their confirmed facts.
- **Rationale**: no AI and no pause, so a workflow adds nothing (same principle as "Preferences are not a workflow" in the architecture).

## R13. Deleting data (FR-034, FR-035)

- **Decision**:
  - **Delete a file**: delete the `resume_files` row and its stored file (when no other row references the hash). Any open review and its run are cancelled. `profile_versions.source_file_id` is set to NULL with `source_deleted = true`.
  - **Delete all**: the request body must be `{"confirm": "DELETE"}`. First, every non-final run is cancelled and queued jobs are aborted through Procrastinate. Then, in one transaction: truncate every `app` table, the LangGraph `lg` tables and the Procrastinate job tables. After that, remove the files folder and re-seed defaults (settings, provider status). `.env` is never touched.
- **Rationale**: meets constitution VIII and SC-008; the typed word prevents accidents.

## R14. Running it: docker compose in this slice

- **Decision**: this slice ships `docker-compose.yml` with `db` (postgres:16), `migrate` (one-shot Alembic), `api` and `worker`, using one backend image (Python 3.12 slim). Node/career-ops is **not** added yet (feature 002 needs it). The SPA is built in a multi-stage step and served by `api`. Ports are published on `127.0.0.1` only. For development: `db` in Docker; api, worker and web native (`uv run`, `npm run dev`).
- **Rationale**: constitution VIII requires `docker compose up` to work. The first slice is the right time to prove it on Windows, macOS and Linux.
- **Alternatives**: postponing compose to the release (risk found late).

## R15. CI gates

- **Decision**: a GitHub Actions workflow on PRs to `master` runs:
  - backend: `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports`, `pytest` (Testcontainers; coverage ≥ 90% for `*/domain` + `*/application`, ≥ 80% overall), `pip-audit`, and a licence check (`pip-licenses` with an allowlist of MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, and LGPL for runtime libraries);
  - frontend: `tsc --noEmit`, `eslint`, `vitest --coverage`, `npm audit --omit=dev`, `license-checker` with the same allowlist;
  - a Playwright smoke journey against the compose stack with the fake LLM (`HIRETITAN_LLM=fake`).
- **Rationale**: constitution gates. The fake LLM keeps CI free of keys and cost.
