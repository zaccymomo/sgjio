# SGJio: briefing for Claude Code

SGJio is an IS4301 team project: a **web app** (not a mobile app) that helps international residents in Singapore learn cultural norms (Singlish, hawker and workplace etiquette, and so on) and build an evidenced record of their integration effort. It is positioned alongside the government's PR journey, but **must never claim or imply that anything in the app improves PR approval chances**; ICA decides outcomes independently.

- **Backlog:** Jira project `SCRUM` on `is4301sgjio.atlassian.net`. Stories use "As a / I want / So that" with numbered GIVEN/WHEN/THEN acceptance criteria and MoSCoW priority. Refer to criteria as e.g. "SCRUM-62 AC5".
- **Design:** Figma file `SGJIO` (file key `rshLkESAaKlry48qBcYOLO`). Key frames: `home-screen` (node 30:8) and `topic-screen / Singlish` (63:5). Frames are drawn at 375px phone width; the app must also work on desktop.
- **Modules:** 1 lessons and quizzes (+ portfolio landing page), 2 buddy matching, 3 integration portfolio / tiers, 4 AI scenario chatbot. Sprint 1 covers accounts and the first lesson/admin stories.

## Repository layout

| Path           | What                                                                                            |
| -------------- | ----------------------------------------------------------------------------------------------- |
| `web/`         | Main app, React 19 + TS + Vite, port 5173                                                       |
| `admin/`       | Admin portal for content administrators, port 5174                                              |
| `packages/ui/` | Shared tokens (`src/theme.css`), components, `apiFetch`, `AuthProvider`/`RequireAuth`/`useAuth` |
| `api/`         | FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16, port 8000, docs at `/api/docs`                |
| `docs/`        | `data-model.md` (ERD), `decisions.md` (proposed defaults for open story decisions)              |

Both Vite servers proxy `/api` to FastAPI, so there is one origin and no CORS.

## Commands

The developer uses Anaconda. **Always run Python tools with `python -m`** from `api/` with `.venv` active, or conda's copies run instead and fail (`No module named 'psycopg'`).

```bash
docker compose up -d                                   # Postgres + Mailpit (http://localhost:8025)
cd api && python -m uvicorn app.main:app --reload      # API
python -m pytest                                       # 44 tests, uses the sgjio_test database
python -m ruff check . && python -m ruff format .
python -m alembic revision --autogenerate -m "..."     # then READ the generated file
python -m alembic upgrade head
python -m app.cli seed | create-admin | send-reset
npm run dev:web | dev:admin                            # from repo root
npm run lint && npm run format && npm run typecheck && npm run build
```

Seed logins: main app `newcomer@sgjio.example.com` / `UserPass123`; admin `admin@sgjio.example.com` / `AdminPass123`.

## Conventions

- Branch `SCRUM-<n>-short-name`; commit messages start `SCRUM-<n>: ...`; PRs into `main` need green CI (`.github/workflows/ci.yml`).
- Before finishing any change, run the relevant tests, lint, format and typecheck. CI also runs `alembic check`, so models and migrations must match.
- Never edit a migration already on `main`; add a new one. Enums are stored as VARCHAR + CHECK (`_enum()` in `models.py`), not native Postgres enums.
- New settings go in `api/app/config.py` **and** `api/.env.example`. Never commit `.env`.
- UI: use the Tailwind tokens (`bg-brand`, `text-ink`, `text-muted`, `text-subtle`, `border-line`, `bg-surface`, `text-danger`, `rounded-sm/md/lg`, `text-2xs`, `text-caption`) and reuse `@sgjio/ui` components (`Button`, `TextField`, `PasswordField`, `Alert`, `AuthCard`, `AppShell`, `AdminLayout`, `SignInForm`, `ErrorState`, `Placeholder`). Brand red `#F43F5E` is for highlights; errors use `danger` `#DC2626`.
- Pages not built yet show `<Placeholder story="SCRUM-xx">`. Replace it when building that story.
- Write user-facing copy in plain language; say "select", not "tap" (web app).

## Auth (already built, `api/app/auth/`)

- One `users` table with `role` (`user`/`admin`); **separate sessions per front end** (`AuthScope.APP` vs `ADMIN`), separate cookies (`sgjio_session` path `/api`, `sgjio_admin_session` path `/api/admin`). An app session never opens admin routes.
- Protect API routes with `Depends(require_user)` / `Depends(require_admin)` (`auth/deps.py`); everything in `routers/admin.py` is already admin-only. Protect pages by nesting under `<Route element={<RequireAuth />}>`.
- Errors are `{"detail": {"code", "message", ...}}`; the front end reads them via `ApiError`.
- Sign-in never reveals whether an email exists or is an admin. Lockout: 5 consecutive failures per email per scope blocks for 15 minutes (429 with `blocked_until`).
- Password rules: `password_rule_failures()` in `app/security.py` (8+ chars, a letter and a number).
- Password reset: `request_password_reset`, `check_reset_token`, `consume_reset_token`, `set_new_password` in `auth/reset.py`. Links last 5 minutes, work once, a new request cancels old ones. Endpoints `forgot-password`, `reset-password/check` and `reset-password` exist on both `/api/auth` and `/api/admin/auth`; the main-app pages are done (SCRUM-63) using `ForgotPasswordForm`/`ResetPasswordForm` from `@sgjio/ui`, and the admin pages (SCRUM-69) can reuse them.

## Product rules that stories depend on

- **Home page = portfolio (SCRUM-43):** one progress circle per topic with ≥1 published lesson, filled by _lessons completed / lessons available_ ("8 / 12"), empty "Not started", visibly distinct when complete; plus one overall figure; selecting a circle opens the topic's lesson list (SCRUM-53). A suggested next lesson from the weakest topic (SCRUM-6). **No daily streaks, no weekly lessons, no separate score, no leaderboard.** Keep the home screen minimal (the Integration Hub was removed).
- **Progress rules live in SCRUM-16:** answering a lesson's single quiz question completes it whether right or wrong; correctness is stored separately and the best result is kept; only currently published lessons count, so completed can never exceed available. Circles show completion; correctness feeds tiers (SCRUM-27).
- Lessons: under 2 minutes to read, exactly one topic, one single-choice quiz question at the end. Statuses Draft / Published / Withdrawn; withdrawn lessons are kept for users' history.
- Open decisions and the defaults chosen are in `docs/decisions.md`. Don't change them silently; flag it.
