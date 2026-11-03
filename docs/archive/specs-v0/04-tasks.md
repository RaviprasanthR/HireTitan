# 04 — Implementation tasks (TDD)

Status: **DRAFT — awaiting review** · Date: 2026-11-03

Rules for every task:

1. **Red** — write the listed tests first from the acceptance criteria; run them; they must fail for the right reason.
2. **Green** — write the minimum code to pass.
3. **Refactor** — clean up with tests green; ruff + mypy `--strict` clean.
4. **Done** = tests green, coverage gate met, requirement IDs ticked in the traceability table, one commit per task (`T3.2: …`).

Tasks are ordered so each one builds only on finished ones. Estimates assume part-time work.

**Start condition:** all 🔴 blocking decisions in `05-open-decisions.md` answered and the specs marked APPROVED. Each task's "Needed by" decisions (see the index in `05-open-decisions.md`) must be answered before that task begins.

---

## Phase 0 — Project skeleton (≈1 day)

| ID | Task | Tests first | Done when |
|---|---|---|---|
| T0.1 | Remove pre-spec scaffolding written on 2026-11-03 (untested); create `backend/` (uv, src layout), `web/` (Vite React TS), `docker-compose.yml` (postgres 16 + pg_trgm), Makefile (`test`, `lint`, `eval`, `up`). | `test_smoke_imports` (package imports) | `make test` and `make lint` run green on an empty project. |
| T0.2 | CI workflow: ruff, mypy strict, import-linter contract (domain ↛ adapters/frameworks), pytest with coverage gates, web typecheck/lint/test, licence report for dependencies (N12). | import-linter contract file | CI green on PR. |
| T0.3 | Settings (`pydantic-settings`), fail-fast validation. | `test_settings_rejects_missing_database_url`, `test_settings_requires_api_token_when_not_localhost` (N6) | — |

## Phase 1 — Domain core (pure, ≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T1.1 | `UrlKey` value object. | property tests (hypothesis): idempotent (`key(key(u)) == key(u)`), tracking params ignored, fragment ignored, `www.`/case ignored; table tests for real Greenhouse/Lever/Naukri URLs. | R1.4 |
| T1.2 | Job status state machine. | every allowed transition passes; every other pair raises `InvalidTransition`; `filtered_out` requires reason. | §3.2 |
| T1.3 | `Application` aggregate + transition table + events. | parametrized allowed/forbidden matrix; `applied` sets `applied_at`, emits `ApplicationApplied`; leaving `applied` emits `ApplicationLeftApplied`; terminal states immutable. | R5.1, R5.2 |
| T1.4 | Draft state machine + revision rule. | regenerate → old `superseded`, new revision = n+1; `sent` only from `approved`. | R4.5–R4.7 |
| T1.5 | `prefilter`, `location_fit`, `comp_fit`. | remote/preferred city pass; conditional city conditional; low-priority city allowed; blocked city blocked; multi-city "preferred; blocked" passes; title keyword rules; blocked company. | R2.1, R2.5 |
| T1.6 | `combine_score` rule caps. | comp ceiling < floor → ≤ 2.5; caps recorded; no cap when facts unknown. | R2.5 |
| T1.7 | `followup_schedule`. | +7/+14 days from applied_at; configurable; timezone-safe. | R5.3 |
| T1.8 | `CvFact` parser for `cv.md`. | parses the real `cv.md` fixture into stable IDs (`exp.punch.1` …), skills list, numbers extracted (40%, 99.9%, 100 ms); stable IDs across re-parse. | R8.2 |

## Phase 2 — Application layer with fakes (≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T2.1 | Ports (Protocols) + in-memory fakes: repos, UoW, `FakeClock`, `FakeSource`, `FakeLlm`, `FakeTaskQueue`. | fakes pass the same contract test suite later reused for real adapters. | N10 |
| T2.2 | `IngestService`. | new jobs created + sightings; duplicates across sources → one job, two sightings; source failure → run `failed`, earlier jobs kept; second concurrent run → `RunAlreadyActive`; pipeline task enqueued once per new job (dedupe key). | R1.4–R1.7, N3 |
| T2.3 | `ApplicationService` (create, transition with `expected_version`, follow-up schedule/cancel via events). | stale version → `StaleVersion`; applied → 2 follow-ups; rejected → follow-ups cancelled. | R5.x |
| T2.4 | `DraftService` (approve with edit → re-validate; regenerate; reject; mark sent). | edited body failing V6 is rejected; mark-sent only after approve; system never sets `sent_at` on its own. | R4.5–R4.7, N1 |
| T2.5 | `ProfileService` reading career-ops files (read-only), computing `profile_hash`. | never opens files for write (spy); hash changes when cv.md changes. | R8.1, R2.8 |

## Phase 3 — Persistence (≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T3.1 | Alembic migration for schema §5 (+ pg_trgm). | testcontainers: upgrade/downgrade round-trip; CHECK constraints reject bad rows (score 5.5, linkedin note 301 chars, two running runs per source). | §5 |
| T3.2 | SQLAlchemy repositories + UoW; reuse T2.1 contract suite. | contract suite green against Postgres. | — |
| T3.3 | Postgres task queue (enqueue in UoW, claim with SKIP LOCKED, retry/backoff, dead letter). | two concurrent workers never claim the same task; failed task retried with backoff; `max_attempts` → `dead`; dedupe key no-op. | N2, N3 |
| T3.4 | Jobs list query via Specification (filters, trigram search, cursor pagination). | each filter; pagination stable under inserts; 10k-row perf test p95 < 300 ms (N4, marked `slow`). | R6.1, N4 |

## Phase 4 — Source adapters (≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T4.1 | `CareerOpsSource`. | contract: real `scan-history.tsv` fixture parsed (only `added` rows, since-last-run filter); JSON receipt parsing; non-zero exit + receipt → partial; missing `scan.mjs` → clear error; env `CAREER_OPS_ROOT` passed, cwd = install (subprocess mocked). One opt-in live test against the real install. | R1.1, R1.5 |
| T4.2 | `GoogleSheetSource`. | CSV fixtures: aliases ("Job Link", "Role"), company-only rows, empty sheet, HTML response → `SheetNotShared` error. | R1.2, R1.8 |
| T4.3 | `ManualSource` + `POST /jobs` path. | invalid URL 422; duplicate URL returns existing job (200, not 201). | R1.3 |
| T4.4 | `JdFetcher` chain (career-ops `fetch-jd.mjs` → http → `jd_needed`). | blocked domains never fetched; exit 1 → next strategy; HTML → text extraction. | R2.2 |

## Phase 5 — LLM infrastructure (≈3 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T5.1 | `PromptRegistry` (front-matter parse, sha256, register, immutability check, one active per name). | edited registered file → startup error; new file → `candidate`; missing placeholder → `StrictUndefined` error; `untrusted()` escapes closing tags. | R7.1 |
| T5.2 | `AnthropicLlmAdapter` (`messages.parse`, `messages.stream`, refusal fallback param, usage → cost, served model). | respx-recorded responses: ok, `max_tokens`, refusal, refusal-rescued-by-fallback, 429→retry→ok, 500 exhausted. | R7.4, R7.5 |
| T5.3 | Decorators: budget guard, circuit breaker. | over budget → `BudgetExceeded`, no API call; 5 failures → open; half-open probe. | R7.6, R7.5 |
| T5.4 | Validator chain V1–V8. | one test per issue code with minimal failing/passing samples; numbers-in-body grounding; URL allowlist; contact source URL must be in search results. | R7.2, R4.3 |
| T5.5 | `LlmTask` template method. | FakeLlm scripted: ok → result; invalid → repair → ok; invalid twice → fallback; refusal → fallback without retry; every attempt writes an `llm_calls` row. | R7.2, R7.5 |
| T5.6 | `screen_untrusted` sanitizer + injection signal patterns. | corpus fixtures: zero-width/bidi stripped, NFKC, length cap, each pattern detected; clean JDs produce no signals (false-positive check). | R7.3 |

## Phase 6 — Agent nodes and workflows (≈4 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T6.1 | Prompt files P1–P6 v1 + Pydantic schemas. | schema unit tests (bounds, enums, `extra=forbid`); render snapshot tests per prompt (golden rendered text). | R7.1 |
| T6.2 | `ExtractFactsTask` + rule-based fallback extractor. | fallback extracts years/location/work mode from fixtures; degraded flag set. | R2.3 |
| T6.3 | `FitScoreTask` (never receives raw JD — enforced by input type) + caps. | input DTO has no jd field (type test); caps applied; degraded rules-only score. | R2.4, R2.5, ADR-4 |
| T6.4 | `FindContactsTask` (web search tool, parse final text). | recorded response with search results → suggestions; invented source URL dropped (V8); empty → ok. | R3.1, R3.2 |
| T6.5 | `DraftTasks` (LinkedIn, HR email, follow-up) + template fallbacks + streaming relay (LISTEN/NOTIFY). | grounding failures → repair → template; char limit; stream chunks published in order. | R4.1–R4.4, R5.4 |
| T6.6 | `job_pipeline` graph. | FakeLlm end-to-end: filtered path; jd_needed interrupt → paste → resume; review interrupt → dismiss ends; shortlist → contacts → drafts → approval interrupt; node idempotency (re-run doesn't re-call LLM); **kill-and-resume** from Postgres checkpoint. | R2.x, N2 |
| T6.7 | `followup` graph + scheduler task `check_followups`. | due + still applied → draft pending; status changed → no draft; runs twice → one draft. | R5.4, R5.5 |
| T6.8 | Worker process (dispatcher loop, graceful shutdown, scheduler). | handler routing; SIGTERM finishes current task; scheduled ingest enqueued once per interval. | N2 |

## Phase 7 — API (≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T7.1 | App factory, problem-details errors, auth token middleware, health/ready. | 409/422/503 shapes; token required when bound publicly. | N6, N8 |
| T7.2 | Jobs, review queue, decision, rescore endpoints. | decision resumes graph (FakeLlm); If-Match mismatch → 409. | R2.6, R2.8, R6.1–2 |
| T7.3 | Ingest, contacts, drafts (+ SSE stream), applications, follow-ups, insights. | SSE emits chunks then `validated` event; insights funnel numbers from seeded data. | R1, R3–R6 |
| T7.4 | OpenAPI export + generated TS types committed; CI fails on drift. | contract diff test. | — |

## Phase 8 — Frontend (≈4 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T8.1 | App shell, routing, API client, TanStack Query setup, problem-details error toasts. | client maps 409 to `ConflictError`. | — |
| T8.2 | Jobs page (filters, search, pagination). | RTL + MSW: filters change query params; empty state. | R6.1 |
| T8.3 | Review queue (score, verdict, skills, gaps, injection badge, shortlist/dismiss/rescore). | actions call API, optimistic removal, rollback on error. | R6.2 |
| T8.4 | Applications Kanban (dnd-kit, valid transitions only, optimistic with 409 rollback). | invalid drop disabled; conflict restores card. | R6.3 |
| T8.5 | Drafts (SSE streaming view, edit, approve, regenerate, reject, copy, mark sent, contact verified badge). | stream renders incrementally (mock EventSource); copy uses clipboard API. | R6.4, R3.4 |
| T8.6 | Follow-ups, Sources, Insights pages. | due/overdue grouping; ingest 409 shows "already running". | R6.5–R6.7 |
| T8.7 | Playwright e2e: 3 flows (design §12). | — | — |

## Phase 9 — Evals, observability, hardening (≈3 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T9.1 | Label the eval sets (40 JDs with my scores, 15 draft cases, 12 injection twins) — **needs my input**. | dataset schema validation. | R7.7 |
| T9.2 | Eval runner + `make eval` + activation CLI with thresholds; spend cap per run. | runner unit tests with FakeLlm; threshold gate logic. | R7.7 |
| T9.3 | Measure real cost/latency per node; verify prompt caching hits; tune effort. | — (report in `docs/evals/`) | N5 |
| T9.4 | OpenTelemetry + structlog wiring; Jaeger compose profile. | span-per-node test with in-memory exporter. | N8 |
| T9.5 | Security tests: architecture guard (no outbound senders), injection corpus suite, dependency audit (`pip-audit`, `npm audit`). | — | N1, R7.3 |

## Phase 11 — Resume versions (≈3 days; part of MVP)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T11.1 | Domain: `ResumeVersion`; `Application` resume rule (applied requires resume or `not_recorded`); resume-change audit event. | applied without resume → error; `not_recorded` allowed; change emits audit event. | R9.4 |
| T11.2 | `FileStorage` port + local content-addressed adapter. | same bytes → same key, stored once; read-back equals input; path traversal impossible (keys are hashes only). | R9.2, ADR-9 |
| T11.3 | Text extraction (pypdf, python-docx) + size/type validation. | fixtures: my real resume PDF → contains "ClickHouse"; DOCX fixture; >10 MB or `.exe` rejected; scanned/empty-text PDF → warning, still stored. | R9.1, R9.3 |
| T11.4 | `ResumeService` (register, dedupe, import from career-ops `output/`, archive; delete blocked when used). | duplicate upload returns existing (200); import picks new PDFs only; delete-in-use → 409. | R9.1, R9.2, R9.7 |
| T11.5 | Migration §5.1 + repositories; `v_resume_outcomes`. | CHECK `applied_needs_resume`; outcome counts on seeded data. | R9.5 |
| T11.6 | Keyword coverage task via career-ops `keyword-match.mjs`. | subprocess mocked: parses output; stored per application; failure leaves application untouched. | R9.6 |
| T11.7 | API + UI: resume library page, resume picker in "mark applied" dialog, outcomes table. | picker required on applied (RTL); outcomes render. | R6.9, R9.4 |

## Phase 12 — Interview rounds and preparation analysis (≈6 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T12.1 | Domain: `InterviewRound` state machine, `Application.add_round` (→ `interview`), question entity, `weakness_score`. | round transitions; outcome only on completed; seq unique/increasing; first round moves app to interview; weakness formula table tests. | R10.1, R10.2, R10.6, R5.1 |
| T12.2 | Migration §5.2–5.3 + repositories; seed topic taxonomy (from Q9). | constraints (outcome without completed rejected); `v_topic_performance` and `v_latest_review` on seeded data incl. user override winning. | R10.4–R10.6 |
| T12.3 | Rounds + Q&A use cases and API (CRUD, delete round/application data). | delete cascades questions/reviews/tags; interviewer data gone. | R10.1, R10.2, R10.10 |
| T12.4 | `SplitTranscriptTask` (P7) + V10 + confirm interrupt. | invented question rejected; empty answers kept empty; confirm step edits persist. | R10.3 |
| T12.5 | `ReviewAnswerTask` (P8) + V9 + fallback; `interview_review` graph with Send fan-out; topic tagging incl. model-suggested topics (`approved=false`). | FakeLlm: status/overall consistency enforced; cited fact must exist; fan-out reviews all questions; re-review keeps history; override wins in views. | R10.4, R10.5 |
| T12.6 | Recurring-question detection (pg_trgm + topic overlap) and answer evolution. | seeded near-duplicates across companies grouped; unrelated questions not grouped; threshold tuned on real data → report. | R10.7, ADR-11 |
| T12.7 | `InterviewInsightsService` (weakness table, monthly trend, failed-round topics). | numbers match hand-computed fixtures exactly. | R10.6 |
| T12.8 | `PrepPlanTask` (P9) + V11 + deterministic fallback; general and application scope. | "why" numbers must equal snapshot; unknown topic rejected; fallback ranks by `weakness_score`. | R10.8 |
| T12.9 | career-ops session interop: export round → `interview-prep/sessions/*.md` (schema-exact, front-matter + speaker labels + competency tags); import existing files. | round-trip export→import is lossless for Q&A and tags; written only on explicit export; never overwrites an existing file; `weekly-digest.mjs --json` parses our exported file (opt-in live test). | R10.9, R8.1 |
| T12.10 | UI: application detail (rounds timeline, Q&A editor with self-rating, paste-notes flow, review panel with override), Interview insights page (heatmap, trend, recurring questions, prep plan). | RTL + MSW for each; heatmap renders from fixture; override updates status badge. | R6.8, R6.10 |
| T12.11 | Evals for P7–P9 (needs my labelled data, see 03-prompts eval table). | dataset schema validation. | R7.7 |

## Phase 10 — Gmail job alerts (optional, ≈2 days)

| ID | Task | Tests first | Req |
|---|---|---|---|
| T10.1 | Gmail OAuth (readonly) + `GmailAlertSource` with per-sender parsers (Naukri, Cutshort, LinkedIn, Instahyre). | contract tests on saved sample emails; unknown sender ignored. | R1.9 |

---

## Traceability matrix

| Req | Tasks |
|---|---|
| R1.1–R1.8 | T2.2, T4.1–T4.3, T7.3 |
| R1.9 | T10.1 |
| R2.1–R2.8 | T1.5, T1.6, T4.4, T6.2, T6.3, T6.6, T7.2 |
| R3.1–R3.4 | T6.4, T7.3, T8.5 |
| R4.1–R4.7 | T1.4, T2.4, T5.4, T6.5, T8.5 |
| R5.1–R5.6 | T1.3, T1.7, T2.3, T6.7, T8.4 |
| R6.1–R6.7 | T3.4, T7.2, T7.3, T8.2–T8.6 |
| R7.1–R7.7 | T5.1–T5.6, T6.1, T9.2 |
| R6.8–R6.10 | T11.7, T12.10 |
| R8.1–R8.2 | T1.8, T2.5, T12.9 |
| R9.1–R9.7 | T11.1–T11.7 |
| R10.1–R10.10 | T12.1–T12.11 |
| N1 | T2.4, T9.5 · N2 T3.3, T6.6, T6.8 · N3 T2.2, T3.3 · N4 T3.4 · N5 T9.3 · N6 T0.3, T7.1 · N7 T12.3 · N8 T7.1, T9.4 · N9 T0.2 · N10 T0.2, T2.1 · N11 T0.1 · N12 design §17, T0.2 (licence report) |

**Total ≈ 36 working days part-time.** MVP cut (usable for my own search): Phases 0–7, T8.1–T8.5, Phase 11, and T12.1–T12.3 + T12.10 (manual round/Q&A tracking without AI review) ≈ 24 days. AI answer review and prep plans (rest of Phase 12) follow right after.

Suggested build order after MVP: Phase 12 (rest) → Phase 9 → Phase 10.
