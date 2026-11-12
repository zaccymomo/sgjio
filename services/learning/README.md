# Learning

Everything a learner does: opening and running through lessons, completions and best scores, the home page circles and topic pages, search, reviewing mistakes, the aptitude quiz and its exemptions, AI-generated lessons on the Practice tab, and the lesson insights administrators see. It never calls another service: what it needs to know about topics, lessons, questions and learners arrives as events and is kept in its own read models.

Learning publishes one event, `learning.lesson_generation.requested`, so it has an outbox, and its relay runs as a background thread beside the consumer.

## Owns

Database `learning` (compose `learning-db`, host port 5435; tests use `learning_test`).

Its own data, written by learners' requests:

| Table                                                   | What                                                                        |
| ------------------------------------------------------- | --------------------------------------------------------------------------- |
| `lesson_attempts`, `attempt_answers`                    | every run through a deck, and the first answer to each question             |
| `lesson_completions`                                    | one row per learner per lesson: completion and the best score               |
| `aptitude_attempts`                                     | the one completed quiz per learner, with a copy of each question            |
| `topic_exemptions`                                      | the level the quiz gave each topic (0 to 5)                                 |
| `generated_lessons`                                     | AI-generated lesson requests and, once ready, the lesson itself             |
| `generated_lesson_attempts`, `generated_lesson_answers` | every run through a generated lesson, and the first answer to each question |
| `generated_lesson_reports`                              | flags on a generated lesson's cards (no admin screen yet)                   |
| `outbox`                                                | events waiting for the relay                                                |

Generated lessons are kept in their own tables on purpose: no circle, overall figure, topic page, suggestion, review or search query reads them, so they never count toward progress (docs/ai-lessons-plan.md D6).

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

| Paths                                                                                                                                                                   | Who     | What                                                    |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------------------------------------------------- |
| `/api/progress`, `/api/topics/{id}`, `/api/search`                                                                                                                      | learner | circles and overall figure, a topic's lessons, search   |
| `/api/lessons/{id}`, `/api/lessons/{id}/attempts`, `/api/attempts/{id}/answers`, `/api/attempts/{id}/finish`                                                            | learner | running a lesson                                        |
| `/api/review`                                                                                                                                                           | learner | questions answered wrongly                              |
| `/api/aptitude/{start,next,submit,skip,result}`                                                                                                                         | learner | the aptitude test                                       |
| `/api/generate/options`, `/api/generate`, `/api/generate/{id}`, `/api/generate/{id}/cancel`                                                                             | learner | asking for an AI-generated lesson and waiting for it    |
| `/api/generated`, `/api/generated/{id}/lesson`, `/api/generated/{id}/attempts`, `/api/generated/attempts/{id}/{answers,finish}`, `/api/generated/{id}/{rating,reports}` | learner | the learner's generated lessons: list, play, rate, flag |
| `/api/admin/lessons/{id}/insights`                                                                                                                                      | admin   | lesson insights (SCRUM-84)                              |
| `/health/live`, `/health/ready`                                                                                                                                         |         | container health                                        |

## Events

Published (outbox, same transaction as the `generated_lessons` row): `learning.lesson_generation.requested`, when a learner asks for a lesson. It carries the request id, the brief and the grounding (lesson text and the learner's mistakes), never a user id, name or email. Consumed by Generation.

Consumed (queue `learning.events`, bound to `identity.user.*`, `content.#` and `generation.lesson.*`): every `content.*` event, `identity.user.registered` / `identity.user.deleted`, and `generation.lesson.progress` / `generated` / `failed`. Each handler is idempotent: a duplicate or an older version changes nothing. Generation's events apply only to a request Learning made (`requester` is `learning`) that is still waiting, and only when newer than the stage it holds, so a result after a cancel or a timeout is ignored.

`identity.user.deleted` erases the learner (`app/erasure.py`): tombstone the id, then delete attempts, completions, the quiz and exemptions, and generated lessons (with their attempts, answers and reports), in one transaction under the learner's advisory lock. The writes that create a learner's first rows (starting an attempt, submitting the quiz, asking for a generated lesson, starting one) take the same lock and check the tombstone, so a request in flight cannot recreate them.

## AI-generated lessons

`app/generated.py`, routes in `app/routers/generated.py`; the HTTP shapes are in docs/ai-lessons-api.md. A request saves a `generated_lessons` row and the event in one transaction and returns 202 at once; the page polls `GET /api/generate/{id}`. A request still waiting after `GENERATION_TIMEOUT_SECONDS` is marked failed (`timeout`) the next time it is read, by a request or the consumer; there is no scheduler. Cancelling only marks the row. Failed and cancelled requests don't count toward the daily limit.

| Setting                      | Default | What                                                                                                                   |
| ---------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------- |
| `GENERATION_DAILY_LIMIT`     | `3`     | requests per learner per Singapore day                                                                                 |
| `GENERATION_TIMEOUT_SECONDS` | `90`    | seconds before a waiting request counts as failed; `docker-compose.yml` sets 180, longer than the worker's model calls |

## Code

`app/progress.py` circles, topic pages, the suggestion, level reached and search; `app/learning.py` running a lesson and scoring; `app/exemptions.py` and `app/aptitude.py` the quiz and exemptions; `app/review.py`; `app/insights.py`; `app/generated.py` AI-generated lessons; `app/consumers.py` and `app/read_models.py` the read models; `app/erasure.py` account deletion.

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
.venv/bin/python -m pytest                         # 294 tests, learning_test on :5435
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

Tests fill the read models only through the real consumer, from stand-ins for Content and Identity (`tests/support/`) whose envelopes are validated against `contracts/events`.
