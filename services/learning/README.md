# Learning

Everything a learner does: opening and running through lessons, completions and best scores, the home page circles and topic pages, search, reviewing mistakes, the aptitude quiz and its exemptions, and the lesson insights administrators see. It never calls another service: what it needs to know about topics, lessons, questions and learners arrives as events and is kept in its own read models.

Learning publishes no events, so it has no outbox or relay.

## Owns

Database `learning` (compose `learning-db`, host port 5435; tests use `learning_test`).

Its own data, written by learners' requests:

| Table                                | What                                                             |
| ------------------------------------ | ---------------------------------------------------------------- |
| `lesson_attempts`, `attempt_answers` | every run through a deck, and the first answer to each question  |
| `lesson_completions`                 | one row per learner per lesson: completion and the best score    |
| `aptitude_attempts`                  | the one completed quiz per learner, with a copy of each question |
| `topic_exemptions`                   | the level the quiz gave each topic (0 to 5)                      |

Read models, written only by the consumer (`app/consumers.py`):

| Table               | Filled from                                      | Guard                                    |
| ------------------- | ------------------------------------------------ | ---------------------------------------- |
| `learnable_topics`  | `content.topic.changed`, `content.topic.deleted` | version; `deleted` tombstone             |
| `learnable_lessons` | `content.lesson.changed`                         | version                                  |
| `lesson_decks`      | `content.lesson_version.published`               | insert if absent (versions never change) |
| `quiz_questions`    | `content.aptitude_question.changed`              | version                                  |
| `quiz_bank`         | `content.aptitude_bank.changed`                  | revision; one row                        |
| `learners`          | `identity.user.registered` (role `user`)         | insert if absent; never for an erased id |
| `erased_learners`   | `identity.user.deleted`                          | the erasure tombstone, kept for good     |

## API

Swagger: http://localhost:8003/docs (direct; a request without the gateway's key gets 401).

| Paths                                                                                                        | Who     | What                                                  |
| ------------------------------------------------------------------------------------------------------------ | ------- | ----------------------------------------------------- |
| `/api/progress`, `/api/topics/{id}`, `/api/search`                                                           | learner | circles and overall figure, a topic's lessons, search |
| `/api/lessons/{id}`, `/api/lessons/{id}/attempts`, `/api/attempts/{id}/answers`, `/api/attempts/{id}/finish` | learner | running a lesson                                      |
| `/api/review`                                                                                                | learner | questions answered wrongly                            |
| `/api/aptitude/{start,next,submit,skip,result}`                                                              | learner | the aptitude test                                     |
| `/api/admin/lessons/{id}/insights`                                                                           | admin   | lesson insights (SCRUM-84)                            |
| `/health/live`, `/health/ready`                                                                              |         | container health                                      |

## Events

Published: none. Consumed (queue `learning.events`, bound to `identity.user.*` and `content.#`): every `content.*` event and `identity.user.registered` / `identity.user.deleted`. Each handler is idempotent: a duplicate or an older version changes nothing.

`identity.user.deleted` erases the learner (`app/erasure.py`): tombstone the id, then delete attempts, completions, the quiz and exemptions, in one transaction under the learner's advisory lock. The two writes that create a learner's first rows (starting an attempt, submitting the quiz) take the same lock and check the tombstone, so a request in flight cannot recreate them.

## Code

`app/progress.py` circles, topic pages, the suggestion, level reached and search; `app/learning.py` running a lesson and scoring; `app/exemptions.py` and `app/aptitude.py` the quiz and exemptions; `app/review.py`; `app/insights.py`; `app/consumers.py` and `app/read_models.py` the read models; `app/erasure.py` account deletion.

## Commands

`docker compose exec learning python -m app.cli ...`:

| Command                                   | What                                                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `wait-for-read-models [--timeout S]`      | wait until the Identity and Content seeds have arrived (exit 1 on timeout)                                                           |
| `seed`                                    | the Newcomer's completions and the personas' quiz results; safe to repeat                                                            |
| `demo-activity --run-nonce X [--count N]` | lesson runs for Identity's demo learners (`scripts/seed-all.sh --demo`)                                                              |
| `reset-read-models [--yes]`               | empty the read models (not `erased_learners`); then run Content's `republish-catalog` and Identity's `republish-learners` to rebuild |
| `health`                                  | check the database and the broker                                                                                                    |

## Tests

```bash
docker compose up -d learning-db rabbitmq          # the over-the-wire consumer test skips without RabbitMQ
cd services/learning
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                         # learning_test on :5435
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

Tests fill the read models only through the real consumer, from stand-ins for Content and Identity (`tests/support/`) whose envelopes are validated against `contracts/events`.
