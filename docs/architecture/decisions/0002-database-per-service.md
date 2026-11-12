# ADR 0002: A database per service, no shared tables

**Status:** accepted, built

## Context

A shared database is the easiest way to split a monolith, but then every table is everyone's API: a column rename in one service breaks another, and the services can only be deployed together.

## Decision

- Each service has its own Postgres 16 container and database (`identity-db` :5433, `content-db` :5434, `learning-db` :5435, `notification-db` :5436, and `generation-db` :5438 since [ADR 0010](0010-generation-worker.md)), with its own Alembic history starting from a fresh baseline. Each also has a `<name>_test` database for its tests (`infra/postgres/init-test-db.sh`).
- **No service reads another's tables.** Ids from elsewhere (a user id in Content, a lesson id in Learning) are plain UUIDs with **no foreign key**.
- What a service needs from another arrives as events and is stored in its own tables (ADR 0007), or is not needed at all (Content keeps no copy of users).
- **The network enforces it.** In `docker-compose.yml` each service shares a network only with its own database (`identity-data`, `content-data`, `learning-data`, `notification-data`, which also holds Mailpit, and `generation-data`). Each service's second network, `<name>-net`, joins it to RabbitMQ and (Identity, Content, Learning) the gateway. No two services share a network: no container can open a connection to another service's database, and only the gateway can call a service. The host ports (`127.0.0.1` only) are for development: tests, `psql` and Swagger.
- Seeds use **deterministic ids** (`uuid5("sgjio:user:" + email)` for seed users), so each service can seed its own part without asking the others (`scripts/seed-all.sh`).

## Consequences

- A service can change its schema freely; only its events (`contracts/events/`) are shared, and those are versioned and validated in CI.
- Referential integrity across services is no longer enforced by Postgres. It is kept by events instead: deleting an account sends `identity.user.deleted`, and each service removes or nulls its references (ADR 0008).
- No joins across services. The one place that needed them (learner pages joining progress with published lessons) uses Learning's read models.
- More containers, ports and volumes. Compose names them under project `sgjio-ms`, so they never touch the monolith's.
- A single database with a schema per service was rejected: it keeps one failure point, and nothing stops a cross-schema query.
