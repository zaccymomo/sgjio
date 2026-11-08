# ADR 0004: Idempotent consumers, ordered by the aggregate's version

**Status:** accepted, built

## Context

RabbitMQ delivers at least once, and not always in order: a message that failed and was requeued can arrive after later ones, and the outbox relay can publish a row twice (ADR 0003). If a consumer applied every message as it came, a duplicate could double-count and a stale "lesson changed" could overwrite a newer one.

## Decision

Every event carries `aggregate_version`, the aggregate's own version **after** the change. Content keeps a `version` column on topics, lessons and aptitude questions (and a `revision` on the bank) and bumps it under the row lock in the same transaction, so versions follow commit order. Consumers then use one of these, per event:

| Technique                                                                                         | Used for                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Version guard**: `INSERT ... ON CONFLICT DO UPDATE ... WHERE stored.version < excluded.version` | Learning's topics, lessons, quiz questions, quiz bank                                                                                                                    |
| **Insert if absent** for facts that never change                                                  | published lesson versions (`lesson_decks`), learners                                                                                                                     |
| **Tombstones**                                                                                    | `topic.deleted` marks the topic deleted at a newer version; `erased_learners` keeps a deleted user's id for good, so a replayed `user.registered` cannot bring them back |
| **Repeatable deletes and updates by id**                                                          | `user.deleted` in Learning and Content                                                                                                                                   |
| **Inbox** (`processed_events`)                                                                    | Notification, because sending an email is not repeatable                                                                                                                 |

Handlers run inside the consumer's transaction and never commit themselves. A handler that raises is retried after 0.5, 1, 2 and 4 s and dead-lettered on the 5th failure. A failure while the service's own database (or, for Notification, the mail server) is unreachable is **not** counted: the consumer waits for it to come back, so an outage never dead-letters good events.

Identity's users have no version column; `user.registered` is always version 1 and `user.deleted` always 2, so deletion always wins.

## Consequences

- Duplicates and stale messages change nothing. Republishing everything (`republish-catalog`, `republish-learners`) is always safe and is how read models are rebuilt.
- Tests check it: Content's tests assert each aggregate's versions rise in commit order; Learning's consumer tests feed duplicates, stale versions and out-of-order events.
- Consumers are tolerant readers: they ignore fields they do not know, so adding a field to an event is never a breaking change.
- Alternative rejected: a single-active-consumer queue for strict ordering. It still needs idempotency for redeliveries, and it serialises everything.
