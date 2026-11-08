# Architecture decision records

One page each: the context, what we decided, and what it costs. They describe the code as built (merged in #21); [../diagrams.md](../diagrams.md) has the pictures.

| ADR                                                   | Decision                                                                                        |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| [0001](0001-service-boundaries.md)                    | Four services (Identity, Content, Learning, Notification), split by who owns the data           |
| [0002](0002-database-per-service.md)                  | A database per service; ids across services are plain UUIDs                                     |
| [0003](0003-rabbitmq-transactional-outbox.md)         | RabbitMQ events, written through a transactional outbox                                         |
| [0004](0004-idempotent-consumers-version-ordering.md) | Idempotent consumers, ordered by the aggregate's version                                        |
| [0005](0005-gateway-forward-auth.md)                  | Gateway forward auth: nginx asks Identity on every protected request and passes trusted headers |
| [0006](0006-copied-platform-code.md)                  | Plumbing copied into each service from `templates/platform`, kept identical by CI               |
| [0007](0007-read-models-in-learning.md)               | Learning keeps read models of content and learners                                              |
| [0008](0008-account-deletion-saga.md)                 | Account deletion as an event-driven saga                                                        |
| [0009](0009-failure-isolation.md)                     | Failure isolation: what degrades, how it says so, how it recovers                               |

Product decisions (password rules, session lengths, and so on) stay in [docs/decisions.md](../../decisions.md).
