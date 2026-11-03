# HireTitan Constitution

## Core Principles

### I. Human in the Loop, No Outbound Actions

- HireTitan MUST NOT send messages, emails, connection requests or job applications, and MUST NOT
  contain any adapter capable of doing so. An automated architecture test MUST enforce this.
- Every AI output that affects what the user sends or searches (drafts, tailored resumes,
  search queries, profile extraction, relevance filtering) MUST be shown to the user and be
  approvable, editable or reversible before it takes effect.
- AI decisions that hide or drop data (e.g. relevance filtering) MUST record a visible reason and
  MUST be undoable.

Rationale: the user stays accountable for everything sent in their name; the worst a model error
or injection can do is produce a draft a human rejects.

### II. Truthful Profile

- The user's confirmed profile (extracted from their resume, then edited by them) is the ONLY
  source of facts about the candidate.
- AI MUST NOT invent experience, employers, dates, numbers, metrics or skills. Drafts, tailored
  resumes and answer reviews MUST cite the profile facts they use, and the system MUST
  automatically reject outputs whose numbers or claimed skills do not appear in the cited facts.
- Tailoring MAY reorder, select and rephrase; it MUST preserve every fact and number exactly.

Rationale: a single fabricated claim can cost the user a job offer and their credibility.

### III. Untrusted Input Is Data

- All external text (job descriptions, careers pages, emails, search results, imported files)
  MUST be treated as untrusted data, never as instructions.
- Raw untrusted text MUST only reach AI steps without tools whose output is a strict, bounded
  schema; privileged steps (scoring, drafting, tailoring) MUST receive only structured,
  length-bounded data derived from it.
- Untrusted content MUST be sanitized (Unicode normalization, control characters stripped,
  length capped), delimited, and screened for injection signals; signals MUST be stored and shown.

Rationale: job postings and web pages are attacker-controllable input to an AI system.

### IV. Validated, Versioned, Provider-Agnostic AI

- Every LLM call MUST go through one provider-neutral LLM port. OpenAI, Anthropic and Google
  Gemini MUST be supported, plus any OpenAI-compatible endpoint; model choice is configuration.
- Every LLM output MUST be validated against a typed schema and then business rules; invalid
  output gets one repair attempt, then a defined fallback. A failed AI step MUST NOT crash a
  workflow or lose user data.
- Prompts MUST be versioned files; each AI artifact MUST record prompt version and model used.
  From version 2 onward, a prompt MUST pass its evaluation set before becoming active.
- Every LLM call MUST be logged (provider, model, tokens, cost, latency, outcome) and MUST be
  blocked when the user's budget cap is reached. Batch AI actions MUST show an estimated cost first.
- Features MUST degrade gracefully when a model lacks a capability (e.g. native structured output).

Rationale: users bring their own key and provider; reliability and cost must not depend on one vendor.

### V. Test-First (NON-NEGOTIABLE)

- TDD is mandatory: tests are written from the acceptance scenarios first, observed failing for
  the right reason, then the minimum code is written, then refactored (red → green → refactor).
- Test names MUST reference the requirement or acceptance-scenario ID they verify.
- Persistence, queries and queues MUST be tested against real PostgreSQL (containers). Fakes are
  allowed only for LLM providers, external job sources, external CLIs and the clock.
- Each external adapter MUST have contract tests against recorded fixtures.

Rationale: a showcase project is judged by its tests; real-database tests catch what fakes hide.

### VI. Lean Architecture

- Ports (interfaces) exist ONLY at real boundaries: LLM provider, job sources, file storage,
  clock, and external CLIs. FastAPI, SQLAlchemy and LangGraph are used directly elsewhere.
- The domain core (rules, state machines, scoring caps) MUST be pure code without framework
  imports, enforced by an import-linter contract.
- Any additional abstraction, service or project MUST be justified in the plan's Complexity
  Tracking table. Start simple; YAGNI.

Rationale: clean boundaries where they pay off, without pattern ceremony that slows delivery.

### VII. Permitted Sources Only

- Jobs MAY come only from: official or public APIs (including public ATS job-board APIs),
  aggregator APIs used with the user's own key within their terms, the user's own email inbox
  (read-only), companies' own public careers pages, and user-pasted content.
- Fetching careers pages MUST honour robots.txt, use conservative rate limits and caching, and
  identify the client honestly.
- HireTitan MUST NOT scrape, automate or use internal endpoints of sites whose terms forbid it
  (e.g. LinkedIn, Naukri, Indeed, Cutshort), and MUST NOT use paid scraped-data APIs.
- Sources MUST be optional and isolated: a failing source MUST NOT affect others or lose data
  already imported.

Rationale: an open-source tool must not get its users blocked or put them in breach of terms.

### VIII. Self-Hosted Privacy and Portability

- One user per install. All user data, files and API keys stay on the user's machine; no
  telemetry or third-party data sharing beyond the LLM provider and sources the user enables.
- Nothing specific to any person (locations, pay, roles, companies' contacts) may be hard-coded;
  all such values are user settings with documented defaults (global, India-friendly).
- The repository MUST NOT contain personal data; all fixtures and demo data are synthetic.
  Third-party personal data (recruiter names, contacts) MUST NOT ship with the product.
- Users MUST be able to delete their data completely (per item and entirely).
- `docker compose up` plus a first-run setup wizard MUST be enough to run HireTitan on Windows,
  macOS and Linux.

Rationale: anyone must be able to clone it and trust it with their career data.

## Technology Constraints

- Backend: Python 3.12+ managed with uv; FastAPI; SQLAlchemy 2 (async) + Alembic; PostgreSQL 16.
- AI orchestration: LangGraph (durable state, human-approval interrupts) with direct provider SDK
  calls inside nodes behind the LLM port.
- Frontend: React + Vite + TypeScript (strict). Web dashboard first; MCP/Claude Code access later.
- Job sources: career-ops (MIT) bundled at a pinned version in the Docker image, with HireTitan
  managing its own career-ops data folder; built-in company list shipped as versioned data.
- Outputs: ATS-friendly PDF and DOCX for tailored resumes.
- Secrets only from local configuration (setup wizard or environment); never in logs or prompts.
- API bound to localhost by default.

## Development Workflow and Quality Gates

- Spec-driven per feature with Spec Kit: specify → clarify → plan → tasks → analyze → implement.
  Specs are technology-agnostic (what/why); technology lives in plans.
- `/speckit-analyze` MUST report no critical issues before `/speckit-implement` starts.
- Each plan MUST pass the Constitution Check (principles I–VIII) before research and again after design.
- `master` is the main branch and MUST stay releasable. Each feature MUST be developed on its own
  branch cut from `master` (named after its spec folder, e.g. `001-setup-and-profile`) and merged
  back only through a GitHub pull request after all gates pass. No feature commits directly on `master`
  (the initial repository skeleton commit is the only exception).
- One commit per task. Every commit message MUST follow
  `[<branch> - <feature>] - If applied this commit will <change>`, enforced by the repository's
  `commit-msg` hook (`.githooks/`) and described in `CONTRIBUTING.md`.
- Gates on every pull request: ruff, mypy `--strict`, import-linter, pytest with coverage
  ≥ 90% on domain and application code and ≥ 80% overall, frontend typecheck/lint/tests,
  dependency licence and vulnerability checks.
- Each completed user story is reviewed (language/framework, security, and database reviewers
  as applicable) before the story is marked done.
- Prompt changes require their evaluation report in the pull request.

## Governance

- This constitution supersedes all other project documents and practices. Where a plan or
  task conflicts with it, the constitution wins until amended.
- Amendments are made by pull request containing the rationale, the impact on existing specs and
  plans, and a semantic version bump: MAJOR for removed or redefined principles, MINOR for new
  principles or materially expanded guidance, PATCH for clarifications.
- Every plan, task list and code review MUST verify compliance; deviations MUST be recorded and
  justified in the plan's Complexity Tracking table.
- Runtime development guidance lives in `CLAUDE.md` and `docs/CONTEXT.md`.

**Version**: 1.1.0 | **Ratified**: 2026-11-03 | **Last Amended**: 2026-11-03
