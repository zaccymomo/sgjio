# SGJio

A web app that helps international residents learn Singapore's cultural norms and build an evidenced record of their integration effort. IS4301 team project. Backlog: Jira project **SCRUM** · Design: Figma file **SGJIO**.

> **This is the `arch/microservices` branch.** The back end is split into four services behind an API gateway, talking through RabbitMQ. The front ends are unchanged. `main` still has the single FastAPI back end (`api/`). Why and how: [docs/architecture/](docs/architecture/README.md) (decisions in [decisions/](docs/architecture/decisions/README.md), pictures in [diagrams.md](docs/architecture/diagrams.md)).

## What is where

| Folder                   | What it is                                                                 | Runs on                       |
| ------------------------ | -------------------------------------------------------------------------- | ----------------------------- |
| `web/`                   | Main app for newcomers and Singaporeans (React)                            | http://localhost:5173         |
| `admin/`                 | Admin portal for content administrators (React)                            | http://localhost:5174         |
| `packages/ui/`           | Shared design tokens, components and sign-in helpers                       | used by `web` and `admin`     |
| `services/gateway/`      | nginx: the only way in; routes `/api/*` and checks sessions with Identity  | http://localhost:8000         |
| `services/identity/`     | Accounts, sign-in, sessions, administrators, profile, introduction         | :8001 (Swagger at `/docs`)    |
| `services/content/`      | Topics, lessons and versions, media, reported problems, aptitude questions | :8002 (Swagger at `/docs`)    |
| `services/learning/`     | Lesson runs, progress, search, review, the aptitude test, lesson insights  | :8003 (Swagger at `/docs`)    |
| `services/notification/` | Sends the emails (worker, no HTTP API)                                     | Mailpit http://localhost:8025 |
| `contracts/`             | The events the services exchange, as JSON Schemas, and their validator     |                               |
| `templates/platform/`    | Plumbing every service copies (errors, logging, outbox, consumer, ...)     |                               |
| `infra/`                 | RabbitMQ definitions, Postgres init script                                 |                               |
| `e2e/`                   | End-to-end tests against the whole stack through the gateway               |                               |
| `scripts/`               | `seed-all.sh` (seed every service), `e2e.sh` (run the e2e suite)           |                               |
| `content/`               | The lessons and aptitude questions SGJio starts with, as files             | loaded by the seed            |
| `docs/`                  | Data model, product decisions, architecture                                |                               |

Each service has a README with its tables, API, events, commands and tests.

## Tech stack

- **Front end:** React 19, TypeScript, Vite, React Router, Tailwind CSS v4, lucide icons, Inter font
- **Services:** Python 3.11, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (one database per service), Argon2 password hashing
- **Between services:** nginx gateway with forward auth; RabbitMQ 4.4 topic exchange; transactional outbox
- **Local:** Docker Compose runs everything except the two Vite servers (project `sgjio-ms`): 4 Postgres, RabbitMQ, Mailpit, 4 services, the gateway
- **Quality:** Ruff, pytest, ESLint and Prettier, GitHub Actions CI (one job per service, platform template, contracts, gateway, front end, end to end)

## First-time setup

You need:

- **macOS, Linux, or WSL 2 on Windows.** The scripts are bash, so on Windows run everything inside WSL, with Docker Desktop's WSL integration turned on.
- **Docker Desktop**
- **Node 20.19+ or 22.12+** (Vite needs one of these; Node 24 works)
- **[uv](https://docs.astral.sh/uv/)**, only to run tests: a service's, the end-to-end suite or the contracts check. It fetches Python 3.11 itself; no conda or system Python needed.

```bash
npm install
cp web/.env.example web/.env.local
./dev.local --seed                   # builds and starts the stack, seeds it, then both front ends
```

The first build takes a few minutes. `./dev.local --seed` does, in order:

```bash
docker compose up -d --build --wait   # everything in Docker, healthy (migrations run as each service starts)
scripts/seed-all.sh                   # Identity, then Content, then Learning once the events have arrived
npm run dev:web                       # http://localhost:5173 (Vite proxies /api to the gateway on :8000)
npm run dev:admin                     # http://localhost:5174
```

Ctrl-C stops the two Vite servers; the stack keeps running in Docker. Next time, `./dev.local` without `--seed` is enough. Stop the stack with `docker compose down` (keeps your data) or `docker compose down -v` (wipes it).

The monolith on `main` also uses port 8000: stop its API (and `docker compose down` there) before starting this branch. The two use different compose projects, so their data never mixes.

## Running it

| What                                                 | Where                                                                                                      |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Main app                                             | http://localhost:5173                                                                                      |
| Admin portal                                         | http://localhost:5174                                                                                      |
| Gateway (what the front ends call)                   | http://localhost:8000/api/...                                                                              |
| Swagger, per service (direct, bypassing the gateway) | Identity http://localhost:8001/docs · Content :8002/docs · Learning :8003/docs                             |
| RabbitMQ management (`sgjio` / `sgjio`)              | http://localhost:15672: queues `learning.events`, `content.events`, `notification.events` and their `.dlq` |
| Mailpit: every email the app sends                   | http://localhost:8025                                                                                      |
| Postgres (user = password = database name)           | identity 5433 · content 5434 · learning 5435 · notification 5436                                           |

Content's and Learning's signed-in routes answer Swagger's "Try it out" with 401: they only accept requests that came through the gateway. Identity's routes and public media work there.

Seeded accounts (development only):

| Where                      | Email                        | Password       |
| -------------------------- | ---------------------------- | -------------- |
| Main app                   | `newcomer@sgjio.example.com` | `UserPass123`  |
| Main app: quiz at Level 1  | `starter@sgjio.example.com`  | `UserPass123`  |
| Main app: mixed levels     | `mixed@sgjio.example.com`    | `UserPass123`  |
| Main app: quiz at Level 4  | `advanced@sgjio.example.com` | `UserPass123`  |
| Main app: skipped the quiz | `skipped@sgjio.example.com`  | `UserPass123`  |
| Admin portal               | `admin@sgjio.example.com`    | `AdminPass123` |

To see an email arrive in Mailpit:

```bash
docker compose exec identity python -m app.cli send-reset --email admin@sgjio.example.com --scope admin
```

For lesson insights, add 60 demo learners and their lesson runs: `scripts/seed-all.sh --demo` (replaces the previous demo learners).

## Sign in with Google

The main app's sign-in and register pages have **Continue with Google** (SCRUM-92). It uses the team's Firebase project, `sgjio-966a1`: its web settings are in `web/.env.example`, and Identity's `FIREBASE_PROJECT_ID` is already set in `docker-compose.yml`, so nobody needs a Firebase account. The admin portal never offers Google.

1. Make sure `web/.env.local` exists (copied from `web/.env.example`), then restart `npm run dev:web`.
2. Open **http://localhost:5173/sign-in** and select **Continue with Google**.

| If you see                                       | Do this                                                                                                                            |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| No Google button                                 | `web/.env.local` is missing or empty: copy it again, then restart `npm run dev:web`                                                |
| "Google sign-in isn't set up on this server"     | Identity is running without `FIREBASE_PROJECT_ID` (`docker-compose.yml` sets it): `docker compose up -d --force-recreate identity` |
| Google's window doesn't open                     | Allow pop-ups for `localhost` in your browser                                                                                      |
| An error inside Google's window about the domain | Use `http://localhost:5173`, not `127.0.0.1` or your computer's IP: Firebase only allows `localhost`                               |
| "We couldn't confirm your Google sign-in"        | `docker compose logs identity` shows why, on a line containing `Google sign-in token refused`                                      |

**Using your own Firebase project instead** (optional): in the [Firebase console](https://console.firebase.google.com), add a project, enable **Authentication → Sign-in method → Google**, then add a web app. Put its `firebaseConfig` values in `web/.env.local`, and its project id in a `.env` file next to `docker-compose.yml` as `FIREBASE_PROJECT_ID=...`, then `docker compose up -d identity`. Leaving `web/.env.local` empty removes the Google button and nothing else changes.

## After pulling or merging

Your databases are your own (Docker volumes on your machine). Someone else's changes may need new packages, rebuilt images, new migrations or new lessons. From the repo root:

```bash
npm install
./dev.local --seed      # rebuilds changed images; each service applies its own migrations when it starts
```

The seed is safe to run again. It adds missing accounts and topics and never touches anyone's progress. Every lesson that has a file in `content/lessons` is reset to match its file and published as a new version if anything differed, so edits you made to one in the admin portal are replaced; lessons you created yourself are left alone.

**Starting over.** If your local data is in a mess, wipe this branch's volumes (and nobody else's) and build it again:

```bash
docker compose down -v && ./dev.local --seed
```

## Looking inside a database

Each service has its own database; only that container has to be running.

```bash
docker compose exec identity-db psql -U identity -d identity
docker compose exec content-db psql -U content -d content
docker compose exec learning-db psql -U learning -d learning
docker compose exec notification-db psql -U notification -d notification
```

| At the `=#` prompt      | What it does                                       |
| ----------------------- | -------------------------------------------------- |
| `\dt`                   | list the tables                                    |
| `\d lessons`            | show one table's columns                           |
| `select * from topics;` | read rows                                          |
| `\x`                    | switch to one field per line, for long lesson text |
| `\q`                    | quit                                               |

With **DBeaver** (Database → New Database Connection → PostgreSQL): host `localhost`, the port from the table above, and user, password and database all the service's name (for example `content` / `content` / `content` on 5434). Each also has a `<name>_test` database that the service's tests use.

After seeding you should find 6 users in Identity; 6 topics, 24 published lessons (each a deck of cards with illustrations and questions) plus a draft "Card gallery", and their images and audio in `media_assets` in Content; and in Learning the same topics and lessons in its read models (`learnable_topics`, `learnable_lessons`, `lesson_decks`) and some completed lessons for the Newcomer. [`docs/data-model.md`](docs/data-model.md) explains every table.

## Everyday commands

| Task                                 | Command                                                                                                  |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Start everything                     | `./dev.local` (`--seed` to seed too)                                                                     |
| Rebuild one service after a change   | `docker compose up -d --build --wait content`                                                            |
| A service's logs                     | `docker compose logs -f learning`                                                                        |
| Run a service command                | `docker compose exec content python -m app.cli <command>` (each service's README lists them)             |
| A service's tests                    | `cd services/<name> && .venv/bin/python -m pytest` (first time: see CONTRIBUTING.md)                     |
| A service's lint and format          | `cd services/<name> && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format .`            |
| New migration for a service          | `cd services/<name> && .venv/bin/python -m alembic revision --autogenerate -m "what changed"`            |
| End-to-end tests                     | `scripts/e2e.sh` (`--resilience` also stops and starts containers)                                       |
| Event contracts                      | `contracts/.venv/bin/python contracts/validate.py` (first time: see `contracts/README.md`)               |
| Gateway routing tests                | `services/gateway/tests/run.sh`                                                                          |
| Front-end lint, format, types, build | `npm run lint` · `npm run format` · `npm run typecheck` · `npm run build`                                |
| First admin, or recovery             | `docker compose exec identity python -m app.cli create-admin --email you@example.com --name "Your Name"` |
| Load lessons from files              | `docker compose exec content python -m app.cli import-lessons --publish` (see `content/README.md`)       |

Add and remove other administrators in the portal: select your name at the top right, then **Administrators**. Invite emails arrive in Mailpit.

## Troubleshooting

| Symptom                                                    | Likely cause and fix                                                                                                                                                                                                                                           |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `port is already allocated` for 8000, 8025 or 1025         | `main`'s stack (its API or Mailpit) or another app holds the port. In the `main` checkout run `docker compose down`; on this branch `docker compose ps` shows what is running.                                                                                 |
| `docker compose up --wait` fails, a container is unhealthy | `docker compose ps` shows which; `docker compose logs <service>` says why (often a migration or a port clash).                                                                                                                                                 |
| Every page says "SGJio is unavailable right now" (503)     | A service the page needs is down. `docker compose ps`, then `docker compose up -d --wait`.                                                                                                                                                                     |
| Vite shows `ECONNREFUSED` for `/api`                       | The gateway isn't running: `docker compose up -d --wait`.                                                                                                                                                                                                      |
| A lesson you published doesn't appear for learners         | It normally takes under a second. Check `docker compose logs learning` and the `learning.events` queue (and its `.dlq`) in RabbitMQ's UI.                                                                                                                      |
| After a fresh `down -v`, learners see no topics            | Seed again (`scripts/seed-all.sh`). If seeding ran before the services were up, events sat in `sgjio.unrouted`: run `docker compose exec content python -m app.cli republish-catalog` and `docker compose exec identity python -m app.cli republish-learners`. |
| No email in Mailpit                                        | `docker compose logs notification`. It waits for the mail server and retries, so the email arrives once Mailpit is up.                                                                                                                                         |
| A reset link says it has expired                           | Links last 15 minutes and work once; a newer request cancels older links.                                                                                                                                                                                      |
| A service's tests fail to connect to Postgres              | Start its database: `docker compose up -d <name>-db` (tests use `<name>_test` on that container).                                                                                                                                                              |
| `ModuleNotFoundError` running a service's tools            | Use that service's own `.venv` (`.venv/bin/python -m ...`), made with uv as in CONTRIBUTING.md, not conda's or the system's Python.                                                                                                                            |

## How the pieces fit

- **One origin in development.** Each Vite server forwards `/api` to the gateway on :8000, which forwards each path to its service, so the browser sees a single site and cookies work without CORS.
- **Two kinds of session.** The main app and the admin portal each have their own cookie and sessions, kept by Identity. Being signed in to one never signs you in to the other (SCRUM-68 AC6).
- **Protecting a route.**
  - Identity: `Depends(require_user)` or `Depends(require_admin)` from `app/auth/deps.py`.
  - Content and Learning: `Depends(require_principal("app"))` or `("admin")` from `app/platform/principal.py`, and a matching `auth_request` location in `services/gateway/templates/gateway.conf.template`.
  - Front end: put the page inside the `<RequireAuth />` route in `App.tsx`. Signed-out visitors are sent to sign-in and brought back afterwards.
- **Changes travel as events.** When an administrator publishes a lesson, Content records an event with the change; Learning receives it and updates its own copy, usually within a second.
- **Styling.** Use the Tailwind classes generated from the Figma tokens in `packages/ui/src/theme.css`, such as `bg-brand`, `text-ink`, `border-line` and `rounded-md`. Reuse the components in `packages/ui` before writing new ones.

More detail:

- [`CONTRIBUTING.md`](CONTRIBUTING.md): branches, commits, pull requests, CI, per-service workflow
- [`docs/data-model.md`](docs/data-model.md): every service's tables and how they relate
- [`docs/decisions.md`](docs/decisions.md): values chosen for the open decisions in the stories
- [`docs/architecture/`](docs/architecture/README.md): the microservices build, its decision records and diagrams
- [`CLAUDE.md`](CLAUDE.md): project briefing read automatically by Claude Code
