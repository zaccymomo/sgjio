# SGJio: briefing for Claude Code

SGJio is an IS4301 team project: a **web app** (not a mobile app) that helps international residents in Singapore learn cultural norms (Singlish, hawker and workplace etiquette, and so on) and build an evidenced record of their integration effort. It is positioned alongside the government's PR journey, but **must never claim or imply that anything in the app improves PR approval chances**; ICA decides outcomes independently.

- **Backlog:** Jira project `SCRUM` on `is4301sgjio.atlassian.net`. Stories use "As a / I want / So that" with numbered GIVEN/WHEN/THEN acceptance criteria and MoSCoW priority. Refer to criteria as e.g. "SCRUM-62 AC5".
- **Design:** Figma file `SGJIO` (file key `rshLkESAaKlry48qBcYOLO`). Key frames: `home-screen` (node 30:8) and `topic-screen / Singlish` (63:5). Frames are drawn at 375px phone width; the app must also work on desktop.
- **Modules:** 1 lessons and quizzes (+ portfolio landing page), 2 buddy matching, 3 integration portfolio / tiers, 4 AI scenario chatbot. Sprint 1 covers accounts and the first lesson/admin stories.

## Repository layout

| Path           | What                                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `web/`         | Main app, React 19 + TS + Vite, port 5173                                                                                                                  |
| `admin/`       | Admin portal for content administrators, port 5174                                                                                                         |
| `packages/ui/` | Shared tokens (`src/theme.css`), components, `apiFetch`, `AuthProvider`/`RequireAuth`/`useAuth`; `@sgjio/ui/lesson` is the lesson deck both front ends use |
| `api/`         | FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 16, port 8000, docs at `/api/docs`                                                                           |
| `docs/`        | `data-model.md` (ERD), `decisions.md` (proposed defaults for open story decisions)                                                                         |
| `content/`     | Lesson files the seed loads (`README.md` explains the format, `STYLE.md` the look)                                                                         |

Both Vite servers proxy `/api` to FastAPI, so there is one origin and no CORS.

## Commands

The developer uses Anaconda. **Always run Python tools with `python -m`** from `api/` with `.venv` active, or conda's copies run instead and fail (`No module named 'psycopg'`).

```bash
docker compose up -d                                   # Postgres + Mailpit (http://localhost:8025)
cd api && python -m uvicorn app.main:app --reload      # API
python -m pytest                                       # 495 tests, uses the sgjio_test database
python -m ruff check . && python -m ruff format .
python -m alembic revision --autogenerate -m "..."     # then READ the generated file
python -m alembic upgrade head
python -m app.cli seed | create-admin | send-reset | prune-media | demo-activity
python -m app.cli import-lessons [folder] [--publish]   # load lesson files (content/README.md)
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
- Administrators (SCRUM-81, `app/admins.py`): invited from the portal's Administrators page with a 3-day set-password link (`/set-password`), all with the same access. Removing one closes the account (`users.removed_at`), never deletes it; `User.is_admin` is false for removed ones, and every change is logged in `admin_events`. `create-admin` is only for the first administrator and recovery.
- Password reset: `request_password_reset`, `check_reset_token`, `consume_reset_token`, `set_new_password` in `auth/reset.py`. Links last 5 minutes, work once, a new request cancels old ones. Endpoints `forgot-password`, `reset-password/check` and `reset-password` exist on both `/api/auth` and `/api/admin/auth`; the main-app pages are done (SCRUM-63) using `ForgotPasswordCard`/`ResetPasswordCard` from `@sgjio/ui`, and the admin pages (SCRUM-69) can reuse them.

## Product rules that stories depend on

- **Home page = portfolio (SCRUM-43):** one progress circle per topic with ≥1 published lesson, filled by _lessons completed / lessons available_ ("8 / 12"), empty "Not started", visibly distinct when complete; plus one overall figure; selecting a circle opens the topic's lesson list (SCRUM-53, built: `/topics/:id` in `web/`, `GET /api/topics/{id}` in `app/progress.py`, same counting rules as the circles). Each lesson there shows "Last attempted on <date>" and its best score, or "Not attempted yet" (SCRUM-54, which replaced the cancelled quiz history, SCRUM-42). A suggested next lesson from the weakest topic (SCRUM-6). **No daily streaks, no weekly lessons, no separate score, no leaderboard.** Keep the home screen minimal (the Integration Hub was removed).
- **Progress rules live in SCRUM-16:** finishing a lesson completes it whether its answers were right or wrong; correctness is stored separately and the best result is kept; only currently published lessons count, so completed can never exceed available. Circles show completion; correctness feeds tiers (SCRUM-27). The best score is `best_correct` of `best_scored` on `lesson_completions`; each run through a deck is a `lesson_attempts` row with its `attempt_answers` (`api/app/learning.py`).
- **Lessons are decks of cards (SCRUM-19).** A card has Markdown text (bold, italics, lists, and at most one `{{blank}}`), an optional image and/or audio, and an optional question: 1 to 4 options, exactly one correct, an explanation, optional "why not" notes on wrong options, shuffled unless the author says not. A one-option question is a tap that fills the blank and isn't scored. A lesson needs at least one question to publish, belongs to exactly one topic, and should read in under 2 minutes. The document's rules live in `api/app/lesson_doc.py` (issues: blockers vs warnings); the shared types in `packages/ui/src/lesson/types.ts`.
- **Drafts and versions (SCRUM-52).** Editors always change a lesson's draft; publishing copies it into a numbered `lesson_versions` row, which is what users see. Statuses Draft / Published / Withdrawn; withdrawn lessons, and every version, are kept for users' history. Topic and position are not versioned.
- **Learners see the newest version** when they start or retake a lesson. Built in SCRUM-15/16 (`/lessons/:id` in `web/`): a lesson is complete when its deck is finished; the score is first-try correct answers out of the scored questions; the best percentage is kept, and a tie keeps the most recent; "mastered" means all correct. Answers are checked on the server, and the learner's copy of a lesson never contains which option is right.
- **Search (SCRUM-85).** The landing page's search bar drops down matching lessons as the user types (`LessonSearch` in `web/`, `GET /api/search`, `search_lessons` in `app/progress.py`): title and card text of the latest published version only. A lesson opened from it steps back to the results (`state={{ from: "search" }}`, as topic pages pass `"topic"`).
- **Reported problems (SCRUM-82, SCRUM-83).** Learners flag a card from the flag in the lesson's top bar (`cardActions` on `LessonDeck`); `lesson_reports` keeps the lesson, version, card id, reason and note. Admins see them at `/reports` in `admin/`, never with the reporter, and mark them Fixed or Dismissed (kept). Rules in `api/app/reports.py`.
- **Media** (images, audio) is uploaded once, stored in Postgres (`media_assets`) and served publicly at `/api/media/{id}`; lessons refer to it by id. Images become WebP at most 1600px wide.
- Open decisions and the defaults chosen are in `docs/decisions.md`. Don't change them silently; flag it.
