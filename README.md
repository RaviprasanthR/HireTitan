
# HireTitan

**An open-source, self-hosted AI job-search assistant.** Upload your resume, set your preferences, and HireTitan finds relevant jobs from permitted sources, tracks your applications, drafts outreach and tailors your resume for each job. It never sends anything on your behalf: every AI output is a draft you approve.

> **Status: pre-alpha.** Feature 001 (setup and profile) is built; the other features are specified and built one at a time with [GitHub Spec Kit](https://github.com/github/spec-kit) and test-driven development.

## Quick start

You need [Docker](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
# edit .env: set POSTGRES_PASSWORD (and OPENAI_API_KEY, or leave it empty to type your profile in by hand)
docker compose up --build
```

Then open <http://127.0.0.1:8000>. Details, what is sent to OpenAI and how to delete your data are in the [getting-started guide](docs/user-guide/getting-started.md); the starting preference values are in [preference-defaults](docs/user-guide/preference-defaults.md). Platforms: checked on Windows 11 by hand; Linux is checked in CI (the `compose-smoke` and `e2e` jobs); macOS is expected to work but has not been tested.

## Planned features (first release)

| # | Feature | What it does |
|---|---|---|
| 001 | Setup & profile | `docker compose up`, first-run wizard, resume upload → AI-extracted editable profile, job preferences |
| 002 | Job search | AI-proposed queries you approve; jobs from public ATS boards, company careers pages, job-alert emails, aggregator APIs and manual paste; AI relevance check with visible reasons |
| 003 | Applications | Status tracking, follow-up reminders, referrals, recruiters, offers |
| 004 | Outreach drafts | Referral requests, LinkedIn notes, HR emails, follow-ups in your own writing style |
| 005 | Tailored resume | Per-job resume that never invents facts; ATS-friendly PDF + DOCX |

Later: interview notes and answer review, MCP / Claude Code access.

## Principles

- **Self-hosted, one user per install.** Your data and API keys stay on your machine.
- **Bring your own LLM key**: OpenAI, Anthropic, Google Gemini or any OpenAI-compatible endpoint.
- **Human in the loop.** The app never sends messages, emails or applications.
- **Truthful.** Your confirmed profile is the only source of facts; the AI never invents experience.
- **Permitted sources only.** No scraping of sites that forbid it.

The full rules are in the [constitution](.specify/memory/constitution.md); the requirements baseline is [docs/clarified-requirements.md](docs/clarified-requirements.md).

## Tech stack (planned)

Python 3.12 + uv · FastAPI · SQLAlchemy 2 + Alembic · PostgreSQL 16 · LangGraph · React + Vite + TypeScript · Docker Compose. Job sources via the bundled career-ops (MIT).

## Repository layout

```
.claude/skills/   Claude Code skills (Spec Kit commands, commit format)
.githooks/        Git hooks (commit message format)
.specify/         Spec Kit config, templates, scripts and the constitution
backend/          Python API and workers
frontend/         React web dashboard
specs/            One folder per feature: spec, plan, tasks
docs/             Context, requirements baseline, archive
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch flow and commit message format. After cloning, enable the hooks once:

```bash
git config core.hooksPath .githooks
```

## License

[MIT](LICENSE)
