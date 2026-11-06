# Notification

Sends the emails: password reset links, "you sign in with Google" replies, administrator invites and removal notices. Identity decides what happened and puts everything the email needs in the event; Notification decides how to say it. It has no HTTP API: it is one worker process (`python -m app.worker`) consuming `notification.events`.

Because email goes out asynchronously, a request such as forgot-password succeeds even while the mail server is down, and the email arrives when it is back.

## Owns

Database `notification` (compose `notification-db`, host port 5436; tests use `notification_test`).

| Table              | What                                                                                                     |
| ------------------ | -------------------------------------------------------------------------------------------------------- |
| `processed_events` | the inbox: the `event_id` of every email sent, kept 30 days, so a redelivered event is not emailed twice |

## Events

Published: none. Consumed (queue `notification.events`):

| Event                               | Email (`app/mailer/templates.py`)                                                       |
| ----------------------------------- | --------------------------------------------------------------------------------------- |
| `identity.password_reset.requested` | `method=password`: reset link (15 minutes); `method=google`: how to sign in with Google |
| `identity.admin.invitation_issued`  | set-password link for a new, re-sent or restored administrator                          |
| `identity.admin.removed`            | your administrator access was removed                                                   |

Delivery is at least once. The consumer skips an `event_id` already in `processed_events`; otherwise it sends, records the id, and commits. A crash between the two can send a duplicate, never lose one. While the database or the mail server is unreachable, a failed message waits and is retried without counting as a failure; any other failure is retried and dead-lettered on the 5th (`notification.events.dlq`, kept one hour because it holds one-time links).

## Code

`app/handlers.py` which email each event sends, and the inbox; `app/consumer.py` the consumer (mail server counted as a dependency); `app/mailer/` SMTP and the templates; `app/worker.py` the process.

## Commands

`docker compose exec notification python -m app.cli ...`:

| Command                  | What                                                                               |
| ------------------------ | ---------------------------------------------------------------------------------- |
| `health`                 | check the database and the broker (the container's healthcheck)                    |
| `prune-inbox [--days N]` | delete inbox rows older than N days (default 30; the worker also does this hourly) |

## Settings

`EMAIL_BACKEND` (`smtp`, `console` or `memory`), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `EMAIL_FROM`. In compose, email goes to Mailpit (http://localhost:8025). For a demo with real email, set the `SMTP_*` values of the `notification` service in `docker-compose.yml` to a provider.

## Tests

```bash
docker compose up -d notification-db rabbitmq mailpit   # broker and Mailpit tests skip without them
cd services/notification
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                              # notification_test on :5436
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

`tests/test_delivery.py` sends through the real broker to Mailpit, including a mail server outage that ends with the email arriving.
