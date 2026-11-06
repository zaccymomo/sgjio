# Architecture diagrams

The microservices build as it runs in `docker-compose.yml`. GitHub renders the Mermaid blocks; the decisions behind them are in [decisions/](decisions/README.md).

## 1. System context and containers

Requests (synchronous HTTP). Every browser request goes through the gateway; the full routing table is in [services/gateway/README.md](../../services/gateway/README.md).

```mermaid
flowchart LR
    learner([Learner])
    admin([Administrator])
    google[[Google sign-in<br/>via Firebase]]

    subgraph browser [Browser]
        web["web/<br/>main app :5173"]
        adm["admin/<br/>portal :5174"]
    end

    gw["gateway<br/>nginx :8000"]

    subgraph identity [Identity]
        id["identity :8001<br/>accounts, sessions,<br/>admins, profile"]
        iddb[(identity-db)]
    end
    subgraph content [Content]
        ct["content :8002<br/>topics, lessons, media,<br/>reports, question bank"]
        ctdb[(content-db)]
    end
    subgraph learning [Learning]
        ln["learning :8003<br/>lesson runs, progress,<br/>quiz, insights"]
        lndb[(learning-db)]
    end

    learner --> web
    admin --> adm
    web -.- google
    web -- "/api" --> gw
    adm -- "/api" --> gw
    gw -- "sign-in, account,<br/>profile, admins" --> id
    gw -. "session check on every<br/>protected request" .-> id
    gw -- "authoring, media,<br/>reporting a problem" --> ct
    gw -- "learner pages,<br/>lesson insights" --> ln
    id --- iddb
    ct --- ctdb
    ln --- lndb
```

Events (asynchronous, through RabbitMQ). Producers write to their own `outbox` table in the same transaction as the change; a relay thread publishes it.

```mermaid
flowchart LR
    id["identity"]
    ct["content"]
    mq{{"RabbitMQ<br/>topic exchange<br/>sgjio.events"}}
    ln["learning<br/>(read models)"]
    nt["notification<br/>(worker)"]
    ntdb[(notification-db<br/>inbox)]
    mail["Mailpit<br/>:8025"]

    id -- "identity.user.registered<br/>identity.user.deleted<br/>identity.password_reset.requested<br/>identity.admin.*" --> mq
    ct -- "content.topic.*<br/>content.lesson.changed<br/>content.lesson_version.published<br/>content.aptitude_*" --> mq
    mq -- "learning.events:<br/>identity.user.*, content.#" --> ln
    mq -- "content.events:<br/>identity.user.deleted" --> ct
    mq -- "notification.events:<br/>password_reset, admin.*" --> nt
    nt --- ntdb
    nt -- SMTP --> mail
```

Only the gateway is published on all interfaces; every other port is bound to `127.0.0.1` for development. Inside Docker each service has two networks: `<name>-data`, shared only with its own database (Notification's also holds Mailpit), and `<name>-net`, shared with RabbitMQ and, for Identity, Content and Learning, the gateway. No two services share a network, so only the gateway can call them. Content and Learning refuse requests that lack the gateway's `X-Gateway-Key`; the compose default key (`dev-gateway-key`) is public, so set `GATEWAY_KEY` anywhere but a development machine. Learning and Notification publish nothing.

## 2. Publishing a lesson until a learner sees it

```mermaid
sequenceDiagram
    autonumber
    actor A as Administrator
    participant G as Gateway
    participant I as Identity
    participant C as Content
    participant CDB as content-db
    participant MQ as RabbitMQ
    participant L as Learning
    participant LDB as learning-db
    actor U as Learner

    A->>G: POST /api/admin/lessons/{id}/publish (admin cookie)
    G->>I: GET /internal/auth/admin (cookie only)
    I-->>G: 200 X-User-Id, X-User-Role=admin, ...
    G->>C: POST .../publish + X-User-* + X-Gateway-Key
    rect rgba(127,127,127,0.12)
    note over C,CDB: one transaction
    C->>CDB: insert lesson_versions (number n), lesson.version += 1
    C->>CDB: outbox: content.lesson_version.published (v1)
    C->>CDB: outbox: content.lesson.changed (lesson.version)
    end
    C-->>G: 200 lesson
    G-->>A: 200 lesson
    loop relay thread, every 0.25 s
        C->>CDB: SELECT unpublished outbox rows FOR UPDATE SKIP LOCKED
        C->>MQ: publish to sgjio.events (publisher confirms)
        C->>CDB: mark published_at
    end
    MQ->>L: learning.events: lesson_version.published
    L->>LDB: insert lesson_decks if absent, commit, ack
    MQ->>L: learning.events: lesson.changed
    L->>LDB: upsert learnable_lessons if newer than stored version, commit, ack
    U->>G: GET /api/topics/{topic_id} (app cookie)
    G->>I: GET /internal/auth/app
    I-->>G: 200 X-User-Id, X-User-Type, ...
    G->>L: GET /api/topics/{topic_id} + headers
    L->>LDB: read model + own progress (lesson shown once its deck has arrived)
    L-->>U: 200 topic with the new lesson
```

Steps 10 to 16 usually take well under a second. If RabbitMQ is down, steps 1 to 9 still succeed and the rows wait in the outbox; if Learning is down, the messages wait in `learning.events`.

## 3. Deleting an account

```mermaid
sequenceDiagram
    autonumber
    actor U as Learner
    participant G as Gateway
    participant I as Identity
    participant MQ as RabbitMQ
    participant L as Learning
    participant C as Content

    U->>G: POST /api/auth/delete-account {password}
    G->>I: (Identity route: passed straight through)
    rect rgba(127,127,127,0.12)
    note over I: one transaction
    I->>I: check password (or fresh Google token)
    I->>I: delete login_attempts, then the user (sessions, reset links, profile cascade)
    I->>I: outbox: identity.user.deleted (version 2)
    end
    I-->>U: 204, session cookie cleared
    U->>G: any later request with the old cookie
    G->>I: GET /internal/auth/app
    I-->>G: 401 (no such session)
    G-->>U: 401 not_signed_in
    I->>MQ: relay publishes identity.user.deleted
    par Learning (queue learning.events)
        MQ->>L: identity.user.deleted
        L->>L: advisory lock on the user, insert erased_learners (tombstone)
        L->>L: delete attempts, answers, completions, quiz, exemptions, learners row
        L-->>MQ: ack
    and Content (queue content.events)
        MQ->>C: identity.user.deleted
        C->>C: null reporter_id, resolved_by, published_by, created_by
        C-->>MQ: ack
    end
```

Both reactions are repeatable, so a redelivery changes nothing, and `erased_learners` makes sure a replayed `identity.user.registered` never brings the learner back ([ADR 0008](decisions/0008-account-deletion-saga.md)).

## 4. Gateway authentication (forward auth)

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant G as Gateway (nginx)
    participant I as Identity
    participant S as Content or Learning

    B->>G: GET /api/progress, Cookie sgjio_session=..., X-User-Id: forged
    alt no sgjio_session cookie at all
        G-->>B: 401 not_signed_in (Identity not asked)
    else cookie present
        G->>I: auth_request GET /internal/auth/app<br/>Cookie, X-Request-ID, X-Forwarded-For, X-Gateway-Key (no body)
        alt session valid for this scope
            I-->>G: 200 X-User-Id, X-User-Scope, X-User-Role, X-User-Type,<br/>X-Profile-Completed, Set-Cookie (sliding expiry)
            G->>S: GET /api/progress with Identity's X-User-* (client's replaced)<br/>+ X-Gateway-Key + X-Request-ID
            S->>S: require_principal("app"): key matches, scope and role fit
            S-->>G: 200 body
            G-->>B: 200 body + Identity's Set-Cookie + X-Request-ID
        else expired, signed out, removed, or wrong scope
            I-->>G: 401
            G-->>B: 401 not_signed_in
        else Identity down or slower than 2 s
            G-->>B: 503 service_unavailable, Retry-After: 5
        end
    end
```

Identity's own routes (`/api/auth/*`, `/api/profile`, ...) skip the subrequest; the gateway drops client `X-User-*` headers there and Identity reads its cookies itself.

## 5. What still works when a component is down

From the resilience drills (`e2e/test_resilience.py`, run with `scripts/e2e.sh --resilience`), the gateway's outage checks (`services/gateway/tests/run.sh`) and the services' own tests. Every outage answer is `503 {"detail":{"code":"service_unavailable",...}}` with `Retry-After: 5`.

| Down                             | Still works                                                                                                        | Stops (503)                                                                          | After recovery                                                                                                                | Checked by                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Learning**                     | sign-in, account and profile; all authoring, including publishing; media                                           | learner pages: home, topics, lessons, search, review, aptitude test; lesson insights | events published meanwhile wait in `learning.events` and are applied; the learner sees the lesson published during the outage | drill `test_learning_down_then_catches_up`                                                    |
| **learning-db**                  | everything outside Learning                                                                                        | Learning's routes (503, not 500)                                                     | Learning recovers by itself; its consumer held messages without dead-lettering them                                           | drill `test_learning_database_down_answers_503_not_500`                                       |
| **Identity**                     | public media; `/api/health`; signed-out visitors get the normal 401, so the sign-in page shows                     | every signed-in route on both front ends, including sign-in itself                   | sessions are in identity-db, so everyone is still signed in                                                                   | drill `test_identity_down_refuses_signed_in_routes_but_serves_media`; gateway `identity-down` |
| **Content**                      | learner pages, lessons and the aptitude test (served from Learning's read models); sign-in                         | authoring and the admin content pages; lesson images and audio; reporting a problem  | `identity.user.deleted` events wait in `content.events`                                                                       | gateway `content-down`                                                                        |
| **RabbitMQ**                     | every request, including publishing and forgot-password                                                            | nothing; changes stop reaching other services                                        | outboxes drain within seconds (reconnect backoff is capped at 5 s); the learner sees the lesson                               | drill `test_broker_outage_delays_but_never_loses_a_publish`                                   |
| **Mail server** (Mailpit / SMTP) | every request; forgot-password and invites still answer 204                                                        | nothing; email is delayed                                                            | Notification retries without counting failures; the email arrives                                                             | `services/notification/tests/test_delivery.py`                                                |
| **Notification**                 | every request                                                                                                      | nothing; email is delayed                                                            | messages wait in the durable `notification.events` queue and are sent                                                         | by design (queue is durable)                                                                  |
| **Gateway**                      | services directly on 127.0.0.1 ports, for Swagger only (Content and Learning refuse calls without the gateway key) | the whole app for browsers                                                           | stateless: just restart it                                                                                                    | —                                                                                             |

What does not happen in any row: a 500, a lost event, or one service's outage taking down another's routes.
