# Getting started

HireTitan runs on your own computer. There is no account and no login, and your data stays on your machine.

## 1. Install

You need [Docker](https://www.docker.com/products/docker-desktop/) (Docker Desktop on Windows and macOS, Docker Engine on Linux).

```bash
git clone https://github.com/RaviprasanthR/HireTitan.git
cd HireTitan
cp .env.example .env        # on Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and set `POSTGRES_PASSWORD` to any password you like. Then:

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000>. The app listens on your computer only.

## 2. The AI key

HireTitan reads your OpenAI API key from `.env` only. It is never stored in the database, never shown in the browser and never written to logs.

1. Create a key on the OpenAI platform and put it in `.env`: `OPENAI_API_KEY=sk-...`
2. Restart the app: `docker compose restart api worker`.
3. Settings shows "Found, working". If it says "Missing" or "Rejected by the provider", fix the key in `.env`, restart, and press **Check again**.

Without a working key the app does not fail: AI tasks wait ("paused") and carry on by themselves once the key works. You can also use **Type it in myself** during setup to fill in your profile by hand, with no AI at all.

## 3. First-run setup

On a new install four cards guide you: your name, your resume, a review of the profile the AI extracted (edit anything, then confirm), and your job preferences. You can close the tab at any point and come back to the same card. The defaults for preferences are listed in [preference-defaults.md](preference-defaults.md).

Your confirmed profile is the only source of facts about you. The AI never adds experience you did not confirm.

## 4. Budget

Settings has a **monthly AI budget cap** (25 USD by default; 0 to 10000). Before every AI call HireTitan checks that this month's spend plus the call's estimated cost stays under the cap. If it would not, the work pauses and says why. Raise the cap and paused work resumes by itself. The spend shown is the sum of the costs recorded for your own calls.

## 5. What is sent to OpenAI, and what is masked

When your resume is read, the text of the resume goes to OpenAI so the model can pull out your details. Before it is sent:

- **Email addresses, phone numbers and links are masked.** They are replaced by placeholders and added back afterwards from your original text, so the model never sees them.
- Text that looks like instructions to an AI (hidden white text, "ignore previous instructions", fake system tags) is detected. You are told about it and asked how to continue; it is never followed.
- Anything the model returns must be found in your resume text, or it is dropped and shown to you in the review.

Nothing else about you is sent. The app does not send messages, emails or applications for you.

## 6. Your data

- **Delete one resume file:** Profile, Your resume files, Delete. Profile versions you already confirmed keep their content.
- **Delete everything:** Settings, Delete all my data, type `DELETE`. This empties the database and the stored files and takes you back to the first setup card. Your `.env` is not touched.

## 7. Updating and stopping

- Stop: `docker compose down` (your data stays in Docker volumes).
- Start again: `docker compose up`.
- Remove all data volumes too: `docker compose down -v`.

## Running from source (contributors)

Postgres in Docker, the rest on your machine. You need Python 3.12 with [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
git config core.hooksPath .githooks            # once per clone
docker compose up -d db                         # set POSTGRES_PORT if 5432 is taken
cd backend && uv sync && uv run alembic upgrade head
uv run python -m hiretitan.api_main             # one terminal
uv run python -m hiretitan.worker_main          # another terminal
cd ../frontend && npm ci && npm run dev         # a third
```

Set `HIRETITAN_LLM=fake` in `.env` to run with scripted replies and no key. Tests: `cd backend && uv run pytest` (needs Docker; they start their own PostgreSQL), `cd frontend && npm test`.
