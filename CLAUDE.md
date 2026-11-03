# HireTitan

Open-source, self-hosted AI job-search assistant (one user per install). Python/FastAPI/LangGraph + React. Built with **GitHub Spec Kit** spec-driven development and TDD.

**Start every session by reading `docs/CONTEXT.md`** (history, decisions, next steps). Then read **`.specify/memory/constitution.md`**, which is binding. `docs/private/` (gitignored, may not exist) holds the maintainer's personal notes; read it if present, never commit it.

Rules:
- Spec Kit flow per feature: `/speckit-specify` → `/speckit-clarify` → `/speckit-plan` → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`. Features live in `specs/NNN-name/`. Don't implement anything until Ravi has approved the feature's spec, plan and tasks and explicitly says to start.
- The requirements baseline is `docs/clarified-requirements.md`. Old specs in `docs/archive/specs-v0/` are input only, not binding.
- **Branches:** `master` is the main branch. Each feature gets its own branch cut from `master`, named after its spec folder (`001-setup-and-profile`). Merge back into `master` only through a GitHub pull request, after tests and gates pass. Never commit feature work directly on `master`.
- **Commits:** use the `commit` skill (`.claude/skills/commit/SKILL.md`). Format: `[<branch> - <feature>] - If applied this commit will <change>`. It's enforced by `.githooks/commit-msg` (run `git config core.hooksPath .githooks` once per clone). Commit only when Ravi asks.
- TDD: write the task's tests first (named after requirement/scenario IDs), see them fail, then code, then refactor. One commit per task.
- The user's confirmed profile in the app is the only source of candidate facts; AI never invents experience.
- The app must never send messages, emails or applications.
- No personal data in the repo: fixtures and demo data are synthetic. The maintainer's own files (career-ops data folder, resumes, `docs/private/`) are never committed or modified.
- Update `docs/CONTEXT.md` at the end of each session (project facts only; personal job-search notes go in `docs/private/`).
