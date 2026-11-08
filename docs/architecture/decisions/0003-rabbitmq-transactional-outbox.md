# ADR 0003: RabbitMQ events, written through a transactional outbox

**Status:** accepted, built

## Context

When a service changes its data, others must hear about it: a published lesson must reach Learning, a reset request must reach Notification. Publishing straight to a broker after the commit loses the event if the process dies in between, or if the broker is down; publishing before the commit can announce a change that then rolls back.

## Decision

- **RabbitMQ 4.4**, one durable topic exchange `sgjio.events`. The routing key is the event type (`<producer>.<aggregate>.<fact>`, for example `content.lesson.changed`). Each consumer declares its own quorum queue (`learning.events`, `content.events`, `notification.events`) with its bindings, and a dead-letter queue. An alternate exchange `sgjio.unrouted` keeps events published before any queue was bound.
- **Transactional outbox.** A producer (Identity, Content) never talks to the broker in a request. It calls `emit(...)`, which inserts a row in its own `outbox` table **in the same transaction** as the change. The event is committed with the change, or not at all.
- **Relay.** A background thread in each producer polls the outbox every 0.25 s, publishes unpublished rows in id order with **publisher confirms**, then marks them published (and prunes rows older than 7 days). If the broker is down it retries with backoff capped at 5 s. Event types listed in `discard_after_publish` are deleted as soon as the broker confirms them instead: Identity passes its three email events, whose payloads hold a one-time link or an email address and name. Reset tokens are stored hashed, and a raw link kept for 7 days would undo that.
- **Contracts.** Every event's envelope and payload is a JSON Schema in `contracts/events/`. Producers' tests validate every event they write; `contracts/validate.py` runs in CI.
- **Consumers check the envelope** before a handler runs (`app/platform/consumer.py`). The `producer` must be the type's first segment, so only `identity` may send `identity.*`. The `schema_version` must be one the handler accepts (`schema_versions`, default 1). A message that fails either check goes straight to the dead-letter queue.

## Consequences

- Requests succeed while RabbitMQ is down; events wait in the outbox and go out when it is back (resilience drill `test_broker_outage_delays_but_never_loses_a_publish`).
- Delivery is **at least once**: a crash between publishing and marking publishes the row again. Consumers must be idempotent (ADR 0004).
- Changes reach other services after a short delay, usually under a second. This is a declared behaviour change (admin edits reach learners slightly later).
- The relay runs inside the API process rather than a separate worker container, to keep the number of containers down.
- **Trust on the broker.** All four services connect as one RabbitMQ user (`sgjio`, administrator). Least-privilege users per service, with topic permissions limiting what each may publish, were deferred (build plan). Until then, the consumer's producer check stops one service's bug from publishing another's events and having them acted on. It does not stop a compromised service, which could forge the `producer` field. Anyone who can publish to the broker can, for example, send `identity.user.deleted` and have a learner's data erased. The broker is reachable only from the services' `<name>-net` networks and on `127.0.0.1`.
- Alternatives: Kafka (more than a four-service school project needs, and harder to run locally); HTTP calls between services (couples availability: Content would fail when Learning is down); Postgres LISTEN/NOTIFY (only works inside one database).
