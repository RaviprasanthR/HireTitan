# HireTitan — Architecture

Status: **APPROVED by Ravi 2026-11-03** (section-by-section review) · Branch: `001-setup-and-profile`

This is the system-wide design every feature plan (`specs/NNN-*/plan.md`) builds on. It covers what cuts across features: processes, layers, the AI layer, workflow conventions, the workflow/node catalogue, data ownership and the open technical choices (§12 ADRs). Per-feature details (exact tables, endpoints, prompts, screens) belong in each feature's plan. It must comply with the [constitution](../.specify/memory/constitution.md); where they differ, the constitution wins. Changes after approval go through a PR like any other change.

Input: `docs/clarified-requirements.md` (binding) and `docs/archive/specs-v0/02-design.md` (earlier design, reused where it still fits).

---

## 1. Shape of the system

HireTitan is a **modular monolith**: one Python backend codebase run as two processes (API and worker), one PostgreSQL database, one React single-page app. It runs on the user's machine with `docker compose up`. It is **not** a free-roaming autonomous agent: every AI feature is a **fixed workflow** (a LangGraph graph) of deterministic steps, a few LLM steps with strict output schemas, and explicit pauses for the user's approval.

```mermaid
flowchart LR
    user([User's browser]) -->|HTTP + SSE, localhost| api

    subgraph host["User's machine (docker compose)"]
        api["api<br/>FastAPI · serves the SPA"]
        worker["worker<br/>task runner · LangGraph runs"]
        db[("PostgreSQL 16<br/>app data · task queue · checkpoints")]
        files[("data volume<br/>resumes · exports · career-ops data")]
        cops["career-ops (Node 22)<br/>bundled, pinned, run as subprocess"]
        api --- db
        worker --- db
        api --- files
        worker --- files
        worker -->|subprocess, JSON| cops
    end

    worker -->|user's key| llm["LLM provider<br/>OpenAI · Anthropic · Gemini · OpenAI-compatible"]
    cops -->|public ATS APIs| ats["Greenhouse · Lever · Ashby · Workday · …"]
    worker -->|robots.txt, rate-limited| careers["Company careers pages"]
    worker -->|read-only OAuth| gmail["Gmail job alerts"]
    worker -->|user's key| agg["Adzuna · Jooble · Careerjet"]
```

Nothing in the system can send email, messages or applications (constitution I). The only outbound traffic is: the LLM provider the user configured, the job sources the user enabled, and Gmail read-only.

## 2. Runtime processes and containers

| Process | What it runs | Notes |
|---|---|---|
| `db` | `postgres:16` | Named volume. One database `hiretitan`, schemas `app` (our tables) and `lg` (LangGraph checkpoints). |
| `api` | FastAPI (uvicorn) | REST `/api/v1`, SSE event stream, serves the built SPA as static files. Bound to `127.0.0.1` only (local only, no login). Never calls an LLM itself; it enqueues tasks. |
| `worker` | Procrastinate worker | Claims tasks from the Postgres queue, runs LangGraph workflows, source fetches, career-ops subprocesses, rendering. Runs N concurrent tasks inside one process (asyncio). |
| `web` (dev only) | Vite dev server | In production the SPA is built into the backend image and served by `api`. |

**One backend image** (Python 3.12 + Node 22 + career-ops pinned at v1.38.0) is used for both `api` and `worker` with different commands. A one-shot `migrate` step (Alembic) runs before `api` starts.

Development (Ravi): `db` in Docker; `api`, `worker` and `web` run natively with `uv` and `npm`.

## 3. Backend layers and module layout

**Package by feature, layers inside** (the usual modular-monolith layout):

```
backend/
  src/hiretitan/
    profile/         resume upload, parsing, profile versions          (001)
    preferences/     job preferences                                    (001)
    companies/       company list, seed loader, CSV import/export       (002)
    jobs/            search rules, search runs, rule filter, AI check, scoring (002)
    applications/    tracking, follow-ups, data export                  (003)
    outreach/        drafts                                             (004)
    resumes/         tailoring, content suggestions, rendering          (005)
    interviews/      (006, R2)
      └─ each module: domain/ · application/ · infra/ · api/ (+ adapters/ only where it owns a boundary)
    platform/        shared building blocks
      llm/           LlmPort, OpenAI adapter (others later), budget guard, validation chain, prompt registry
      runtime/       Procrastinate app + task definitions, workflow runs, LangGraph checkpointer, events/SSE
      untrusted/     sanitize · screen · delimit · hidden-text detection
      storage/ clock/ config/ db/ security/ careerops/
    api_main.py      FastAPI composition root
    worker_main.py   worker composition root
    prompts/         versioned prompt files + output schemas (see §5.4)
  seed/              companies.yaml (company columns only)
  evals/             evaluation sets and runner (per prompt)
  tests/             unit / integration / contract / workflow / api / architecture / security
```

Rules (enforced by import-linter, constitution VI):
- Inside every module: `api → application → domain`; `infra` implements what `application` needs; `domain` imports nothing from frameworks (no FastAPI, SQLAlchemy, LangGraph, pydantic-settings).
- Modules don't reach into each other's internals: they call only another module's public `application` functions (e.g. `jobs` asks `preferences` for the current rules; it never reads its tables).
- Every module may use `platform`; `platform` never imports a feature module.
- `api_main` and `worker_main` are the only composition roots.
- Persistence: SQLAlchemy is used directly in each module's `infra/`, with no extra repository-interface layer (lean architecture). Application code receives repositories by dependency injection.
- **No-send rule:** an architecture test fails the build if any module imports `smtplib`, an email-sending SDK or a messaging SDK, or if an outbound HTTP adapter uses a non-GET method against a host outside the allowlist (OpenAI and other LLM providers, aggregator APIs, Google OAuth).
- **career-ops request allowlist:** career-ops is Node code, so the Python test above can't see it. Each enabled career-ops provider has an allowlist of hosts and HTTP methods (e.g. Workday search is a POST to `*.myworkdayjobs.com`). A contract test runs career-ops against recorded responses through a recording proxy and fails on any request outside the list. Before a provider is enabled, its request paths are checked against the target's robots.txt (see `docs/research/2026-11-03-company-source-feasibility.md`, Keka finding).

## 4. Task and workflow execution

Everything that calls an LLM, fetches a source or renders a file runs in the **worker**, never in an API request.

```mermaid
sequenceDiagram
    participant UI as SPA
    participant API as api
    participant DB as Postgres
    participant W as worker
    UI->>API: POST /api/v1/resumes (upload)
    API->>DB: insert resume_file + task(profile_ingest), NOTIFY
    API-->>UI: 202 {task_id, run_id}
    W->>DB: claim task (SKIP LOCKED)
    W->>W: run graph (thread_id = run_id) until interrupt
    W->>DB: checkpoint (lg schema), run.status = awaiting_review, NOTIFY
    DB-->>API: LISTEN event
    API-->>UI: SSE "run awaiting_review"
    UI->>API: POST /api/v1/runs/{run_id}/resume {approved edits}
    API->>DB: insert task(resume run), NOTIFY
    W->>W: resume graph with Command(resume=…) → save → done
```

Conventions:
- **Queue: Procrastinate** (ADR-03) on the same Postgres. The API defers a task in the same transaction as the data it belongs to; the worker picks it up with `SELECT … FOR UPDATE SKIP LOCKED`, woken by `LISTEN/NOTIFY` (with polling as a fallback). Retries with backoff (e.g. 10 s, 1 min, 5 min), then failed (visible in the UI). Stalled tasks from a crashed worker are detected and retried. Queueing locks limit per-type concurrency (e.g. one search run at a time). Procrastinate's periodic tasks run the daily date check.
- **Workflow runs** (`app.workflow_runs`): one row per graph execution, with the LangGraph `thread_id`, status (`running | awaiting_review | done | failed | cancelled`), and what's waiting for the user. The UI's "Needs your review" list is built from this table.
- **Human approval** uses LangGraph `interrupt()`. Resuming is a new task carrying the user's decision. A paused run costs nothing while it waits.
- **Idempotent nodes:** a node checks for its existing output (keyed by input hash and prompt version) before calling the LLM, so a retried task never pays twice.
- **Progress** goes out as Postgres `NOTIFY` events → `api` → SSE to the browser. No Redis.
- **Manual triggers only** for search runs (requirements §3). The only scheduled job in R1 is the daily `no_response` / follow-up date check, a cheap SQL job (a Procrastinate periodic task).
- **Invalid API key:** when OpenAI rejects the key (401/403), the provider is marked "key invalid", AI tasks are **paused, not failed**, and the dashboard shows a banner to update `OPENAI_API_KEY` in `.env` and restart. Paused tasks continue after that; nothing is lost.

## 5. AI layer

### 5.1 LLM port

```python
class LlmPort(Protocol):
    async def generate(self, req: LlmRequest[T]) -> LlmResult[T]: ...

@dataclass
class LlmRequest(Generic[T]):
    task: str                 # e.g. "extract_profile"
    prompt: PromptVersion     # name + version + rendered system/user parts
    output_schema: type[T]    # Pydantic model
    tier: Literal["fast", "strong"]
    max_output_tokens: int
    untrusted_blocks: list[UntrustedText]   # already sanitized and delimited (§6)

@dataclass
class LlmResult(Generic[T]):
    value: T | None
    outcome: Literal["ok", "repaired", "fallback", "refused", "budget_blocked", "error"]
    usage: Usage              # tokens in/out, cost_usd, latency_ms
    provider: str
    model: str
```

- One adapter per provider family: **OpenAI**, **Anthropic**, **Google Gemini**, and **OpenAI-compatible** (base URL + key; covers Ollama, OpenRouter, Groq, Azure OpenAI and others). Each adapter uses the provider's own SDK and its native structured-output feature when the model supports it. Otherwise it falls back to JSON in the prompt plus strict parsing (constitution IV, "degrade gracefully").
- **OpenAI first** (ADR-02): feature 001 builds only the OpenAI adapter; the others land before the first public release. The port, the fake LLM and all tests are provider-neutral from day one.
- **Model tiers**: workflows ask for `fast` or `strong`, never a model name. Settings map each tier to a model per provider. **Profile extraction uses `fast` for now** (cost); the 001 cost/quality test decides whether to change it.
- **Budget guard** (wraps every adapter): estimates the cost before the call and blocks it with `budget_blocked` if the month's spend plus the estimate would pass the cap. Logs every call to `app.llm_calls` (provider, model, task, prompt version, tokens, cost, latency, outcome). Batch actions (e.g. relevance check on 80 jobs) show an estimate before the user confirms.
- Prices come from a versioned price table shipped with the app and editable in settings, since OpenAI-compatible endpoints vary.

### 5.2 Validation chain

Every LLM output passes, in order:
1. **Schema**: parse into the Pydantic model (bounded lengths, enums, required fields).
2. **Business rules** per task, e.g. relevance reason non-empty; rule count ≤ N; dates sane.
3. **Truthfulness check** for profile-derived outputs (drafts, tailored resume, answer reviews): every number, employer, date and skill in the output must appear in the cited profile facts (constitution II). This is deterministic code, not another LLM call.
4. **Safety**: no URLs or emails other than allowed ones, no echoed injection phrases.

On failure: **one repair attempt** (the error list goes back to the model), then a **defined fallback** per task (e.g. relevance → "unsure", shown to the user; extraction → partial profile marked for manual entry). A failed AI step never crashes a workflow or loses data.

### 5.3 Model use per node
See §7. Rule of thumb: `fast` for extraction, classification and search-rule proposal; `strong` for drafting and tailoring.

### 5.4 Prompts and evals
- Prompts live as files: `prompts/<task>/v<N>/{system.md, user.md.j2, schema.py, meta.yaml}`. `meta.yaml` holds version, tier, max tokens and changelog.
- Every AI-produced artifact stores `prompt_name`, `prompt_version`, `provider`, `model`.
- `evals/<task>/` holds synthetic cases with expected properties. From v2 of a prompt, the eval run for that task must pass on the configured provider before the new version becomes active. The report goes in the PR (constitution IV and workflow).

## 6. Untrusted-input pipeline (constitution III)

All external text (resumes, job descriptions, careers pages, emails, aggregator results, pasted text) goes through:

1. **Sanitize**: Unicode NFKC normalisation, strip control and zero-width characters, collapse whitespace, cap length.
2. **Screen**: flag injection signals (e.g. "ignore previous instructions", role tags, tool-call syntax). Flags are stored and shown, never silently dropped.
3. **Delimit**: wrapped in clearly marked data blocks with a random boundary token.
4. **Quarantined extraction**: only extraction nodes (`extract_profile`, `extract_job_facts`, `extract_jobs_from_page`, `parse_alert_email`, `split_transcript`) ever see raw untrusted text. They have no tools and a strict, bounded output schema.
5. **Privileged nodes** (relevance, scoring, drafting, tailoring) receive only the **structured, length-bounded facts**, never raw text.

A resume is the user's own file but is still treated as untrusted: it could contain hidden text.

Further layers (approved 2026-11-03):

6. **Capability limits** (the strongest layer): the app can't send anything, AI steps have no tools and no internet access, and AI text is rendered as plain text (never HTML or Markdown, which blocks image-link exfiltration).
7. **Grounding check on extraction**: every skill, employer, title, date and number an extraction step returns must appear in the source text (deterministic check); anything not found is dropped and reported. Planted claims can't become facts, and the user still confirms the profile.
8. **Hidden-text detection in PDFs**: while parsing, text that is white-on-white, tiny or outside the page is detected and shown to the user during profile review.
9. **High-severity flags pause the workflow** for the user instead of letting it continue automatically.
10. **Attack test set**: injected job posts, hidden-text PDFs, emails with fake system messages, link-exfiltration attempts. The tests assert bounded fields, raised flags, unchanged rule decisions and no planted links in drafts. They run on every build; the eval variants run on prompt changes.

Residual risk: a source can still simply lie (e.g. claim "remote"). That's bad data the user can see, not an AI takeover.

## 7. Workflow catalogue

Legend: **D** deterministic code · **L** LLM node (tier) · **⏸** interrupt for user approval · **S** source/IO.

### W1 `profile_ingest` (feature 001)
Trigger: resume upload (first time or re-upload).

| # | Node | Type | Input → Output |
|---|---|---|---|
| 1 | `store_file` | D | upload → content-addressed file (sha256); type/size checks (PDF/DOCX) |
| 2 | `parse_document` | D | file → plain text + layout hints (sections, bullets) + **hidden-text report** |
| 3 | `sanitize` | D | text → sanitized text + injection flags |
| 4 | `extract_profile` | L fast | sanitized text → `ExtractedProfile` (contact, summary, experience[] with bullets, education, skills, certifications, links) |
| 5 | `validate_profile` | D | schema + rules (dates ordered, no empty roles) + **grounding check against the source text**; repair/fallback |
| 6 | `diff_with_current` | D | only if a confirmed profile exists → field-level diff |
| 7 | `review_profile` | ⏸ | first time: user edits/approves the profile; re-upload: user accepts/rejects each diff item |
| 8 | `save_profile_version` | D | new immutable profile version, **linked to the resume file it came from**; becomes the source of truth |

Preferences are not a workflow: a plain form saved directly through the `preferences` module (no AI, no pause).

### W2 `search_rules_proposal` (feature 002)
Trigger: user asks for suggestions, or the profile or preferences change. The user can also skip the AI and write the rules by hand.

"Search rules" replace the earlier "search queries": job boards return a company's whole list, so what matters is the rule set the W3 `rule_filter` applies. One concept: AI proposes, the user approves, the rules filter.

| # | Node | Type | Input → Output |
|---|---|---|---|
| 1 | `build_context` | D | confirmed profile + preferences (roles, stack, locations weighted highest) |
| 2 | `propose_rules` | L fast | context → `SearchRules` (title include/exclude keywords, synonyms, stack keywords, locations + work mode, max posting age, rationale) |
| 3 | `validate_rules` | D | bounds, conflicts (same word included and excluded), dedup against existing rules |
| 4 | `approve_rules` | ⏸ | user edits/approves/rejects each rule |
| 5 | `save_rules` | D | approved rule set stored with version; used by W3 |

### W3 `search_run` (features 002 / 002b)
Trigger: user clicks "Search now". **Rules first, then the `fast` model judges the rest** (ADR-12): jobs that pass the rules are judged for relevance in groups of 10; a "rules only" run makes no LLM calls. The run works in **batches of 8 companies**, stores each batch in one transaction, publishes `search.batch_done` and shows the cost so far; Stop, the budget cap and an out-of-credit answer end the run after the batch is stored. As built (002), the graph is `plan_run → fetch_batch → normalize/dedup → rules → judge_relevance → store`, looping over batches. The diagram below is the earlier design and the table is still a fair guide to each step. W3b became the one-node `recheck_job` workflow ("Check again" on one job).

```mermaid
flowchart LR
    plan[plan_run D] --> fan{{per enabled source}}
    fan --> s1[fetch_careerops S]
    fan --> s2["fetch_careers_pages S<br/>JSON-LD → generic parse → (opt) AI fallback"]
    fan --> s3["fetch_gmail_alerts S<br/>per-sender parser → (opt) AI fallback"]
    fan --> s4[fetch_aggregators S]
    s1 & s2 & s3 & s4 --> norm[normalize D]
    norm --> dedup[dedup D]
    dedup --> facts[extract_facts_rules D]
    facts --> rules[rule_filter D]
    rules --> store[store_results D]
```

| Node | Type | Notes |
|---|---|---|
| `plan_run` | D | approved search rules × enabled sources → fetch plan; pushes location/keyword filters into the source request where the board's search supports it |
| `fetch_*` | S | one branch per source (LangGraph `Send`), **isolated**: a failure is recorded on that source's run and doesn't stop the others (constitution VII). career-ops: HireTitan writes its `portals.yml` from the company list and runs `node scan.mjs --json` in its own data folder |
| careers-page parsing | D, then L fast (opt) | 1) schema.org `JobPosting` JSON-LD; 2) generic job-link/title heuristics; 3) only if enabled for that source: `extract_jobs_from_page` (quarantined). robots.txt + rate limit + cache first; failure → "check manually" list |
| alert parsing | D, then L fast (opt) | per-sender template parsers (Naukri, LinkedIn, Indeed, …); `parse_alert_email` (quarantined) only as an opt-in fallback when a template changes |
| `normalize` | D | common `JobPosting` shape (title, company, location(s), url, posted_at, source, description, raw ref) |
| `dedup` | D | exact (canonical URL, ATS requisition ID) → merge; fuzzy (company + title + city) → marked "possible duplicate" for the user to confirm |
| `extract_facts_rules` | D | from title + description: seniority words, years of experience (regex), work mode, locations, stack keywords (matched against the user's stack + a synonym list), pay if stated |
| `rule_filter` | D | the user's rules → **match / maybe / hidden**, each with the deciding rule as the reason; match score = weighted roles + stack + location (from preferences). Only explicit exclusions (blocked cities, excluded title words, max age) hide; nothing is deleted; hidden jobs can be restored |
| `store_results` | D | jobs list (newest first, or by match score), per-source run stats |

No interrupt here: results go straight to the jobs list, where every rule decision is visible and reversible.

### W3b `ai_relevance_check` (feature 002, optional, on demand)
Trigger: the user clicks "Check with AI" on the **maybe** bucket or on selected jobs; the cost estimate is shown first.
`extract_job_facts` L fast (quarantined: raw JD → `JobFacts`, cached per JD hash) → `relevance_check` L fast (facts + profile summary + preferences → `relevant / not_relevant / unsure` + visible reason; batched ~10 jobs per call) → `store_decisions` D (moves jobs between buckets with an "AI:" reason; undoable).

### W4 `score_job` (feature 002, optional, on demand)
`load_facts` D (runs `extract_job_facts` from W3b first if the job has no AI facts yet) → `fit_score` L fast (dimension scores + evidence citing job facts and profile facts) → `apply_caps` D (pure domain rules, e.g. location/pay caps from the user's settings) → `store_score` D.

### W5 `outreach_draft` (feature 004)
Trigger: user picks a job/application and a draft type (referral request, LinkedIn note, HR email, follow-up).

| # | Node | Type | Notes |
|---|---|---|---|
| 1 | `select_facts` | D | relevant profile facts (by overlap with job facts), recipient details entered by the user, style guide |
| 2 | `draft_message` | L strong | → `Draft` (optional subject, body, `cited_fact_ids[]`); length limits per type (LinkedIn note 200/300 chars by account type) |
| 3 | `check_draft` | D | truthfulness + safety + length; repair/fallback |
| 4 | `review_draft` | ⏸ | user edits/approves; the app offers copy buttons and **never sends** |
| 5 | `save_draft` | D | stored with versions; the user can mark it "sent" manually for tracking |

### W6 `tailor_resume` (feature 005)

| # | Node | Type | Notes |
|---|---|---|---|
| 1 | `select_material` | D | confirmed profile + job facts → candidate bullets/skills ranked by overlap |
| 2 | `tailor` | L strong | → `TailoredResume` (summary rewrite; chosen/reordered/rephrased bullets, each with `source_bullet_id`; skills order) |
| 3 | `check_preservation` | D | every number, employer, date, title and skill traces to a source bullet/fact; no new facts |
| 4 | `review_resume` | ⏸ | full-document preview with inline edits |
| 5 | `render` | D | one resume document model → PDF (HTML template + WeasyPrint) and DOCX (python-docx); ATS-friendly single column |
| 6 | `save_version` | D | stored and linked to the application |

### W9 `content_suggestions` (feature 005, optional, on button press)
Trigger: the user asks for suggestions on the **base profile** (general) or on a **tailored resume** (job-aware). The cost estimate is shown first. Never runs automatically.

| # | Node | Type | Notes |
|---|---|---|---|
| 1 | `build_review_context` | D | resume content (profile or tailored version) + job facts if job-aware |
| 2 | `suggest_improvements` | L strong | → `Suggestion[]`: target (bullet/summary/skill/section order), kind (`rewrite`, `reorder`, `add_keyword`, `clarify_impact`, `remove_weak`, `ask_user`), proposed text, reason (e.g. "JD asks for Kafka; you list it but no bullet shows it") |
| 3 | `check_suggestions` | D | the truthfulness check applies to every proposed text; anything that would need a new fact is converted into an `ask_user` question ("What was the latency improvement here?") instead of a claim |
| 4 | `review_suggestions` | ⏸ | the user accepts / edits / rejects each one; answers `ask_user` questions |
| 5 | `apply_accepted` | D | accepted changes → new profile version (base) or new tailored version (job-aware); user answers become confirmed profile facts |

Same single template; suggestions change content, never layout.

### W7 `interview_review` (feature 006, R2, sketch)
`split_transcript` L fast (quarantined: pasted notes → Q&A pairs) → ⏸ confirm split → on button press per answer: `review_answer` L strong (cites profile facts) → `weak_topics` D (aggregation) → `prep_plan` L fast.

### W8 `company_discovery` (feature 002, user-added companies)
`discover_board` S (career-ops `discover-ats.mjs`) → ⏸ user confirms the matched board (or none → careers-page fallback) → `save_company` D.

## 8. Data ownership (overview)

Exact schemas are designed per feature. Ownership by area:

| Area | Main tables (indicative) | Owner feature |
|---|---|---|
| Setup | `settings` (budget cap, tier → model mapping; **no API keys**, those live in `.env`) | 001 |
| Profile | `resume_files`, `profiles`, `profile_versions` (each linked to its source resume file), `preferences`, `style_guides` | 001 (style guide: 004) |
| Runtime | `workflow_runs`, `llm_calls`, `events`, plus Procrastinate's own queue tables | 001 (foundation) |
| Search | `companies` (built-in seed + user), `sources`, `search_rules`, `source_runs`, `jobs`, `job_sources`, `job_facts`, `filter_decisions` (rule and AI), `job_scores` | 002 |
| Applications | `applications`, `application_events`, `contacts` (entered by the user), `offers` | 003 |
| Outreach | `drafts`, `draft_versions` | 004 |
| Resumes | `tailored_resumes` | 005 |
| Interviews | `interview_sessions`, `qa_items`, `answer_reviews` | 006 |

Cross-cutting rules: UUID primary keys; `created_at`/`updated_at`; AI-produced rows carry prompt version and model; user data can be deleted per item and entirely (constitution VIII).

**Companies table.** `app.companies` is the runtime source of truth for the company list: name, city, website, careers URL, ATS vendor + board id, resolution status (`verified` / `user_confirmed` / `unresolved` / `check_manually`), origin (`built_in` / `user`), `user_modified`, `hidden`, `seed_version`, last checked. The repo ships the maintainer-verified list as seed data (`backend/seed/companies.yaml`, company columns only, never contacts). A seed loader inserts it on install and, on later releases, **upserts by a stable key** without touching rows the user modified or deleted. Users add, edit, hide and delete companies in the app; **CSV import/export** lets the list be maintained in a spreadsheet and loaded back (import = preview + confirm, same upsert rules).

**Files**: `FileStoragePort` → local volume `data/files/<sha256[:2]>/<sha256>`; content-addressed, deduplicated, deleted when no row references them.

**Export all my data** (feature 003, small item): one click produces a zip with the profile versions, preferences, search rules, companies (CSV), jobs, applications, drafts, tailored resumes and the original files, plus a JSON manifest. It's for backups and moving to a new machine. A matching import is not planned for R1.

**Backups and deletion**: all user data lives in the Postgres volume and the data folder; backing up both is a full backup. "Delete all my data" wipes both.

## 9. Security and privacy

- **Local only** (Ravi, 2026-11-03: "we are not gonna host it anywhere. anyone wanna use should pull the repo and run locally"). `api` binds to `127.0.0.1` and there is no login. There's no hosted version and no network-exposure setting in R1; docker compose publishes ports on `127.0.0.1` only.
- **API keys live only in `.env`** (`OPENAI_API_KEY`), never in the database (ADR-09). The setup wizard checks that the key is set and makes a test call; if it's missing or rejected, it explains how to set it and restart. The key is never logged and never sent to the browser; Settings shows only its status ("found, working" / "missing" / "rejected").
- No telemetry. Logs are structured JSON with secrets and resume text redacted.
- Careers-page fetching: honest User-Agent (`HireTitan/<version> (+repo URL)`), robots.txt, per-host rate limit, cache, timeouts, size caps. HTML is parsed, never executed.
- Uploads: type sniffing (not just the extension), size limit, parsed in the worker.
- SPA: strict Content Security Policy; model output is rendered as text, never as HTML.

## 10. Frontend

React (current stable; exact version pinned in the 001 plan) + Vite + TypeScript strict. React Router; **TanStack Query** for server state; **Tailwind + shadcn/ui** components; react-hook-form + zod for forms; a TypeScript API client generated from FastAPI's OpenAPI schema (`openapi-typescript`), so types match the backend; EventSource for SSE. Tests: Vitest + Testing Library; Playwright end-to-end for the main journeys.

**Theme: dark only in R1**, built from Ravi's palette. All colours are theme variables (Tailwind/shadcn CSS variables), so a light theme can be added later without touching components. Contrast meets WCAG AA (verified in implementation).

| Token | Colour | Use |
|---|---|---|
| `background` | `#06141b` | page |
| `surface` | `#11212d` | sidebar, cards, inputs, dialogs |
| `divider` / hover | `#253745` | dividers, hover, muted fills (decorative; text on it 7.9:1) |
| `slate` | `#4a5c6a` | gradient stops, glows and shadows only (2.7:1 on the page, never text or outlines) |
| `muted` / `muted-small` | `#9ba8ab` | hint and label text, icons, outlines (6.7:1 or better) |
| `accent` | `#4cc9f0` (ice cyan) | links, focus ring, highlights (8:1 or better on the page and cards) |
| `heading` | `#f4f6f5` | headings, brighter than body text for hierarchy (7:1 or better) |
| `primary` | `#4cc9f0` to `#1fa3d1` gradient | button, active-nav and progress fill, with `#06141b` text (6:1 or better) |
| `text` | `#ccd0cf` | body text (10.5:1 or better) |
| `logo` / `logoEnd` | `#e8fbff` to `#4cc9f0` gradient | the bolt logo (sidebar, setup header, tab icon) with a cyan glow: the brightest element on the page |
| `success` / `warning` / `danger` | `#3fb950` / `#d29922` / `#f85149` | status badges (kept from the earlier palette) |

Palette changed 2026-11-04 to Ravi's slate scale `#06141B #11212D #253745 #4A5C6A #9BA8AB #CCD0CF`. The slate scale has no saturated colour, so on 2026-11-05 one accent was added: ice cyan `#4cc9f0`. The page background is a top-to-bottom gradient (`#253745` to `#11212d` to `#06141b`, 2026-11-05). Gradients (panels, primary actions, the bolt) and shadows (panels, primary actions, dialogs) are CSS variables in `theme.css`.

**First-run setup (001, US5):** until setup is finished, every page shows one centred card instead of the app: (1) name, (2) resume (upload, paste or "Type it in myself"), (3) check the profile, (4) preferences, ending in "Finish setup". The card comes from saved data (`GET /onboarding`), so closing the tab returns the user to the same card; a stored `setup_completed_at` keeps the cards from coming back, and "Delete all my data" clears it. Design: `docs/superpowers/specs/2026-11-04-first-run-onboarding-design.md`.

**First-level UI (001), after setup:** a sidebar shell with **Home** (setup checklist: key found and working, resume uploaded, profile confirmed, preferences set) · **Profile** (upload, extraction progress, review/edit/confirm, hidden-text and injection flags) · **Preferences** (form) · **Review** (items waiting for approval) · **Settings** (budget cap, key status, tier → model mapping, usage and spend).

Later screens, each added by its feature: Search rules · Companies · Jobs (match / maybe / hidden with reasons, job detail) · Applications · Drafts · Tailored resumes · Export.

## 11. Testing strategy (constitution V)

| Level | What | Tools |
|---|---|---|
| Unit | domain rules, state machines, validators, truthfulness checker, dedup, sanitizer | pytest |
| Integration | repositories, migrations, task queue (SKIP LOCKED, leases), checkpointer | pytest + **Testcontainers PostgreSQL 16** |
| Contract | each source adapter and LLM adapter against recorded fixtures | pytest + respx / recorded JSON |
| Workflow | each graph end to end with a **fake LLM** (scripted outputs, including invalid ones to exercise repair/fallback) and interrupt/resume | pytest + LangGraph |
| API | routers via `httpx.AsyncClient` against real Postgres | pytest |
| Architecture | import-linter contracts (module and layer rules), the no-send test, the career-ops request allowlist | import-linter + pytest |
| Security | the attack test set (§6): injected job posts, hidden-text PDFs, fake system messages in emails, link-exfiltration attempts | pytest (every build) |
| Frontend | components and hooks; e2e journeys against a seeded backend with the fake LLM | Vitest, Playwright |
| Evals | prompt quality against real providers; run manually and in PRs that change prompts | `evals/` runner |

Test names reference requirement/scenario IDs. Coverage gates: ≥ 90% domain + application, ≥ 80% overall. Normal test runs never call OpenAI; only evals do (small, on demand, counted against the budget cap). All test data is synthetic.

## 12. Architecture decisions (ADRs)

Each ADR: decision · why · alternatives. **Approved by Ravi 2026-11-03.**

**ADR-01 Modular monolith, two processes, organised by feature.** One codebase, `api` + `worker`, one Postgres. Code is packaged by feature module with layers inside each, plus a shared `platform/` (§3). *Why:* the simplest design that keeps LLM calls and fetches out of request handlers, with an easy `docker compose up`. *Alt:* microservices (overkill for one user); a single process (long runs would block or die with HTTP requests).

**ADR-02 Own thin LLM adapters, not LiteLLM.** Four adapters behind `LlmPort` using the official SDKs (`openai`, `anthropic`, `google-genai`). *Why:* we need provider-specific structured output, refusal handling and accurate usage/cost data, and our validation, budget and logging layer sits on top anyway. Four adapters are small and well-testable, bring fewer heavy transitive dependencies, and show real design work. *Alt:* LiteLLM (100+ providers for free, but a large dependency whose structured-output behaviour varies by provider; our layer would wrap it anyway). Revisit if users ask for many more native providers; the OpenAI-compatible adapter already covers most. **Decided (Ravi, 2026-11-03): OpenAI first.** Feature 001 builds only the OpenAI adapter, and development and evals use Ravi's OpenAI key. The Anthropic, Gemini and OpenAI-compatible adapters are separate tasks that must land before the first public release (constitution IV unchanged). The port, fake LLM and contract tests are provider-neutral from day one.

**ADR-03 Postgres as the task queue, via Procrastinate.** [Procrastinate](https://github.com/procrastinate-org/procrastinate) (MIT; version and licence confirmed in the 001 plan before pinning) uses `SELECT … FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`, with retries, periodic tasks, queueing locks and asyncio support. *Why:* no extra service (Redis/RabbitMQ), tasks are created in the same transaction as their data, plenty for one user, and a proven implementation instead of our own leases and retries. Our `workflow_runs` table and the LangGraph checkpointer stay ours; Procrastinate only moves tasks. *Alt:* our own `tasks` table (about 200 lines, but we'd own every edge case); Celery/RQ + Redis (another container to run).

**ADR-04 LangGraph with the Postgres checkpointer.** `langgraph-checkpoint-postgres` in schema `lg` of the same database; `thread_id` = `workflow_runs.id`; human approval via `interrupt()` / `Command(resume=…)`. *Why:* durable pause/resume for approvals and crash recovery, without writing our own state machine for every workflow. *Alt:* plain async functions + our own state tables (one less dependency, but we would rebuild interrupts and checkpointing).

**ADR-05 career-ops as a pinned subprocess.** Node 22 + career-ops v1.38.0 baked into the backend image with `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. The scanner uses plain HTTP (checked: `scan.mjs` doesn't import Playwright); browser-based scripts aren't used. HireTitan owns a separate career-ops data folder, generates its `portals.yml` from the company list and approved queries, and reads `scan.mjs --json` output through `CareerOpsPort`. Each enabled provider has a request allowlist with a recorded-response contract test, and a robots.txt check before it's enabled (§3). *Why:* reuses mature ATS providers (Greenhouse, Lever, Ashby, Workday, …) instead of rewriting them; a pinned version keeps contract tests stable. *Alt:* port the providers to Python (lots of work, loses upstream fixes); call the user's own career-ops install (breaks "anyone can clone it").

**ADR-06 Resume parsing: pypdf / pdfplumber + python-docx.** Permissive licences, pure Python. PyMuPDF is excluded: it's AGPL, which conflicts with shipping under MIT. Scanned (image-only) PDFs get no OCR in R1; the user is told and can paste the text or edit the profile by hand. pdfplumber's per-character colour and size data is used for hidden-text detection (§6).

**ADR-07 Resume rendering: one document model → WeasyPrint (PDF) and python-docx (DOCX).** An HTML/CSS template (Jinja2) for the PDF, so the browser preview matches the PDF; the DOCX is built from the same model. **Exactly one ATS-friendly single-column template** (decided by Ravi); improvement happens through content (W6 tailoring, W9 suggestions), not layout. *Alt:* career-ops `generate-pdf.mjs` (needs Playwright + Chromium in the image, about 300 MB); LaTeX (heavy, poor DOCX story).

**ADR-08 Realtime via SSE over LISTEN/NOTIFY.** One-way server → browser updates (run progress, "needs review"). *Alt:* WebSockets (two-way isn't needed); polling (kept as a fallback only).

**ADR-09 API keys in `.env` only.** `OPENAI_API_KEY` (and later the other providers' keys) are read from the environment; nothing is stored in the database, so no encryption layer is needed. *Why:* simplest and standard for self-hosted, local-only apps; updating an expired key is "edit `.env`, restart". An invalid key pauses AI tasks with a banner instead of failing them (§4). *Alt:* encrypted keys in the database, set from the dashboard (no restart, but more code); decided against by Ravi.

**ADR-10 Frontend stack.** Current stable React + Vite + TS, TanStack Query, React Router, Tailwind + shadcn/ui, generated OpenAPI client; dark theme from Ravi's palette (§10). *Why:* common, well documented, fast to build, typed end to end.

**ADR-11 Default models per provider (OpenAI decided 2026-11-05).** Profile extraction uses the `fast` tier (`gpt-5.4-mini`). Eval on 15 synthetic English documents (11 resumes and 4 that are not; `backend/evals/reports/extract_profile-2026-11-05.md`, prompt v2): `fast` (`gpt-5.4-mini`) precision 100%, recall 100%, $0.0019 per document, p95 3.2 s, all 4 non-resumes rejected and no resume rejected by mistake; `strong` (`gpt-6-astra`) the same scores at $0.0193 per document, p95 6.4 s. An earlier run on prompt v1 (11 resumes) gave `fast` 97.9% recall (3 skills missed in a table layout) and `strong` 100%, so run-to-run variation is real. Both pass SC-003 and SC-007; `strong` costs about 10 to 16 times more for no measured gain. Other providers get their defaults from the same eval when their adapters are added. Rule: change the default only with a newer report that supports it (`test_defaults_match_latest_eval_report`). HireTitan is English-only, so the eval set is English. How to run and read an eval: `docs/how-we-choose-a-model.md`.

**ADR-12 Relevance judging in the default search (decided 2026-11-06, feature 002).** The default search judges relevance with the `fast` model after the rules, instead of leaving AI to an on-demand step. Reason: the person wants only relevant jobs in the list. Eval of prompt `judge_relevance` v1 on 60 labelled postings, `gpt-5.4-mini`: precision 98.3%, recall 94.3%, no unusable answers, no injection-affected decisions, $0.00024 per job (`backend/evals/reports/`). To keep cost and waiting visible, W3 runs in batches with live cost and a Stop button instead of an upfront estimate (deviation D3, approved). Job text is untrusted input: it goes to the model inside quarantined blocks and the answer is validated. Without a key, in rules-only mode or after an unusable answer, jobs stay in Explore as "not checked by AI".

## 13. Open questions for Ravi

1. ~~ADR-02~~ decided: own adapters, OpenAI first; the other providers before the public release.
2. ~~ADR-07 templates~~ decided: one template; optional content suggestions (W9).
3. ~~Network exposure~~ decided: local only, no hosting, no login.
4. ~~Workflow catalogue~~ approved; W2 became "search rules".
6. ~~Queue~~ decided: Procrastinate. ~~Key storage~~ decided: `.env` only. ~~Theme~~ decided: dark, Ravi's palette. ~~Export~~ decided: "Export all my data" in feature 003.

No open questions remain.
5. ~~Company list storage~~ decided: Postgres `companies` table seeded from the repo, editable in the app, CSV import/export (§8).
