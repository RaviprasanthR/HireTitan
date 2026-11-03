# 05 — Open decisions and questions

Status: **OPEN — Ravi to answer** · Created: 2026-11-03

How to use this file: each item has context, options, a recommendation and an **Answer** line. Fill in the answer (or write "accept recommendation"). Once answered, the decision is copied into the relevant spec (requirements / design / tasks) and the item is marked ✅ here. Items marked **🔴 blocking** must be answered before implementation starts (task T0.1); the rest can be answered later, before the task that needs them.

Index

| ID | Topic | Blocking? | Needed by |
|---|---|---|---|
| D1 | Where resume files are stored | 🔴 | T11.2 / T0.1 (compose volumes) |
| D2 | Where resumes come from (source / import) | 🔴 | T11.4 |
| D3 | How a resume version is identified and named | | T11.1 |
| D4 | Resume file formats | | T11.3 |
| D5 | Relationship between `cv.md` and resume PDFs | 🔴 | T1.8, T11 |
| D6 | Where the app's data lives on disk + backups | 🔴 | T0.1 |
| D7 | Project location, name, repo visibility | 🔴 | T0.1 |
| D8 | Database: Postgres in Docker vs SQLite | 🔴 | T0.1 |
| D9 | Claude API key, monthly budget, daily cap | 🔴 | T5.2 |
| D10 | Model per node (Opus 5.5 everywhere vs cheaper for some) | | T6.1 |
| D11 | Google Sheet: layout and access method | | T4.2 |
| D12 | Sync applications to the career-ops tracker? | | T2.3 |
| D13 | LinkedIn note limit (free 200 / Premium 300) | | T6.5 |
| D14 | Gmail job-alert ingestion (phase 10) | | T10.1 |
| D15 | How interviews are captured (typed vs pasted notes) | | T12.4, T12.10 |
| D16 | Starting topic taxonomy | | T12.2 |
| D17 | career-ops dependency: path, version pinning, upgrades | 🔴 | T4.1 |
| D18 | Exporting interview rounds into career-ops automatically or on request | | T12.9 |
| D19 | Scheduling: how often to scan, follow-up days | | T6.8 |
| D20 | Notifications (none / desktop / email to self / Telegram) | | T6.8 |
| D21 | Authentication for the dashboard | | T7.1 |
| D22 | Deployment target (local only vs a small cloud VM later) | | T0.1 (keep compatible) |
| D23 | Approval UI: our own vs LangChain Agent Inbox | | T8.5 |
| D24 | Resume-Matcher integration | | after MVP |
| D25 | JobSpy / scraping-based sources | | — |
| D26 | Labelled evaluation data — who labels, how many | | T9.1, T12.11 |
| D27 | Observability backend | | T9.4 |
| D28 | Toolchain choices (uv, npm/pnpm, Python 3.12, Node 22, GitHub Actions) | 🔴 | T0.1 |
| D29 | Data retention and deletion | | T12.3 |
| D30 | Pending career-ops scanner fixes (from the first scan) | | before next scan |

---

## Resumes

### D1 — Where resume files are stored 🔴

Context: every resume version must be kept byte-for-byte as sent (R9.2), survive renames/moves of the original file, and never land in git (N7).

| Option | Pros | Cons |
|---|---|---|
| **A. App-managed local folder, content-addressed** (`<data dir>/resumes/<sha256>.pdf`, mounted into the containers) | Immutable by construction, dedup for free, simple, offline, private | Lives on one machine (needs backup, see D6) |
| B. Reference the original files where they are (career-ops `output/`, local folders) | No copy | Breaks when a file is moved, renamed or overwritten — loses the "exactly what I sent" guarantee |
| C. Google Drive folder via Drive API | Accessible from anywhere, Drive backs it up | OAuth setup, network dependency, more code; personal data in a third-party service |
| D. S3-compatible object storage (MinIO container now, AWS S3 later) | Production-like, cloud-ready, good resume talking point | Extra container and config for a single user |
| E. Postgres `bytea` | One place for everything, transactional | Bloats DB and backups; awkward to open files |

**Recommendation: A**, behind a `FileStorage` port so D (MinIO/S3) can be added later without touching domain code. The original path is stored as metadata only.

**Answer:** ______

### D2 — Where resumes come from 🔴

Context: today resumes exist as several PDF versions in local folders, and career-ops can generate tailored PDFs into its data folder's `output/`.

| Option | Notes |
|---|---|
| **A. Upload in the UI** | Always available. |
| **B. "Import from career-ops" button** — lists new PDFs in career-ops `output/` and registers the ones you pick | Links tailored CVs to the job they were made for when the filename/report number allows. |
| C. Auto-watch a folder (career-ops `output/` or a `resumes/inbox`) | Convenient but registers drafts you never sent; harder to test. |
| D. Google Drive folder sync | Only if D1 = C. |

**Recommendation: A + B**, plus a one-time import of the existing local PDFs as the first versions (you pick which). No auto-watching.

Sub-questions:
- Import which existing PDFs, and which one is the current "base" resume? **Answer:** ______
- Should career-ops `/career-ops pdf` stay the only way tailored resumes are made (recommended), or do you also edit resumes by hand in Word/Docs? **Answer:** ______

**Answer:** ______

### D3 — How a resume version is identified and named

| Option | Example |
|---|---|
| **A. Hash as identity + human label + auto sequence per family** | `Backend base · v4`, `Backend · tailored · Acme · v1` |
| B. Free-text label only | `backend_nov` |
| C. Semantic version numbers you set | `2.1.0` |

**Recommendation: A.** The SHA-256 is the true identity (dedup, immutability); the label and sequence are what you see. Families: `base`, `tailored` (per job), `manual`.

**Answer:** ______

### D4 — Resume file formats

| Option | Notes |
|---|---|
| **A. PDF only (v1)** | What you actually send; text extraction with `pypdf`. |
| B. PDF + DOCX | Some portals want Word files; needs `python-docx`. |
| C. Also the source (HTML/LaTeX from career-ops) | Lets you regenerate; more storage logic. |

**Recommendation: B** (PDF + DOCX), since Indian portals sometimes ask for Word. Store career-ops source files only if you want regeneration later.

**Answer:** ______

### D5 — Relationship between `cv.md` and resume PDFs 🔴

Context: `cv.md` (career-ops) is the source of truth for facts — drafts and answer reviews may only cite it (R4.3, R10.5). PDFs are what you send; they may be older or tailored.

| Option | Meaning |
|---|---|
| **A. `cv.md` = facts; PDFs = sent artifacts** | Grounding always uses `cv.md`. A PDF's extracted text is used only for keyword coverage and "what did I send" lookups. |
| B. Ground drafts in the specific PDF sent to that company | More precise per application, but old PDFs may contain claims you've since corrected. |
| C. Extract a new `cv.md` from each PDF | Duplicates career-ops' job; risk of drift. |

**Recommendation: A.** Optionally warn when a sent PDF contains a number or skill that isn't in `cv.md` (drift check).

**Answer:** ______

## Infrastructure and project

### D6 — Where the app's data lives on disk, and backups 🔴

Data = Postgres volume, resume files, exported reports. Personal data must never be committed.

| Option | Notes |
|---|---|
| **A. `<data dir>` (outside the repo)** with `postgres/`, `resumes/`, `exports/`; bind-mounted into Docker | Clear separation from code; easy to back up. |
| B. Docker named volumes only | Simplest, but harder to find/back up on Windows. |
| C. Inside the repo under a gitignored `data/` | Convenient; one `git clean -fdx` away from losing everything. |

Backups: **recommended** nightly `pg_dump` + copy of `resumes/` to a second location you choose (another drive, or a Google Drive-synced folder), keep 14 days.

**Answer (location):** ______ **Answer (backup target):** ______

### D7 — Project location, name and repo visibility 🔴

- Location/name: currently `job-agent`. Keep, or rename (e.g. `jobpilot`, `hireflow`)? **Answer:** ______
- Repo visibility: for your resume, a **public GitHub repo** is most useful. That requires: no personal data in the repo (D6), a synthetic demo dataset and screenshots, and your `cv.md` never committed. Alternative: private repo, shown on request. **Recommendation:** public, with demo data. **Answer:** ______
- Licence if public: MIT (recommended) / Apache-2.0 / none. **Answer:** ______

### D8 — Database 🔴

| Option | Notes |
|---|---|
| **A. PostgreSQL 16 in Docker** | Needed for: SKIP LOCKED queue, LISTEN/NOTIFY streaming, pg_trgm, partial unique indexes, LangGraph Postgres checkpointer. Docker Desktop is installed. |
| B. SQLite | Zero setup, but loses all of the above; would change the design. |

**Recommendation: A** (the design depends on it). Tests use testcontainers (needs Docker running).

**Answer:** ______

### D9 — Claude API key and budget 🔴

- Do you have an Anthropic API key (console.anthropic.com), or should we set up `ant auth login`? **Answer:** ______
- Monthly budget you're comfortable with (estimate at ~100 scored jobs + 20 shortlisted + 40 reviewed answers per month ≈ **$9–12/month** on Opus 5.5): **Answer:** ______
- Daily hard cap (default $2): **Answer:** ______

### D10 — Model per node

Default in the design: **Claude Opus 5.5 for every node**, tuned with effort (low: extraction, transcript split, follow-ups; medium: scoring, contacts, drafts; high: answer review, prep plan). Cheaper options, if you want them, are Claude Sonnet 5.5 ($2/$10 per MTok) or Claude Haiku 5.5 ($0.10/$0.50) — most plausible for `extract_facts` and `split_transcript`. Any switch must pass that node's eval set.

**Answer:** keep Opus 5.5 everywhere / switch these nodes: ______

### D11 — Google Sheet

- Columns and what each row is (company / opening / both): **Answer:** ______
- Can it be shared as "anyone with the link can view"? Yes → CSV export (simplest). No → Google service account + Sheets API read-only. **Answer:** ______
- One tab or several? **Answer:** ______

### D12 — Sync applications to the career-ops tracker?

| Option | Notes |
|---|---|
| A. No sync — the new app is the tracker | Simplest; career-ops tracker stays for career-ops-only evaluations. |
| **B. One-way export** (new app → career-ops `batch/tracker-additions/*.tsv`, merged by `merge-tracker.mjs`) | career-ops modes (`followup`, `patterns`, `interview-prep`) keep seeing your applications. |
| C. Two-way sync | Conflict handling; not worth it. |

**Recommendation: B**, on an explicit "sync" action.

**Answer:** ______

### D13 — LinkedIn account type

Free (200-character connection notes) or Premium (300)? **Answer:** ______

### D14 — Gmail job-alert ingestion (phase 10)

Read-only Gmail access to parse Naukri / Cutshort / LinkedIn / Instahyre alert emails. Yes / no / later? Which senders do you actually get alerts from? **Answer:** ______

## Interviews

### D15 — How you'll capture interviews

| Option | Notes |
|---|---|
| A. Type each question and answer in the dashboard | Most accurate; more effort right after a call. |
| B. Paste free-form notes or a transcript; AI splits into Q&A; you confirm | Fastest; the split may need edits. |
| **C. Both** (default B, edit like A) | |

Also: do you take notes during interviews, or write them from memory afterwards? **Answer:** ______

### D16 — Starting topic taxonomy

Proposed seed (edit freely):

- `dsa/{arrays, strings, hashing, two-pointers, sliding-window, trees, graphs, dp, heaps, sorting-searching}`
- `system-design/{fundamentals, caching, databases, queues-streaming, scalability, consistency, api-design, observability, case-study}`
- `backend/{rest-api, auth, concurrency, microservices, error-handling, testing}`
- `python/{core, async, fastapi, internals}` · `go/{core, concurrency, internals}`
- `databases/{sql-queries, indexing, transactions, postgres, clickhouse, timeseries, modeling}`
- `data-engineering/{etl-elt, dbt, pipelines}`
- `cloud-devops/{aws, docker, kubernetes, ci-cd, linux}`
- `ai-llm/{llm-basics, rag, agents, langgraph, evals}`
- `fintech/{trading-domain, payments}`
- `behavioral/{conflict, ownership, failure, leadership, ambiguity, prioritization}` · `project-deep-dive` · `hr/{salary, notice, motivation}`

**Answer:** accept / changes: ______

### D18 — Exporting rounds into career-ops

Write a career-ops session file (`interview-prep/sessions/*.md`) automatically when a round is completed, or only when you press "Export"? The requirement currently says on request (R10.9). **Recommendation:** on request. **Answer:** ______

## Operations

### D17 — career-ops dependency 🔴

- career-ops install: the Claude Code plugin cache (plugin copy, v1.38.0; the path changes on plugin updates). Data: a separate local data folder.
- Options: **A. configure both paths in `.env`; app checks the version at startup and warns on mismatch** · B. clone career-ops into its own checkout (e.g. `<career-ops checkout>`) used only by the app, pinned to a tag — stable path, independent of plugin updates.
- **Recommendation: B** for stability (the plugin path includes the version number and moves on update), still using the same data folder.

**Answer:** ______

### D19 — Scheduling

- Scan frequency: daily at 09:00 IST (recommended) / twice daily / manual only. **Answer:** ______
- Follow-up days: +7 and +14 (default) or other. **Answer:** ______
- Posting-age limit for scans: currently 45 days in `portals.yml` (see D30). **Answer:** ______

### D20 — Notifications

None (check dashboard) / Windows desktop notification / email to yourself / Telegram bot. Triggers: new jobs ≥ 4.0, follow-up due, drafts ready. **Recommendation:** none in MVP, Telegram or email-to-self later. **Answer:** ______

### D21 — Dashboard authentication

Local only (bound to 127.0.0.1, no login) for MVP; a single token if ever exposed. **Recommendation:** local-only now. **Answer:** ______

### D22 — Deployment target

Local Docker Compose only, or keep a path to a small cloud VM (e.g. so the scheduler runs while your laptop is off)? The design stays cloud-compatible either way. **Answer:** ______

### D23 — Approval UI

Own approval screens in the dashboard (planned) vs plugging in LangChain Agent Inbox (needs LangGraph Server + LangSmith key). We adopt its interrupt schema either way. **Recommendation:** own UI. **Answer:** ______

### D24 — Resume-Matcher (≈27k-star open-source ATS tool)

Not in MVP; career-ops `keyword-match.mjs` covers keyword coverage. Revisit after MVP? **Answer:** ______

### D25 — Scraping-based sources (JobSpy for Naukri / LinkedIn / Indeed)

Rejected in the design because those sites' terms forbid scraping and accounts/IPs get blocked. Confirm, or do you want it as an opt-in source at your own risk? **Recommendation:** keep rejected. **Answer:** ______

### D26 — Evaluation data

Evals need your labels: ~40 JDs scored 1–5, ~30 interview answers marked strong/solid/gap, ~15 draft cases, ~10 interview notes split into Q&A. Roughly 3–4 hours of your time, spread out. Can you do this, and should we start collecting from real usage (label as you go in the UI)? **Recommendation:** label as you go; add a "label this" action in the UI. **Answer:** ______

### D27 — Observability backend

Console logs only (MVP) / Jaeger container (local traces) / LangSmith (hosted, free tier) for LLM traces. **Recommendation:** logs + `llm_calls` table in MVP; Jaeger profile later. **Answer:** ______

### D28 — Toolchain 🔴

Python 3.12 (installed) with **uv** (installed); Node 22 (installed) with **npm** (installed) or pnpm; GitHub Actions for CI; pre-commit hooks (ruff, mypy, eslint). **Recommendation:** as listed, npm. **Answer:** ______

### D29 — Data retention

Keep everything forever (default) or auto-delete interview Q&A / contacts after N months of a closed application? **Answer:** ______

### D30 — Pending career-ops scanner fixes (from the scan on 2026-11-02)

Proposed changes to the career-ops data folder's `portals.yml`, not yet applied — you hadn't answered when the project discussion started:

1. Add title keywords: "Software Engineer", "Software Developer", "SDE", "Golang", "Go Developer", "Platform Engineer".
2. Remove "Java" and ".NET" from blocked titles (you're open to any stack).
3. Raise posting-age limit 45 → 90 days.
4. Drop postings with no location (`strict: true`) so US-only roles can't slip in.
5. Add Indian product companies for the user's preferred cities.
6. Disable the EU/US template companies and Spain/EU searches.

Also: discard a mis-located (US) line in `data/pipeline.md`.

**Answer:** apply all / apply: ______
