# ADR 0009: Failure isolation and graceful degradation

**Status:** accepted, built; checked by the resilience drills (`scripts/e2e.sh --resilience`)

## Context

In the monolith, anything down meant everything down. With a gateway, four services (five since [ADR 0010](0010-generation-worker.md)), a broker and a database for each service, something will be down sometimes. The aim: one component failing takes away only the features that truly need it, says so clearly, and recovers by itself.

## Decision

- **Asynchronous by default.** Only the gateway's session check is synchronous (ADR 0005). Everything else crosses services as events (ADR 0003), so a service being down delays its consumers' updates rather than failing anyone's request.
- **The gateway resolves services per request** (Docker DNS, 10 s validity), so it starts and keeps routing while a service is down. A service it cannot reach answers **503 `service_unavailable` with `Retry-After: 5`**; one that connects but is too slow (15 s) answers 504 `gateway_timeout`. The auth check gives up after 2 s.
- **A service whose own database is down** answers the same 503 (the platform's error handler), not a bare 500, and recovers when Postgres is back.
- **Consumers wait out outages.** A message that fails while the database (or, for Notification, the mail server) is unreachable is held and retried without counting, so outages never dead-letter good events. The relay and consumers reconnect to RabbitMQ with backoff capped at 5 s.
- **Health checks** (`/health/ready`: `SELECT 1`) drive `docker compose up --wait`; the gateway depends on services being _started_, not healthy, so it never blocks on one.

## Consequences

What still works with each component down: see the table in [diagrams.md](../diagrams.md#5-what-still-works-when-a-component-is-down). In short: Learning down stops learner pages but not authoring; Content down stops authoring and media but not learning; Identity down stops every signed-in route but not public media or the sign-in page; RabbitMQ down only delays replication; Notification or the mail server down only delays email; Generation or the AI model down only stops new generated lessons and AI drafts.

- The front ends show the 503's message ("SGJio is unavailable right now. Please try again in a moment.") or their existing "Couldn't load, try again" state, so no front-end change was needed.
- The drills stop real containers, so they are opt-in and not part of CI's e2e job.
- Identity remains a single point of failure for signed-in traffic, the price of immediate sign-out (ADR 0005). Running two Identity replicas behind the gateway would remove it; not needed for this project.
