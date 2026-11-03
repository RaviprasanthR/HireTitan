# Project context — read this first in a new session

Last updated: 2026-11-03 · Maintainer: Ravi Prasanth R · Summary kept by Claude (Claude Code)

This file captures project decisions so work can resume in a new session without the old conversation. Keep it updated at the end of every working session. It holds **project facts only**; the maintainer's personal job-search notes live in the gitignored `docs/private/` folder.

---

## 1. What and why

- **HireTitan** is an open-source, self-hosted AI job-search assistant: anyone can clone it and run it for their own search (one user per install, BYO LLM key).
- It is also the maintainer's showcase project, so it is built production-grade: spec-driven, test-first, validated and versioned AI, prompt-injection defence.
- Repo: `github.com/RaviprasanthR/HireTitan` (private now, public at first release, MIT).

## 2. Working agreements

- **Plan before implementing.** No code until a feature's spec, plan and tasks are approved and Ravi explicitly says to start.
- **GitHub Spec Kit** spec-driven development, one feature at a time (`specs/NNN-name/`), with ecc and superpowers skills in supporting roles.
- **TDD:** red → green → refactor per task, tests named after requirement/scenario IDs; real PostgreSQL in tests.
- **Reuse before building:** career-ops (MIT) is a bundled dependency for job sources.
- **Honesty:** the user's confirmed profile is the only source of candidate facts; AI never invents experience.
- **Git:** `master` is the main branch; one branch per feature cut from `master`, merged back by GitHub pull request after tests pass. Commit messages: `[<branch> - <feature>] - If applied this commit will <change>` (see `CONTRIBUTING.md` and the `commit` skill). Ravi prefers questions asked in rounds via the question dialog.

## 3. Key documents

| File | Role |
|---|---|
| `docs/clarified-requirements.md` | **Approved requirements baseline** (2026-11-03) |
| `.specify/memory/constitution.md` | Binding principles and quality gates |
| `CONTRIBUTING.md` | Branching, commit format, PR flow |
| `docs/archive/specs-v0/` | Earlier monolithic specs (requirements, design, prompts, tasks, open decisions, analysis). Input only, not binding |

## 4. History

- **2026-11-02/03:** First specs written as one monolithic set (now in `docs/archive/specs-v0/`): hexagonal design, Postgres schema, LangGraph workflows, prompts P1–P9 with schemas, validator chain, TDD task plan, open decisions D1–D30.
- **2026-11-03 (session 2):** Switched to **GitHub Spec Kit**. Deep analysis and ~80 questions (`06-analysis-and-questions.md`), then a Q&A round produced **`docs/clarified-requirements.md`**. Key outcomes: renamed **HireTitan**; the app owns the profile (resume upload + AI extraction + manual edits); AI proposes search queries, the user approves, runs are manual; AI scoring optional; first release = setup & profile, job search, applications, outreach drafts, tailored resume (PDF + DOCX); interviews in R2; provider-agnostic LLM (OpenAI, Anthropic, Gemini + OpenAI-compatible); LangGraph + direct SDK calls; default budget $25/month; ports only at real boundaries.
- **2026-11-03 (scope):** HireTitan is for anyone: self-hosted, global with India-friendly defaults, `docker compose up` + first-run wizard, career-ops required and bundled. Nothing person-specific is hard-coded; all preferences are user settings.
- **2026-11-03 (sources):** Built-in global company list (company name, city, website, careers URL, resolved board; no HR contacts) → career-ops ATS boards; careers-page fetch + AI extraction with a "check manually" fallback; Gmail job alerts (read-only); Adzuna/Jooble/Careerjet with the user's own key; career-ops free boards optional; manual paste. No scraping or paid scraped-data APIs. ATS discovery recon: 14/62 seed companies resolve automatically.
- **2026-11-03 (setup):** Baseline approved. Spec Kit 1.2.6 initialised (Claude integration, Python scripts). Constitution v1.0.0 ratified, amended to **v1.1.0** (master branch, PR merges, project commit format). Old specs archived and redacted of personal data. Pre-spec backend code removed from the repo. **First commit = repository skeleton** on `master`: README, LICENSE, CONTRIBUTING, editor/git config, `.env.example`, `backend/` and `frontend/` placeholders, `specs/`, commit-msg hook and `commit` skill.

## 5. Next steps

1. Push `master` to the HireTitan remote (when Ravi says so).
2. `git switch -c 001-setup-and-profile master`, then `/speckit-specify` for **001-setup-and-profile** (install, setup wizard, resume upload + extraction, profile editing, re-upload diff, preferences), then clarify → plan → tasks → analyze, each approved by Ravi.
3. Open items from `docs/clarified-requirements.md` §13: missing careers URLs, fuzzy dedup rules, aggregator terms check, Gmail OAuth guide, default models per provider, offer comparison, pay handling when unstated.

## 6. How to resume in a new session

Open Claude Code in the repo; `CLAUDE.md` points here. Run `git config core.hooksPath .githooks` once per clone.

## 7. How to update this file

At the end of each session: update "Last updated", add a line to §4 History, and refresh §5 Next steps. Personal notes go in `docs/private/`, never here.
