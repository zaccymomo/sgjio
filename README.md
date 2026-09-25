# SGJio

A web app that helps international residents learn Singapore's cultural norms and build an evidenced record of their integration effort. IS4301 team project. Backlog: Jira project **SCRUM** · Design: Figma file **SGJIO**.

This repository holds three parts that run side by side:

| Folder         | What it is                                           | Runs on                                     |
| -------------- | ---------------------------------------------------- | ------------------------------------------- |
| `web/`         | Main app for newcomers and Singaporeans (React)      | http://localhost:5173                       |
| `admin/`       | Admin portal for content administrators (React)      | http://localhost:5174                       |
| `api/`         | Backend shared by both (FastAPI + PostgreSQL)        | http://localhost:8000 · docs at `/api/docs` |
| `packages/ui/` | Shared design tokens, components and sign-in helpers | used by `web` and `admin`                   |

## Tech stack

- **Front end:** React 19, TypeScript, Vite, React Router, Tailwind CSS v4, lucide icons, Inter font
- **Back end:** Python 3.11+, FastAPI, SQLAlchemy 2, Alembic migrations, PostgreSQL 16, Argon2 password hashing
- **Local services:** Docker Compose runs PostgreSQL and Mailpit, a test inbox that catches all email
- **Quality:** Ruff (Python lint and format), ESLint and Prettier (TypeScript), pytest, GitHub Actions CI

## First-time setup

You need **Node 20+**, **Python 3.11+** and **Docker Desktop**.

```bash
# 1. Database and test inbox
docker compose up -d

# 2. API
cd api
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m alembic upgrade head     # create the tables
python -m app.cli seed             # admin account, demo user, topics, a sample lesson
cd ..

# 3. Front ends
npm install
```

> **Always run Python tools as `python -m <tool>`** (`python -m alembic`, `python -m pytest`, `python -m uvicorn`, `python -m ruff`). This guarantees the copy inside `api/.venv` runs.
>
> **Using Anaconda?** Its `(base)` environment puts its own `alembic` and `pip` ahead of the venv's, which causes `ModuleNotFoundError: No module named 'psycopg'`. Run `conda deactivate` before activating `.venv` (your prompt should show only `(.venv)`), or turn it off for good with `conda config --set auto_activate_base false`. Check with `which python`: it should end in `api/.venv/bin/python`.

## Running it

Use three terminals:

```bash
# Terminal 1: API
cd api && source .venv/bin/activate && python -m uvicorn app.main:app --reload

# Terminal 2: main app
npm run dev:web

# Terminal 3: admin portal
npm run dev:admin
```

Sign in with the seeded accounts (development only):

| Where               | Email                        | Password       |
| ------------------- | ---------------------------- | -------------- |
| Main app (5173)     | `newcomer@sgjio.example.com` | `UserPass123`  |
| Admin portal (5174) | `admin@sgjio.example.com`    | `AdminPass123` |

Emails the app sends appear in Mailpit at **http://localhost:8025**. To try one:

```bash
cd api && python -m app.cli send-reset --email admin@sgjio.example.com --scope admin
```

## Everyday commands

| Task                      | Command                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------- |
| API tests                 | `cd api && python -m pytest`                                                          |
| API lint and format       | `cd api && python -m ruff check . && python -m ruff format .`                         |
| Front-end lint and format | `npm run lint` · `npm run format`                                                     |
| Type-check both apps      | `npm run typecheck`                                                                   |
| Build both apps           | `npm run build`                                                                       |
| New database migration    | `cd api && python -m alembic revision --autogenerate -m "what changed"`               |
| Apply migrations          | `cd api && python -m alembic upgrade head`                                            |
| Add an administrator      | `cd api && python -m app.cli create-admin --email you@example.com --name "Your Name"` |

The API tests use a separate `sgjio_test` database, so they never touch your data.

## How the pieces fit

- **One origin in development.** Each Vite server forwards `/api` to FastAPI, so the browser sees a single site. Cookies work without any CORS setup.
- **Two kinds of session.** The main app and admin portal each have their own cookie and sessions. Being signed in to one never signs you in to the other (SCRUM-68 AC6).
- **Protecting a route.**
  - API: add `Depends(require_user)` or `Depends(require_admin)` from `app/auth/deps.py`. Every route in `app/routers/admin.py` is already admin-only.
  - Front end: put the page inside the `<RequireAuth />` route in `App.tsx`. Signed-out visitors are sent to sign-in and brought back afterwards.
- **Styling.** Use the Tailwind classes generated from the Figma tokens in `packages/ui/src/theme.css`, such as `bg-brand`, `text-ink`, `border-line` and `rounded-md`. Reuse the components in `packages/ui` before writing new ones.
- **Placeholders.** Pages that a later story builds show a dashed card naming the Jira key. Replace the card when you build the page.

More detail:

- [`CONTRIBUTING.md`](CONTRIBUTING.md): branches, commits and pull requests
- [`docs/data-model.md`](docs/data-model.md): tables and how they relate
- [`docs/decisions.md`](docs/decisions.md): values chosen for the open decisions in the stories (to confirm as a team)
- [`CLAUDE.md`](CLAUDE.md): project briefing read automatically by Claude Code
