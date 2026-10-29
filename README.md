# SGJio

A web app that helps international residents learn Singapore's cultural norms and build an evidenced record of their integration effort. IS4301 team project. Backlog: Jira project **SCRUM** · Design: Figma file **SGJIO**.

This repository holds three parts that run side by side:

| Folder         | What it is                                           | Runs on                                     |
| -------------- | ---------------------------------------------------- | ------------------------------------------- |
| `web/`         | Main app for newcomers and Singaporeans (React)      | http://localhost:5173                       |
| `admin/`       | Admin portal for content administrators (React)      | http://localhost:5174                       |
| `api/`         | Backend shared by both (FastAPI + PostgreSQL)        | http://localhost:8000 · docs at `/api/docs` |
| `packages/ui/` | Shared design tokens, components and sign-in helpers | used by `web` and `admin`                   |
| `content/`     | The lessons SGJio starts with, as files              | loaded by the seed                          |

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
python -m app.cli seed             # admin account, demo user, topics and the lessons in content/
cd ..

# 3. Front ends
npm install
cp web/.env.example web/.env.local # Windows: copy web\.env.example web\.env.local
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

## Sign in with Google

The main app's sign-in and register pages have **Continue with Google** (SCRUM-92). It uses the team's Firebase project, `sgjio-966a1`, whose settings are already in `web/.env.example` and `api/.env.example`, so nobody needs a Firebase account to run it. The admin portal never offers Google.

**Setting it up on a copy you already had before this was added**, on any computer:

1. Copy the web settings file:
   - macOS or Linux: `cp web/.env.example web/.env.local`
   - Windows (PowerShell or Command Prompt): `copy web\.env.example web\.env.local`
2. Open `api/.env` in any editor and add this line at the end:
   ```
   FIREBASE_PROJECT_ID=sgjio-966a1
   ```
3. Install the new packages and update the database, as in [After pulling or merging](#after-pulling-or-merging).
4. Restart the API and `npm run dev:web` (both read their settings only when they start).
5. Open **http://localhost:5173/sign-in** and select **Continue with Google**.

| If you see                                       | Do this                                                                                              |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| No Google button                                 | `web/.env.local` is missing or empty: repeat step 1, then restart `npm run dev:web`                  |
| "Google sign-in isn't set up on this server"     | `FIREBASE_PROJECT_ID` is missing from `api/.env`: repeat step 2, then restart the API                |
| Google's window doesn't open                     | Allow pop-ups for `localhost` in your browser                                                        |
| An error inside Google's window about the domain | Use `http://localhost:5173`, not `127.0.0.1` or your computer's IP: Firebase only allows `localhost` |
| "We couldn't confirm your Google sign-in"        | The API terminal shows why on a line starting `Google sign-in token refused`                         |

**Using your own Firebase project instead** (optional): in the [Firebase console](https://console.firebase.google.com), add a project, enable **Authentication → Sign-in method → Google**, then add a web app (**Project settings → Your apps → </>**). Put its `firebaseConfig` values in `web/.env.local` and its project id in `api/.env`. Leaving both empty removes the Google button and nothing else changes.

## After pulling or merging

Your database is your own (it runs in Docker on your machine), so nobody else's data reaches it. Someone else's changes may need new packages, new database tables or new lessons. Run this from the repo root each time you pull or merge `main`:

```bash
npm install
cd api && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m alembic upgrade head     # apply any new migrations
python -m app.cli seed             # load new or changed lessons from content/
cd ..
```

Then restart `npm run dev:web` / `npm run dev:admin` if they were running. The API reloads by itself.

Skipping the migration step leaves your database behind the code, and pages fail with a 500 error. The API terminal then shows `column ... does not exist` or `relation ... does not exist`. To check, run `python -m alembic current` in `api/`: it should end in `(head)`.

Three more things to know:

- **`api/.env.example` or `web/.env.example` changed?** Copy any new settings into your own `api/.env` or `web/.env.local`.
- **What the seed does to your data.** It is safe to run again. It adds missing accounts and topics and never touches your progress. Every lesson that has a file in `content/lessons` is reset to match its file and published as a new version if anything differed, so edits you made to one in the admin portal are replaced. Lessons you created yourself are left alone. The first time, it finds your existing lessons by title; a seeded lesson you had renamed is not recognised, and the seed adds a second copy next to it.
- **Starting over.** If your local data is in a mess, delete it and build it again. This removes everything in your local database, but nobody else's:

  ```bash
  docker compose down -v && docker compose up -d
  cd api && python -m alembic upgrade head && python -m app.cli seed
  ```

## Looking inside the database

Only the `db` container has to be running for this — the API does not.

### With DBeaver

Install [DBeaver Community](https://dbeaver.io/download/), then **Database → New Database Connection → PostgreSQL** and fill in:

| Field    | Value       |
| -------- | ----------- |
| Host     | `localhost` |
| Port     | `5432`      |
| Database | `sgjio`     |
| Username | `sgjio`     |
| Password | `sgjio`     |

Select **Test Connection** (DBeaver downloads the PostgreSQL driver the first time, which takes a moment), then **Finish**. The tables are under **sgjio → Databases → sgjio → Schemas → public → Tables**; open one to see its rows, or select **SQL Editor → New SQL script** to write a query.

Two settings worth knowing. Tick **Show all databases** on the connection's PostgreSQL tab if you also want to see `sgjio_test`. And DBeaver does not save edits until you select **Save**, so a changed cell is only in the grid until then.

### With psql instead

No install needed, since it runs inside the container:

```bash
docker compose exec db psql -U sgjio -d sgjio
```

| At the `sgjio=#` prompt | What it does                                       |
| ----------------------- | -------------------------------------------------- |
| `\dt`                   | list the tables                                    |
| `\d lessons`            | show one table's columns                           |
| `select * from topics;` | read rows                                          |
| `\x`                    | switch to one field per line, for long lesson text |
| `\q`                    | quit                                               |

After seeding you should find 2 users, 6 topics and 18 published lessons, each a deck of cards with illustrations and questions (plus a draft "Card gallery"), their images and audio in `media_assets`, and some completed lessons for the Newcomer account so the landing page circles have something to show. [`docs/data-model.md`](docs/data-model.md) explains how the tables relate.

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
| First admin, or recovery  | `cd api && python -m app.cli create-admin --email you@example.com --name "Your Name"` |
| Load lessons from files   | `cd api && python -m app.cli import-lessons --publish` (see `content/README.md`)      |
| Add demo learners         | `cd api && python -m app.cli demo-activity` (for lesson insights; replaces earlier)   |

Add and remove other administrators in the portal: select your name at the top right, then **Administrators**. Invite emails arrive in Mailpit.

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
