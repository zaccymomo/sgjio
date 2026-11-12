# ADR 0006: Plumbing copied into each service, not shared as a library

**Status:** accepted, built

## Context

Every service needs the same plumbing: the error shape, JSON logging with a correlation id, health endpoints, the gateway principal, the outbox and relay, the consumer base, broker connection. Writing it four times invites drift; importing it from a shared package couples the services (one change ships to all at once, and each image would need the package).

## Decision

- The plumbing lives once in `templates/platform/app/platform/` (about 1,000 lines with comments) with its own tests (34, including integration tests against Postgres and RabbitMQ).
- Each service has an **identical copy** at `services/<name>/app/platform/`. A service never imports from outside its folder, so each image builds from `services/<name>/` alone.
- CI's Platform template job runs the template's tests and fails if any service's copy differs from the template (`diff -r`).
- To change the plumbing: change the template, run its tests, copy it into every service (`cp -r templates/platform/app/platform services/<name>/app/`), run each service's tests.

## Consequences

- Services stay independently buildable; there is no package to version or publish.
- The CI diff makes drift visible at once. Copying a fix to five folders is the cost.
- If a service ever needs to differ, it must stop being an exact copy and say so in its `app/platform/__init__.py`; the CI check would then be relaxed for that service on purpose.
- Alternative rejected: a versioned wheel (`libs/chassis`) in the detailed plan. Correct for a larger organisation; for four services in one repository it adds a release process with no benefit.
