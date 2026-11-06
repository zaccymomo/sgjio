# Contracts

The only things the services share. A service never imports another's code; it agrees with the others on what is written here: the events on the broker, the headers the gateway sets, and the error shape every API answers with.

- `events/envelope.schema.json`: the envelope every event travels in
- `events/<type>.schema.json`: one JSON Schema (draft 2020-12) per event, envelope plus `data`
- `events/examples/<type>.json`: one valid example per event
- `validate.py`: checks every schema and example, and that the schemas really are strict (151 checks)

```bash
uv venv -p 3.11 contracts/.venv && uv pip install -p contracts/.venv/bin/python -r contracts/requirements.txt
contracts/.venv/bin/python contracts/validate.py                 # all schemas and examples
contracts/.venv/bin/python contracts/validate.py out/*.json      # plus events your tests wrote out
```

## Envelope

Every message on the `sgjio.events` exchange is one JSON object:

```json
{
  "event_id": "uuid",
  "type": "content.lesson.changed",
  "schema_version": 1,
  "occurred_at": "2026-11-10T08:00:00Z",
  "producer": "content",
  "aggregate_type": "lesson",
  "aggregate_id": "uuid",
  "aggregate_version": 7,
  "correlation_id": "4f9d2c1b...",
  "data": {}
}
```

| Field                            | Meaning                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| `event_id`                       | UUID, unique per event. Notification's inbox key.                                          |
| `type`                           | `<producer>.<aggregate>.<fact>`. Also the AMQP routing key and the AMQP `type` property.   |
| `schema_version`                 | `1` for every event today. A breaking change to `data` is a new version (CONTRIBUTING.md). |
| `occurred_at`                    | When the change was committed, RFC 3339 with a zone (the platform writes UTC `Z`).         |
| `producer`                       | `identity` or `content` (Learning and Notification publish nothing yet).                   |
| `aggregate_type`, `aggregate_id` | What changed. Fixed per event; see the catalogue.                                          |
| `aggregate_version`              | The aggregate's own version after the change. See [Ordering](#ordering-and-idempotency).   |
| `correlation_id`                 | The `X-Request-ID` of the request that caused it, or `null` (command line, seed).          |
| `data`                           | The event's payload, defined by its schema.                                                |

AMQP properties mirror it: `message_id` = `event_id`, `type` = `type`, `app_id` = `producer`, `content_type` = `application/json`, persistent delivery, header `x-correlation-id`. The platform's relay (`templates/platform/app/platform/outbox.py`) builds all of this from the outbox row; producers only call `emit(...)`.

Consumers check two fields before any handler runs (`templates/platform/app/platform/consumer.py`), and a message that fails goes straight to the dead-letter queue: `producer` must equal the type's first segment, and `schema_version` must be one the consumer accepts (`schema_versions`, default 1).

**Strict for producers, tolerant for consumers.** The schemas forbid unknown fields, so a producer can't drift from the contract without a schema change (and `validate.py` fails). Consumers must ignore fields they don't know, so adding a field is never breaking. Removing or renaming one, or changing its meaning, is.

## Event catalogue

| Event                               | Producer → consumers         | Aggregate (id, version)                                                                         | `data`                                                                                                                                                                                                                       | Emitted when                                                                                                                                                                                         |
| ----------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `identity.user.registered`          | Identity → Learning          | user (user_id, always 1)                                                                        | user_id, role (`user`/`admin`), user_type (`newcomer`/`singaporean`; null exactly for admins), registered_at                                                                                                                 | register, Google sign-up, admin invite, `create-admin`, seed, `seed-demo-learners`, `republish-learners`                                                                                             |
| `identity.user.deleted`             | Identity → Learning, Content | user (user_id, always 2)                                                                        | user_id, deleted_at                                                                                                                                                                                                          | delete-account, `clear-demo-learners`; same transaction as the delete                                                                                                                                |
| `identity.password_reset.requested` | Identity → Notification      | user (user_id, always 1)                                                                        | user_id, email, name, audience (`app`/`admin`), method (`password`/`google`); password: link, expires_in_minutes; google: sign_in_url                                                                                        | forgot-password for an account that exists (and is an admin, for `admin`)                                                                                                                            |
| `identity.admin.invitation_issued`  | Identity → Notification      | user (admin_id, always 1)                                                                       | admin_id, email, name, inviter_name (null only for `forgot_password`), link, expires_in_hours, trigger (`invited`/`resent`/`restored`/`forgot_password`)                                                                     | invite, resend, restore, forgot-password by an admin who hasn't accepted yet                                                                                                                         |
| `identity.admin.removed`            | Identity → Notification      | user (admin_id, always 1)                                                                       | admin_id, email, name, remover_name                                                                                                                                                                                          | remove admin                                                                                                                                                                                         |
| `content.topic.changed`             | Content → Learning           | topic (topic_id, `topics.version`)                                                              | topic_id, name, description, position, is_archived                                                                                                                                                                           | create, rename, describe, archive, restore, reorder (each moved topic), import, seed, republish                                                                                                      |
| `content.topic.deleted`             | Content → Learning           | topic (topic_id, version + 1)                                                                   | topic_id                                                                                                                                                                                                                     | delete (only a topic that never had lessons or questions)                                                                                                                                            |
| `content.lesson.changed`            | Content → Learning           | lesson (lesson_id, `lessons.version`)                                                           | lesson_id, key, topic_id, level, position, created_at, display_title, publication_state (`published`/`withdrawn`), learner_visible, first_published_at, published_at, withdrawn_at, latest_version_id, latest_version_number | only lessons published at least once: publish, withdraw, restore, draft title change, topic move, reorder, archive/restore of its topic, republish                                                   |
| `content.lesson_version.published`  | Content → Learning           | lesson_version (version_id, always 1)                                                           | version_id, lesson_id, number, title, summary, published_at, doc, questions[{card_id, question_id, scored, correct_option_id}], reading_seconds, scored_questions, assets{id: AssetOut}, cards_plain_text[]                  | a publish that creates a version (written before `lesson.changed`), republish                                                                                                                        |
| `content.aptitude_question.changed` | Content → Learning           | aptitude_question (question_id, `aptitude_questions.version`)                                   | question_id, topic_id, level, prompt, options[{id, text}], correct_option_id, is_active, seed_key                                                                                                                            | create, update (incl. topic move), activate, deactivate, seed, republish                                                                                                                             |
| `content.aptitude_bank.changed`     | Content → Learning           | aptitude_bank (fixed id `d69a3dc8-6470-5484-a156-901c82a34f06`, `aptitude_bank_state.revision`) | ready, topics[{topic_id, ready}] in quiz order (position, then name)                                                                                                                                                         | every change that can alter `aptitude.bank()`: any question change, and topic archive, restore, rename and reorder (one bank event per transaction, after the `topic.changed` ones), seed, republish |

Each schema's `description` says the same in more detail, field by field. What the payloads were built from:

- **Grading and the learner deck.** `doc` is the stored version document unchanged (every field present, as `lesson_doc.dump` writes it), so Learning can build `LearnerCardOut` (option ids and text only, shuffled where `shuffle` is true) and return the full doc in admin insights exactly as today. `questions` carries `lesson_doc.is_scored` and `lesson_doc.correct_option` per question, so Learning never needs `lesson_doc.py`. This differs from the detailed plan (which annotated the doc in place) so that the insights `doc` stays byte-identical.
- **Media.** `assets` is exactly today's `AssetOut` per referenced file (`media.assets_for`), and `reading_seconds` already includes audio length, so Learning never needs `media.py`.
- **Search.** `cards_plain_text[i]` is `lesson_doc.plain_text(cards[i].text)`, so the first-matching-card snippet works unchanged.
- **Quiz topic order.** `aptitude_bank.changed.topics` is the order the quiz asks topics in (today's `_assessed_topics`: `Topic.position`, then `Topic.name`). Learning uses it exactly as given and never re-sorts it from its topic read model. Because a reorder or a rename (name breaks ties between equal positions) can change that order without touching a question, Content bumps `aptitude_bank_state.revision` and emits the bank in the same transaction as `reorder_topics` and a rename, as it does for question changes and archive/restore.
- **Ordering of lessons.** Learning sorts by level, position, then `created_at`, so `lesson.changed` carries `created_at` (not in the detailed plan).
- **Emails.** Each Identity event carries every argument its template takes (`mailer/templates.py`): `password_reset_email(to, name, link, minutes, for_admin=audience=="admin")`, `google_account_email(to, name, link=sign_in_url)`, `admin_invite_email(to, name, inviter=inviter_name, link, hours=expires_in_hours, restored=trigger=="restored")`, `admin_removed_email(to, name, remover=remover_name)`. One-time links and addresses therefore cross the broker: it is internal only, events are never logged at INFO, and `notification.events.dlq` has a 1-hour TTL. In Identity's outbox these three event types are deleted as soon as the broker confirms them (`discard_after_publish`), not kept for 7 days like the rest, so reset tokens stay stored only as hashes.

## Ordering and idempotency

Delivery is **at least once** and **unordered** (a requeued message can come back after later ones). Every consumer is written so that duplicates and stale messages change nothing:

- **Version guard.** A read model row keeps the `aggregate_version` it was built from. A consumer applies an event only when `aggregate_version` is greater than the stored one (`INSERT ... ON CONFLICT DO UPDATE ... WHERE stored.version < excluded.version`), and ignores one that is less than or equal. Content bumps the version in the same transaction (and with the same row lock) as the change, so versions follow commit order.
- **Insert if absent** for immutable facts: `lesson_version.published` (versions never change) and `user.registered` (refused for an id in `erased_learners`).
- **Tombstones.** `topic.deleted` sets `deleted = true` and bumps the version, so a stale `topic.changed` can't bring it back. `user.deleted` adds the id to `erased_learners` for good.
- **Deletes and nulling by id** (`user.deleted` in Learning and Content) are naturally repeatable.
- **Inbox.** Sending email is not idempotent, so Notification records each handled `event_id` in `processed_events` and skips ones it has seen (the platform consumer's `dedupe` hook). A crash between sending and recording sends a duplicate; it never loses one.
- **Identity's versions.** Users have no version column: `user.registered` is always 1 and `user.deleted` always 2, which is all Learning needs (erasure wins). The email events are always 1; Notification orders nothing.
- The outbox `id` is only the relay's cursor and is never part of a contract.

## Broker topology

| Thing                                             | Declared by                                                         | Notes                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `sgjio.events` (topic, durable)                   | `infra/rabbitmq/definitions.json`, and idempotently by the platform | Routing key = event `type`.                                                                                                                                                                                                                                                                               |
| `sgjio.dlx` (direct, durable)                     | same                                                                | Routing key = the queue the message died in.                                                                                                                                                                                                                                                              |
| `sgjio.unrouted` (fanout exchange + quorum queue) | definitions only                                                    | Alternate exchange of `sgjio.events` (a policy): an event published before any consumer queue was bound is kept here instead of dropped. Recover with the producer's `republish-*` command. A second policy caps it at 10,000 messages (oldest dropped) and 7 days, so copies nobody reads don't pile up. |
| `<consumer>.events` (quorum)                      | the consumer, in code (`Consumer.declare`)                          | `x-dead-letter-exchange: sgjio.dlx`, `x-dead-letter-routing-key: <queue>`, `x-delivery-limit: 20` (a backstop only; see below).                                                                                                                                                                           |
| `<consumer>.events.dlq` (quorum)                  | the consumer, in code                                               | Bound to `sgjio.dlx` with key `<consumer>.events`. Notification sets a 1-hour message TTL.                                                                                                                                                                                                                |

Bindings, owned by each consumer:

| Queue                 | Binds                                                   |
| --------------------- | ------------------------------------------------------- |
| `learning.events`     | `identity.user.*`, `content.#`                          |
| `content.events`      | `identity.user.deleted`                                 |
| `notification.events` | `identity.password_reset.requested`, `identity.admin.*` |

A handler that raises is retried after 0.5, 1, 2 and 4 seconds; on the 5th failure the message moves to the DLQ. The platform consumer counts these failures itself, in memory per `event_id` (RabbitMQ 4 doesn't count a `nack` with requeue towards `x-delivery-limit`, and `x-acquired-count` also rises during an outage). A failure while the service's database is unreachable is not counted: the consumer holds the message, checks `SELECT 1` with backoff until Postgres answers, then retries it, so a database restart never parks events. The queue's `x-delivery-limit: 20` only catches a consumer that dies mid-message. A message that isn't JSON goes to the DLQ at once; an event type the consumer has no handler for is acknowledged and dropped. Replay parked messages from the management UI (http://localhost:15672, `sgjio`/`sgjio`) or by republishing the aggregate.

Changing a queue's arguments later fails with `PRECONDITION_FAILED` until the queue is deleted; in development, delete it in the management UI and restart the service.

## Auth contract (gateway ↔ Identity ↔ services)

This replaces the detailed plan's JWT (sections 4.5 and 5.1): the gateway asks Identity on **every** protected request, with no cache.

1. For a protected route (see `services/gateway/templates/gateway.conf.template`) nginx makes a subrequest, without the body, to Identity: `GET /internal/auth/app` or `GET /internal/auth/admin` (the scope comes from the path: `/api/admin/*` is admin, the rest is app). It forwards only `Cookie`, `X-Request-ID`, `X-Forwarded-For` (the client address as nginx sees it) and `X-Gateway-Key`. A request that carries no cookie for that scope at all (`sgjio_session` or `sgjio_admin_session` absent or empty) is signed out for certain: nginx answers the 401 below at once without asking Identity, so a visitor still gets sign-in rather than 503 while Identity is down.
2. Identity reads that scope's cookie (`sgjio_session` or `sgjio_admin_session`) and runs today's session checks (expiry, sliding refresh, removed accounts, `is_admin` for admin). It answers:
   - **200** with headers
     - `X-User-Id`: the user's UUID
     - `X-User-Scope`: `app` or `admin`
     - `X-User-Role`: `user` or `admin`
     - `X-User-Type`: `newcomer` or `singaporean`; empty for administrators
     - `X-Profile-Completed`: `true` or `false` (the user has a profile row; aptitude eligibility)
     - `Set-Cookie`, when it refreshed the session cookie. nginx relays it to the browser.
   - **401** otherwise (no body needed). Identity may check `X-Gateway-Key` and answer 401 without it.
3. nginx answers the 401 itself with exactly `{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}`. If Identity can't be reached or takes over 2 s, it answers **503** `service_unavailable`.
4. On success nginx forwards the request with `X-User-Id`, `X-User-Scope`, `X-User-Role`, `X-User-Type`, `X-Profile-Completed` taken from Identity's answer (any copies the client sent are replaced; empty values are not sent), plus `X-Gateway-Key: $GATEWAY_KEY`, `X-Request-ID`, and `X-Forwarded-For`/`X-Real-IP` set to the client address.
5. Content and Learning protect routes with `Depends(require_principal("app"))` or `require_principal("admin")` from their platform copy. It checks `X-Gateway-Key` against the `GATEWAY_KEY` env var (constant-time; an empty key refuses everything), that `X-User-Scope` is the scope asked for, and for admin that `X-User-Role` is `admin`, and returns `Principal(user_id, scope, role, user_type, profile_completed)`. Anything else is 401 with the body above.
6. **Identity's own routes** (`/api/auth/*`, `/api/admin/auth/*`, `/api/profile*`, `/api/intro/*`, `/api/admin/admins*`, `/api/admin/ping`) are passed straight through with no subrequest; Identity checks cookies in-process as today. Client `X-User-*` headers are stripped there too.
7. `/api/media/*` is public (no subrequest). `/internal/*` is never routed by the gateway.

## Errors

Every service answers errors as the monolith did, so the front ends' `ApiError` keeps working:

- A broken rule: `{"detail": {"code": "...", "message": "...", ...extra, "field"?: "..."}}` with the rule's status. The platform's `Problem` produces it (`errors.py`), keys in that order.
- Request validation: FastAPI's default 422 body, `{"detail": [{"type", "loc", "msg", "input", ...}]}`, unchanged.
- Signed out: 401 `{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}`, byte for byte.
- An unhandled exception: 500 `text/plain` "Internal Server Error", as the monolith answered, now with `X-Request-ID` and a logged traceback carrying the same id (`CorrelationIdMiddleware`).
- The service's own database unreachable (SQLAlchemy `OperationalError` or `InterfaceError`: connection refused or dropped, or a transient failure such as a deadlock): 503 with `Retry-After: 5` and the same `service_unavailable` body as the gateway's (table below), logged as a warning with the request id. The monolith answered 500 here; this is a deliberate change so the front end says "try again in a moment" whether a whole service or only its database is down.
- Produced by the gateway itself (never replacing a service's own response):

| Status                                 | Body                                                                                                                  |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 401                                    | `{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}`                                         |
| 404 (no route)                         | `{"detail":"Not Found"}`                                                                                              |
| 413 on `/api/admin/media` (over 20 MB) | `{"detail":{"code":"media_too_large","message":"That file is too large. The limit is 15 MB."}}`                       |
| 413 elsewhere (over 10 MB)             | `{"detail":{"code":"payload_too_large","message":"That request is too large. The limit is 10 MB."}}`                  |
| 503 (service or Identity unreachable)  | `{"detail":{"code":"service_unavailable","message":"SGJio is unavailable right now. Please try again in a moment."}}` |
| 504 (service too slow)                 | `{"detail":{"code":"gateway_timeout","message":"SGJio took too long to answer. Please try again."}}`                  |

## Seed and demo ids

Seed users get deterministic ids, so Learning's seed can refer to them without asking Identity: `uuid5(NAMESPACE_URL, "sgjio:user:" + email)` (email lower-case). Demo learners add a run nonce, `uuid5(NAMESPACE_URL, "sgjio:user:" + email + ":" + nonce)`, so a re-run never collides with the erased ids of the previous run. Content's seed data is found by natural keys: lessons by `key`, topics by name, questions by `seed_key`.
