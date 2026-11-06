# SGJio microservices: build plan

Branch `arch/microservices`, not merged to `main`. This is the source of truth for the build. [detailed-plan.md](detailed-plan.md) is the full multi-agent plan, for reference. Where the two disagree, this page wins.

## Target

```
 web/ (5173)   admin/ (5174)        front ends unchanged; Vite still proxies /api to :8000
        \        /
      gateway (nginx, :8000)        routes by path; asks Identity "who is this?" on every protected request
     /      |       \
identity  content  learning   notification
   |        |        |            |
  db       db       db           db          one Postgres container each, no cross-service FKs
     \      |       /            /
       RabbitMQ (topic exchange sgjio.events)
```

| Service | Owns | Publishes | Consumes |
|---|---|---|---|
| identity | users, profiles, auth_sessions, password_reset_tokens, login_attempts, admin_events, outbox | identity.user.registered, identity.user.deleted, identity.password_reset.requested, identity.admin.invitation_issued, identity.admin.removed | none |
| content | topics, lessons, lesson_versions, media_assets, lesson_reports, aptitude_questions, aptitude_bank_state, outbox | content.topic.changed, content.topic.deleted, content.lesson.changed, content.lesson_version.published, content.aptitude_question.changed, content.aptitude_bank.changed | identity.user.deleted |
| learning | lesson_attempts, attempt_answers, lesson_completions, aptitude_attempts, topic_exemptions; read models learnable_topics, learnable_lessons, lesson_decks, quiz_questions, quiz_bank, learners, erased_learners | none (yet) | identity.user.*, content.# |
| notification | processed_events (inbox) | none | identity.password_reset.requested, identity.admin.* |

The detailed plan holds the service catalogue, the event payloads and the routing table: sections 2, 4.4 and 5.2. They apply as written, except where the rules below differ.

## Rules (every decision follows these)

1. **Database per service.** No service reads another's tables. Cross-service ids are plain UUIDs.
2. **Network-only communication.** Services never import each other's code. State changes go out as events. The only synchronous call is gateway to Identity for authentication.
3. **Independently deployable.** Each service is built only from `services/<name>/` and has its own Dockerfile, requirements, config, Alembic history and tests.
4. **Reliable events.** A producer writes its event to its own `outbox` table in the same transaction as the change, and a relay publishes it. Consumers are idempotent: they use version guards, insert-if-absent and tombstones, and Notification uses an inbox.
5. **Ordering.** Each event carries the aggregate's own `version` (`aggregate_version`). A consumer ignores a version older than or equal to the one it already has.
6. **The front ends don't change.** All paths, cookies, status codes and error bodies stay the same, except for the declared changes below.

## Simplifications to the detailed plan

| Detailed plan | Build plan |
|---|---|
| Identity mints an RS256 JWT; 15 s auth cache with stale-if-error | The gateway calls Identity `/internal/auth/{app,admin}` on **every** protected request, with no cache. Identity returns `X-User-Id`, `X-User-Role`, `X-User-Type` and `X-Profile-Completed`. nginx strips any client copies of these headers and forwards Identity's. It also adds `X-Gateway-Key`, which services check, so a request that bypasses the gateway is refused. Sign-out takes effect immediately everywhere. |
| `libs/chassis` built as a versioned wheel | Each service has its own copy of the plumbing (~300 lines) under `app/platform/`: errors, logging and correlation id, health, principal, outbox and relay, consumer base. A template lives in `templates/platform/`. |
| Separate `*-worker` containers | Each service runs its relay and consumer as background threads inside its API process (started in the FastAPI lifespan). Notification has no HTTP API, so it is a single worker process. |
| Gateway legacy mode and a `legacy-api` profile | Dropped. `main` is the monolith to compare against. |
| RabbitMQ shovel, least-privilege broker users, chaos script | Deferred. The management UI is kept. |
| Advisory locks on learner writes during account deletion | Dropped. The session is gone before the event is sent, and the gateway checks every request, so the deleted user cannot write afterwards. Learning keeps the `erased_learners` tombstone, so a replayed `user.registered` cannot bring a learner back. |
| `RESET_TOKEN_MINUTES = 5` | **15** on this branch, because email is now sent asynchronously. |

## Declared behaviour changes

- Admin changes (publish, withdraw, reorder, archive, aptitude bank edits) reach learners after a short replication delay, usually under a second.
- Emails are sent asynchronously. The request succeeds even if SMTP is down, and the email arrives when it recovers.
- After account deletion, the learner's progress and reporter links are erased within seconds instead of in the same commit.
- The insights learner count includes a new learner after the same delay.
- A topic that has ever had an aptitude question can't be deleted (`topics.assessed_at`).
- Lesson insights for a lesson Learning has never seen returns the empty "not published yet" shape instead of a 404.
- Request bodies are capped at the gateway: 10 MB by default, 20 MB on media upload.
- API docs move to one Swagger page per service: identity :8001, content :8002, learning :8003.
- If Identity is down, all signed-in routes return 503. Public media still works.

## Layout

```
services/{gateway,identity,content,learning,notification}/
contracts/events/*.schema.json   event payload schemas, the published language
templates/platform/              source of each service's copied plumbing
infra/                           rabbitmq definitions, postgres init
e2e/                             tests against the whole stack through :8000
scripts/seed-all.sh
docker-compose.yml
api/                             removed once every service passes its tests and the e2e suite
```

## Build order (you and Claude)

| Step | What | How | Done when |
|---|---|---|---|
| 0 | Foundations: layout, compose (4 DBs, RabbitMQ, Mailpit), `contracts/`, platform template, gateway skeleton | Claude, inline | `docker compose up` brings everything healthy; the event schemas are reviewed |
| 1 | Identity and Notification | Parallel agents in separate worktrees, one per service, each building against `contracts/` | Each service's ported tests pass in its own CI job, and the events show up in RabbitMQ |
| 2 | Content | (same run) | |
| 3 | Learning, the hardest: read models plus ported progress, exemptions, aptitude and insights | (same run) | Per service: tests green, image healthy |
| 4 | Integration: full gateway routing, `seed-all.sh`, e2e suite, manual click-through of both front ends | Claude, with you on the click-through | e2e green; checklist signed off |
| 5 | Cleanup and presentation: delete `api/`, update README/CLAUDE.md/dev.local/CI, write architecture decision records and diagrams, failure demo | Claude, with you | Clean clone runs with one command |

Steps 1–3 can run at the same time because they depend only on `contracts/` and the platform template. Each step is reviewed before the next one starts.
