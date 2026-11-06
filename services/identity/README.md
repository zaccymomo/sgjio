# Identity

Who someone is and whether they are signed in: accounts (learners and administrators), passwords, Google sign-in, sessions for both front ends, lockout, password reset, administrator invites, the profile and the introduction. It also answers the gateway's "who is this?" check on every protected request.

Identity is the only service the gateway calls synchronously. It consumes no events.

## Owns

Database `identity` (compose `identity-db`, host port 5433; tests use `identity_test`).

| Table                   | What                                                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `users`                 | one row per account; `role` user/admin, `user_type` newcomer/singaporean, `google_sub`, `invited_at`, `removed_at`, `intro_finished_at` |
| `profiles`              | interests, languages, neighbourhood (one per user)                                                                                      |
| `auth_sessions`         | sessions per scope (`app`, `admin`), stored as SHA-256 of the cookie                                                                    |
| `password_reset_tokens` | one-time reset and invite links, hashed; reset links last 15 minutes                                                                    |
| `login_attempts`        | sign-in history for lockout and "last sign-in"                                                                                          |
| `admin_events`          | administrators' activity log (invited, joined, removed, restored, ...)                                                                  |
| `outbox`                | events waiting for the relay; the three email events are deleted once published (their links and addresses don't stay)                  |

## API

Swagger: http://localhost:8001/docs (direct, bypassing the gateway). The gateway passes these through without asking for a session first; Identity checks its own cookies.

| Paths                                                         | What                                                                                                                                                                                                     |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/auth/*`                                                 | main app: sign-in, register, google, privacy-notice-version, change-password, delete-account, forgot-password, reset-password/check, reset-password, sign-out, me                                        |
| `/api/admin/auth/*`                                           | admin portal: sign-in, forgot-password, reset-password/check, reset-password, invite/check, invite/accept, sign-out, me                                                                                  |
| `/api/admin/admins*`, `/api/admin/ping`                       | administrators (SCRUM-81)                                                                                                                                                                                |
| `/api/profile`, `/api/profile/options`, `/api/intro/finished` | profile setup and the introduction                                                                                                                                                                       |
| `/internal/auth/app`, `/internal/auth/admin`                  | the gateway's session check (not routed from outside; needs `X-Gateway-Key`). 200 with `X-User-Id`, `X-User-Scope`, `X-User-Role`, `X-User-Type`, `X-Profile-Completed` and the refreshed cookie, or 401 |
| `/health/live`, `/health/ready`                               | container health                                                                                                                                                                                         |

## Events

Published (outbox, same transaction as the change; schemas in `contracts/events/`):

| Event                               | When                                                         | Consumed by       |
| ----------------------------------- | ------------------------------------------------------------ | ----------------- |
| `identity.user.registered`          | register, Google sign-up, admin invite, `create-admin`, seed | Learning          |
| `identity.user.deleted`             | delete-account, `clear-demo-learners`                        | Learning, Content |
| `identity.password_reset.requested` | forgot-password for an account that exists                   | Notification      |
| `identity.admin.invitation_issued`  | invite, resend, restore, forgot-password by an invited admin | Notification      |
| `identity.admin.removed`            | remove an administrator                                      | Notification      |

Consumed: none.

## Code

`app/auth/` sessions, lockout, Google, reset links and the `require_user`/`require_admin` dependencies; `app/admins.py` administrators; `app/routers/internal.py` the gateway check; `app/events.py` every event; `app/platform/` the copied plumbing (`templates/platform`).

## Commands

Run in the container (`docker compose exec identity python -m app.cli ...`) or with the service's `.venv`.

| Command                                            | What                                                                                        |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `seed`                                             | admin, the Newcomer and the aptitude personas, with deterministic ids                       |
| `create-admin --email E [--name N] [--password P]` | first administrator, or recovery                                                            |
| `send-reset --email E [--scope app\|admin]`        | send a reset email (arrives in Mailpit)                                                     |
| `seed-demo-learners [--count N] [--run-nonce X]`   | replace the demo learners; prints the run nonce Learning needs                              |
| `clear-demo-learners`                              | delete the demo learners                                                                    |
| `republish-learners`                               | publish `identity.user.registered` again for every account (rebuilds Learning's `learners`) |
| `health`                                           | check the database and the broker                                                           |

## Tests

```bash
docker compose up -d identity-db rabbitmq          # broker tests skip without RabbitMQ
cd services/identity
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                         # identity_test on :5433, migrations run first
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

Every event a test leaves in the outbox is checked against its schema in `contracts/events`.
