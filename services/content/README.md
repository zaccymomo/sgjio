# Content

Authoring and publishing: topics, lessons (drafts and numbered published versions), AI-drafted lessons, images and audio, problems learners report on a card, and the aptitude question bank. Administrators work here through the admin portal; learners only touch it to fetch media and to report a problem. Everything learners read comes from Learning's copy, which Content keeps up to date with events.

## Owns

Database `content` (compose `content-db`, host port 5434; tests use `content_test`).

| Table                 | What                                                                                                                                                                                                |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `topics`              | name, description, position, `archived_at`, `assessed_at` (ever had an aptitude question), `version`                                                                                                |
| `lessons`             | the draft deck, status draft/published/withdrawn, topic, position, level, `version`; `origin` (`authored` or `ai`) and, for an AI draft, `ai_reviewed_at` / `ai_reviewed_by` from its first publish |
| `lesson_versions`     | each publish, numbered per lesson: what learners see                                                                                                                                                |
| `media_assets`        | uploaded images (WebP, at most 1600 px wide) and audio, stored in Postgres                                                                                                                          |
| `lesson_reports`      | reported problems; the reporter is never shown to administrators                                                                                                                                    |
| `aptitude_questions`  | the quiz bank, Level 1 to 5, deactivated rather than deleted, `version`                                                                                                                             |
| `aptitude_bank_state` | one row: the bank's `revision`                                                                                                                                                                      |
| `generation_jobs`     | administrators' requests for an AI draft: topic, level, cards, notes, status, the Draft it became                                                                                                   |
| `erased_users`        | ids of deleted accounts (tombstone, no personal data), so a report in flight can't record one again                                                                                                 |
| `outbox`              | events waiting for the relay                                                                                                                                                                        |

User ids (`published_by`, `created_by`, `reporter_id`, `resolved_by`, `requested_by`, `ai_reviewed_by`) are plain UUIDs from Identity, with no foreign key.

## API

Swagger: http://localhost:8002/docs (direct; a request without the gateway's key gets 401).

| Paths                                                 | Who     | What                                                                                      |
| ----------------------------------------------------- | ------- | ----------------------------------------------------------------------------------------- |
| `/api/admin/topics*`                                  | admin   | list, create, edit, reorder, archive, restore, delete                                     |
| `/api/admin/lessons*` (not `/insights`)               | admin   | list, create, edit the draft, reorder, publish, discard, withdraw, restore, delete        |
| `/api/admin/lessons/generate`                         | admin   | ask for an AI draft (202)                                                                 |
| `/api/admin/generation`, `/api/admin/generation/{id}` | admin   | drafts left today; a request's progress, and the Draft once done                          |
| `/api/admin/media`                                    | admin   | upload (the gateway allows 20 MB; Content's limits are 15 MB images, 10 MB / 120 s audio) |
| `/api/admin/reports*`                                 | admin   | reported problems, mark fixed or dismissed                                                |
| `/api/admin/aptitude-questions*`                      | admin   | the question bank and its readiness                                                       |
| `/api/lessons/{id}/reports`                           | learner | report a problem on a card                                                                |
| `/api/media/{id}`                                     | public  | images and audio, with ranges and ETags                                                   |
| `/health/live`, `/health/ready`                       |         | container health                                                                          |

## Events

Published (outbox, same transaction as the change; each aggregate's `version` rises with every change and travels as `aggregate_version`):

| Event                                 | When                                                                     |
| ------------------------------------- | ------------------------------------------------------------------------ |
| `content.topic.changed`               | create, rename, describe, archive, restore, reorder, seed                |
| `content.topic.deleted`               | delete (only a topic that never had lessons or questions)                |
| `content.lesson.changed`              | any change learners can see to a lesson published at least once          |
| `content.lesson_version.published`    | a publish that makes a version (sent before the `lesson.changed`)        |
| `content.aptitude_question.changed`   | create, edit, activate, deactivate                                       |
| `content.aptitude_bank.changed`       | once per transaction that can change the quiz's readiness or topic order |
| `content.lesson_generation.requested` | an administrator asks for an AI draft (with the `generation_jobs` row)   |

All but the last consumed by Learning; `content.lesson_generation.requested` is consumed by Generation, and carries the job's id as `request_id`, the brief (topic, level, length, the notes) and the topic's published lessons, never who asked. `app/projections.py` works out what Learning needs (who may see a lesson, which option is right, reading time, assets, plain text for search, bank readiness), so Learning never needs Content's rules.

Consumed (queue `content.events`, bound to `identity.user.deleted` and `generation.lesson.*`):

- `identity.user.deleted`, which tombstones the id in `erased_users` and nulls it on reports, versions, media, generation jobs and `ai_reviewed_by` (`app/erasure.py`; repeatable, so no inbox). Under the user's advisory lock, so a report already in flight either commits first and is anonymised, or is refused.
- `generation.lesson.progress`, `generated` and `failed` (`app/generation.py`), applied only to Content's own requests (`requester` is `content`) that are still waiting, and only when newer than the job's `progress_version`. `generated` creates the Draft through the usual create path (`lessons.add_draft`, Content's own ids, no media) with `origin = ai`; if that is refused (the topic was archived or deleted meanwhile), the job fails as `invalid_output`.

## AI drafts

`app/generation.py`; the HTTP shapes are in docs/ai-lessons-api.md. "Generate draft" saves a `generation_jobs` row and the event in one transaction and returns 202; the dialog polls `GET /api/admin/generation/{id}` until it is `done` (open the editor at `lesson_id`) or `failed`. A job still waiting after `GENERATION_TIMEOUT_SECONDS` is marked failed (`timeout`) when it is next read; there is no scheduler. Failed jobs don't count toward the daily limit.

Publishing an AI draft for the first time needs `{"reviewed": true}` in the publish body (the editor's "I have reviewed every card"); without it, 409 `review_required`. That publish records `ai_reviewed_at` and `ai_reviewed_by`; later publishes don't ask again.

| Setting                        | Default | What                                                                                                                     |
| ------------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------ |
| `GENERATION_ADMIN_DAILY_LIMIT` | `20`    | requests per administrator per Singapore day                                                                             |
| `GENERATION_TIMEOUT_SECONDS`   | `90`    | seconds before a waiting request is shown as failed; `docker-compose.yml` sets 180, longer than the worker's model calls |

## Code

`app/lesson_doc.py` what a lesson is and what blocks publishing; `app/lessons.py` drafts, versions, publishing, ordering; `app/topics.py` topics; `app/media.py` uploads; `app/reports.py` reported problems; `app/aptitude.py` the bank; `app/generation.py` AI drafts; `app/events.py` and `app/projections.py` the events; `app/consumers.py` the consumer; `app/erasure.py` forgetting a deleted account.

## Commands

`docker compose exec content python -m app.cli ...` (lesson files are mounted at `/srv/content`):

| Command                               | What                                                                                               |
| ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `seed`                                | the six topics, the lessons in `content/lessons` (published) and the aptitude bank; safe to repeat |
| `import-lessons [folder] [--publish]` | load lesson files (`content/README.md`)                                                            |
| `prune-media`                         | delete images and audio no lesson uses                                                             |
| `republish-catalog`                   | publish current-state events for everything again (rebuilds Learning's read models)                |
| `health`                              | check the database and the broker                                                                  |

## Tests

```bash
docker compose up -d content-db rabbitmq
cd services/content
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                         # 390 tests, content_test on :5434
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

After every test, each event it wrote is validated against `contracts/events` and each aggregate's versions are checked to rise in commit order.
