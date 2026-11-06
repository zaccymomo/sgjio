> **Reference only.** This is the full multi-agent plan (revision 2). Where it disagrees with [README.md](README.md) (the build plan), the build plan wins. The main differences: no JWT or auth cache, plumbing copied instead of shipped as a wheel, no legacy gateway mode, no separate worker containers, no RabbitMQ shovel or least-privilege users.

# SGJio microservices: target architecture and migration plan (revision 2)

Status: proposal for team review. Nothing in the repository has been changed. The work goes on a long-lived branch (working name `arch/microservices`) and is not merged to `main` for now. Nothing is pushed to origin without Yash asking.

**Checked against the code for this revision:**
- `auth/deps.py` and `auth/sessions.py`: sessions, cookie paths, the sliding refresh.
- `main.py` and every `routers/*` file.
- `aptitude.py`: `update_question` can move a question to another topic; `bank()`; `_ready_topics` builds an error message that names the topics that are not ready.
- `topics.delete_topic`: it checks lessons only, and relies on the RESTRICT FK for exemptions.
- `lessons.delete_lesson`: only a lesson with no version can be deleted.
- `models.Lesson.title`: this is the draft title, and each version keeps its own copy.
- `insights.lesson_insights` and `LessonInsights`: the title, status and topic name are shown by `admin/src/pages/LessonInsightsPage.tsx`, which also shows "Not published yet" when there are no versions.
- `progress._levels` and `progress._snippet`: the snippet comes from the first matching card.
- `config.py`: `media_max_image_mb=15`.
- `routers/admin.py`: the upload reads at most limit+1 bytes and returns a JSON `media_too_large` error.
- `ci.yml`, `dev.local` and the Vite proxy config.

---

## 1. Target architecture overview

```mermaid
flowchart LR
  subgraph Browser
    WEB["web/ (Vite :5173)"]
    ADM["admin/ (Vite :5174)"]
  end
  WEB -- "/api/* (Vite proxy)" --> GW
  ADM -- "/api/* (Vite proxy)" --> GW

  GW["API gateway (nginx :8000)<br/>path routing · forward-auth<br/>app-scope auth cache 15 s<br/>correlation id · JSON errors"]
  GW -- "auth_request (no body)<br/>GET /internal/auth/{app|admin}" --> IDA
  GW -- "/api/auth, /api/admin/auth, /api/profile,<br/>/api/intro, /api/admin/admins, /api/admin/ping" --> IDA
  GW -- "/api/admin/{topics,lessons,media,reports,aptitude-questions},<br/>/api/media, POST /api/lessons/:id/reports" --> CTA
  GW -- "/api/lessons, /api/attempts, /api/progress, /api/topics,<br/>/api/search, /api/review, /api/aptitude,<br/>/api/admin/lessons/:id/insights" --> LNA

  subgraph Identity["Identity service"]
    IDA["identity-api"] --- IDB[(identity-db)]
    IDW["identity-worker<br/>(outbox relay)"] --- IDB
  end
  subgraph Content["Content service"]
    CTA["content-api"] --- CDB[(content-db)]
    CTW["content-worker<br/>(relay thread + consumer thread)"] --- CDB
  end
  subgraph Learning["Learning service"]
    LNA["learning-api"] --- LDB[(learning-db<br/>own tables + read models)]
    LNW["learning-worker<br/>(consumer)"] --- LDB
  end
  subgraph Notification["Notification service"]
    NTW["notification-worker"] --- NDB[(notification-db)]
  end

  MQ{{"RabbitMQ 4<br/>topic exchange sgjio.events<br/>+ DLX sgjio.dlx"}}
  IDW -- "identity.*" --> MQ
  CTW -- "content.*" --> MQ
  MQ -- "identity.user.deleted" --> CTW
  MQ -- "identity.user.*, content.*" --> LNW
  MQ -- "identity.password_reset.requested,<br/>identity.admin.*" --> NTW
  NTW -- SMTP --> MP["Mailpit / SMTP"]

  KEY[/"JWT public key (mounted file)"/] -.-> CTA
  KEY -.-> LNA
```

**Key properties:**
- **4 business services and 1 gateway.** The services are Identity, Content, Learning and Notification. Each one has its own image, built from its own directory, and its own dependencies, config, Alembic history and Postgres container.
- **The only synchronous call between components is authentication.** The gateway calls Identity. Every cross-domain state change travels as an event. There are no snapshot or rebuild HTTP endpoints. A rebuild works by having the producer republish its current state through the same event path.
- **Events carry the facts consumers need, not copies of Content's tables.** Content evaluates its own rules (whether a learner can see a lesson, whether the aptitude bank is ready) and publishes the results. Learning keeps read models named for its own purpose (`learnable_lessons`, `lesson_decks`, `quiz_questions`, `quiz_bank`, `learners`), and never re-implements Content's rules.
- **Ordering uses a per-aggregate `version` owned by the aggregate.** This replaces the outbox row id, so ordering survives outbox pruning and data migration.
- **Delivery is reliable.** Each producer uses a transactional outbox. Content and Learning consumers are naturally idempotent. Notification, the only consumer with a side effect that cannot be repeated safely, keeps an inbox table.
- **The front ends do not change.** The gateway listens on `:8000`, which the Vite proxies already target. Every public path, cookie, status code and error body stays the same, apart from the declared changes in section 3.3.

---

## 2. Service catalogue

### 2.0 Every existing table and its owner

| Existing table | Owner | Notes |
|---|---|---|
| users | Identity | |
| profiles | Identity | Seed of a future Community/Matching context |
| auth_sessions | Identity | |
| password_reset_tokens | Identity | Also holds admin invites |
| login_attempts | Identity | |
| admin_events | Identity | |
| topics | Content | Gains `version int` and `assessed_at timestamptz` (set once, never cleared) |
| lessons | Content | Gains `version int`. Becomes the source of `learnable_lessons` in Learning, only after the first publish |
| lesson_versions | Content | Projected into `lesson_decks` in Learning (insert-only) |
| media_assets | Content | Not replicated. Asset facts travel inside the version event |
| lesson_reports | Content | `reporter_id` and `resolved_by` become plain UUIDs |
| aptitude_questions | Content | Gains `version int`. Projected into `quiz_questions` |
| lesson_attempts | Learning | `user_id`, `lesson_id` and `version_id` become plain UUIDs |
| attempt_answers | Learning | |
| lesson_completions | Learning | |
| aptitude_attempts | Learning | |
| topic_exemptions | Learning | `topic_id` becomes a plain UUID |
| alembic_version | every DB | One per service |
| (new) outbox | Identity, Content | Defined in each service's own models and baseline migration |
| (new) aptitude_bank_state | Content | Single row holding `revision`, which orders `aptitude_bank.changed` |
| (new) learnable_topics, learnable_lessons, lesson_decks, quiz_questions, quiz_bank, learners, erased_learners | Learning | Read models plus the erasure tombstone |
| (new) processed_events | Notification | Inbox, because sending email is not idempotent |

### 2.1 Identity: accounts, sessions, credentials, administrators, learner profile, onboarding

- **Bounded context:** who someone is, how they sign in, and what they have told us about themselves.
- **Owned tables:** users, profiles, auth_sessions, password_reset_tokens, login_attempts, admin_events and outbox. All foreign keys and cascades inside Identity stay as they are.

**Public API (through the gateway; paths and bodies unchanged):**
- `/api/auth/`: sign-in, register, google, privacy-notice-version, change-password, delete-account, forgot-password, reset-password/check, reset-password, sign-out, me
- `/api/admin/auth/`: sign-in, forgot-password, reset-password/check, reset-password, invite/check, invite/accept, sign-out, me
- `GET/PUT /api/profile`, `GET /api/profile/options`, `POST /api/intro/finished`
- `GET/POST /api/admin/admins`, `POST /api/admin/admins/{id}/resend-invite|remove|restore`, `GET /api/admin/ping`
- Identity keeps its in-process `require_user`/`require_admin` for these routes, because it owns the sessions.

**Internal API** (never routed by the gateway; the caller must send `X-Service-Key`):
- `GET /internal/auth/app` and `GET /internal/auth/admin`: session introspection. It reads the cookie for that scope from the forwarded `Cookie` header and runs today's `resolve_session` (expiry, sliding refresh, `is_removed`, and `is_admin` for the admin scope).
  - When the session is valid it returns `200` with:
    - `X-Principal-Token: <RS256 JWT>`
    - `Set-Cookie`, only when the sliding refresh was written, which happens at most once a minute
    - `Cache-Control`: `max-age=15, stale-if-error=240` for app, and `no-store` for admin
  - Otherwise it returns `401` with `Cache-Control: no-store`.
- `/health/live` and `/health/ready`.

**Events published (outbox):**
- `identity.user.registered`
- `identity.user.deleted`
- `identity.password_reset.requested`
- `identity.admin.invitation_issued`
- `identity.admin.removed`

**Events consumed:** none. **Read models:** none.

**Command-line tools:**
- `seed`, `create-admin`, `send-reset`, `seed-demo-learners`, `clear-demo-learners`
- `republish-learners`: writes `user.registered` for every current user, used to rebuild Learning's `learners`
- `health`

**Files moving in from `api/app`:**
- `auth/`, `admins.py`, `security.py`, `privacy.py`, `profile_options.py`
- `routers/auth.py`, `routers/profile.py`, `routers/onboarding.py`, and the `/admins*` and `/ping` parts of `routers/admin.py`
- The Identity models (User, Profile, AuthSession, PasswordResetToken, LoginAttempt, AdminEvent and the enums AuthScope, UserRole, UserType), the Identity schemas and settings
- `create-admin` and `send-reset` from `cli.py`, and the user and profile part of `seed.py`

**Changes inside:**
- `auth/reset.py` and `admins.py` write outbox events instead of calling `send_email`.
- `delete-account` writes `identity.user.deleted` in the same transaction as the delete.
- Every account creation (register, Google sign-up, invite, `create-admin`, seed) writes `identity.user.registered`.
- `admins.py` raises the chassis `Problem` instead of `ContentProblem`.
- New modules: `routers/internal.py` and `principal_token.py`, which mints the JWT.
- uvicorn runs with `--proxy-headers --forwarded-allow-ips=<gateway address>`, where the address is the gateway's fixed IP on the compose network. Lockout and `login_attempts` therefore record the real client IP. See section 5.1 for why the gateway overwrites `X-Forwarded-For`.

### 2.2 Content: authoring and publishing (topics, lessons, versions, media, reports, aptitude bank)

- **Bounded context:** what there is to learn, and how it is authored, published and quality-controlled. Content owns the rules for what a learner may see and for whether the aptitude test is ready.
- **Owned tables:** topics, lessons, lesson_versions, media_assets, lesson_reports, aptitude_questions, aptitude_bank_state and outbox.
  - Foreign keys inside Content stay, including `aptitude_questions.topic_id` RESTRICT.
  - Foreign keys to `users` are dropped. `published_by`, `created_by`, `reporter_id` and `resolved_by` become plain UUIDs.

**New columns:**
- `topics.version`, `lessons.version` and `aptitude_questions.version`: integers, incremented in the same transaction as any change that the published projection reflects.
- `topics.assessed_at`: set when a question is first created in, or moved into, the topic. It is never cleared. It guards topic deletion (see section 3.4).

**Public API (through the gateway; unchanged):**
- `/api/admin/topics`: GET, POST; `/order` PUT; `/{id}` PATCH, DELETE; `/{id}/archive`, `/{id}/restore`
- `/api/admin/lessons`: GET, POST; `/order` PUT; `/{id}` GET, PATCH, DELETE; `/{id}/publish|discard|withdraw|restore`
- `POST /api/admin/media`
- `GET /api/admin/reports`, `PUT /api/admin/reports/{id}/status`
- `GET/POST /api/admin/aptitude-questions`, `PATCH /api/admin/aptitude-questions/{id}`
- `GET /api/media/{id}` (public)
- `POST /api/lessons/{id}/reports` (learner)

**Internal API:** `/health/*` only.

**Events published (outbox):**
- `content.topic.changed`, `content.topic.deleted`
- `content.lesson.changed`
- `content.lesson_version.published`
- `content.aptitude_question.changed`
- `content.aptitude_bank.changed`

There is no `lesson.deleted` event. Only lessons that were never published can be deleted, and those are never published as events.

**Events consumed:** `identity.user.deleted`. The handler sets `reporter_id`, `resolved_by`, `published_by` and `created_by` to NULL for that user. Running it twice has the same effect, so it is naturally idempotent.

**Read models:** none. The admin's id comes from the JWT `sub`, and Content never displays user names.

**Command-line tools:**
- `seed`, `import-lessons [folder] [--publish]`, `prune-media`
- `republish-catalog`: writes current-state events for every topic, every lesson published at least once, every version, every question and the bank
- `health`

**Files moving in:**
- `topics.py`, `lessons.py`, `lesson_doc.py`, `media.py`, `reports.py`, `content_import.py` and `problems.py`
- The bank part of `aptitude.py`: `_assessed_topics`, `bank`, `create_question`, `update_question`
- The topic, lesson, media, report and aptitude-question parts of `routers/admin.py`, plus `routers/media.py` and the reports route from `routers/lessons.py`
- The Content models and schemas, the content part of `seed.py`, and `import-lessons` and `prune-media` from `cli.py`
- The `content/` lesson folder is not baked into the image. It is mounted read-only at runtime (`./content:/srv/content:ro`) as the input to the import command, so the image builds from `services/content` alone.

**New module `projections.py` (the published language):**
- `learner_visible(lesson)` returns `lesson.status == published and topic not archived`. It is the single definition of the rule. `reports.py` uses it, and its result is published in `lesson.changed`.
- `lesson_projection(lesson)` builds the payload described in section 4.4.
- `version_projection(version)` precomputes, for each question, `scored` and `correct_option_id`, plus `reading_seconds` (which needs media durations), `scored_questions`, the assets map and `cards_plain_text[]` (one entry per card, in card order). Learning therefore never needs `lesson_doc.py` or `media.py`.
- `bank_projection()` wraps `bank()` and returns `{ready, topics:[{topic_id, ready}]}` in the admin's order.

**Emission rules (`events.py`, always in the same transaction as the change):**
- **Topics.**
  - `topic.changed` on create, rename, describe, archive, restore and reorder (one event per topic whose position moved), on import, and on the direct `Topic()` inserts in `content_import.py:149` and `seed.py:361`.
  - Archive and restore also emit `lesson.changed` for every lesson in the topic that has ever been published, because `learner_visible` changed. Each of those lessons' `version` is bumped.
  - Archive and restore emit `aptitude_bank.changed` as well.
- **Lessons.** `lesson.changed` is emitted only for lessons that have been published at least once. It fires on publish, withdraw, restore, a draft title change, a topic move, reorder, and a discard that changes the title. Draft edits to cards or the summary emit nothing.
- **Versions.** `lesson_version.published` is emitted on every publish that creates a version. It is written before `lesson.changed` in the same transaction.
- **Aptitude questions.** `aptitude_question.changed` is emitted on create, update, activate, deactivate and seed, each followed by `aptitude_bank.changed`. The bank event takes `UPDATE aptitude_bank_state SET revision = revision + 1 RETURNING revision`, and that row lock serialises concurrent bank changes.

**Other changes inside:**
- `delete_topic` refuses with `topic_not_empty` when the topic has lessons or when `assessed_at IS NOT NULL`. This covers everything today's FK block covers (see section 3.4).
- `require_admin` and `require_user` become `require_principal("admin")` and `require_principal("app")`.

### 2.3 Learning: what a learner does with content, and what it tells us

- **Bounded context:** lesson runs, grading, completions, the aptitude test and exemptions. It also owns the learner's views (circles, topic page, suggestion, search, review, results) and the admin lesson analytics (insights).

**Owned tables:**
- **Own data:** lesson_attempts, attempt_answers, lesson_completions, aptitude_attempts and topic_exemptions.
  - Foreign keys inside Learning stay: answers to attempts, `best_attempt_id` to attempts, and exemptions to aptitude_attempts.
  - References to users, lessons, versions and topics become plain UUIDs.
- **Read models**, written only by the Learning consumer and named for Learning's use:

| Table | Fed by | Columns | Ordering guard |
|---|---|---|---|
| `learnable_topics` | content.topic.* | id, name, description, position, is_archived, deleted, version | `version` |
| `learnable_lessons` | content.lesson.changed | id, key, topic_id, level, position, display_title, publication_state (published or withdrawn), learner_visible, first_published_at, published_at, withdrawn_at, latest_version_id, latest_version_number, version | `version` |
| `lesson_decks` | content.lesson_version.published | id (the version id), lesson_id, number, title, summary, published_at, doc JSONB (full, including correct flags, why_not and explanation), reading_seconds, scored_questions, assets JSONB, cards_plain_text JSONB array | insert if absent (immutable) |
| `quiz_questions` | content.aptitude_question.changed | id, topic_id, level, prompt, options, correct_option_id, is_active, seed_key, version | `version` |
| `quiz_bank` | content.aptitude_bank.changed | single row: revision, ready, topics JSONB `[{topic_id, ready}]` | `revision` |
| `learners` | identity.user.registered / deleted | user_id, user_type, registered_at (only `role=user`) | insert if absent; refused if erased |
| `erased_learners` | identity.user.deleted | user_id, erased_at (no personal data) | insert if absent |

**Public API (through the gateway; unchanged):**
- Lessons: `GET /api/lessons/{id}` (the deck, without answers), `POST /api/lessons/{id}/attempts`, `POST /api/attempts/{id}/answers`, `POST /api/attempts/{id}/finish`
- Learner pages: `GET /api/progress`, `GET /api/topics/{id}`, `GET /api/search`, `GET /api/review`
- Aptitude test: `POST /api/aptitude/start|next|submit|skip`, `GET /api/aptitude/result`
- Admin: `GET /api/admin/lessons/{id}/insights`

**Internal API:** `/health/*` only. Learning makes no outgoing HTTP calls at all.

**Events published:** none in this scope. `learning.lesson.completed` and `learning.aptitude.completed` are reserved for the future Portfolio/tiers service (SCRUM-27); see the open questions.

**Events consumed:**
- `identity.user.registered`, `identity.user.deleted`
- `content.topic.changed|deleted`, `content.lesson.changed`, `content.lesson_version.published`, `content.aptitude_question.changed`, `content.aptitude_bank.changed`

**Command-line tools:**
- `seed`, `demo-activity`
- `reset-read-models`: truncates the read models, but not `erased_learners`, so producers can then republish into them
- `wait-for-read-models`
- `health`

**Files moving in:**
- `learning.py`, `progress.py`, `review.py`, `exemptions.py`, `insights.py` and `demo.py`
- The quiz engine part of `aptitude.py`: `_eligible`, `_ready_topics`, `_pick`, `_trace`, start/next/submit/skip, `result_out`, `has_taken_quiz`
- `routers/lessons.py` (deck, attempts, answers, finish), `routers/progress.py`, `routers/review.py`, `routers/aptitude.py`, and the insights route from `routers/admin.py`
- The Learning models and schemas, and the `demo-activity` command

**Changes inside:**
- **Visibility.** Wherever the code tested "published and topic not archived" (`published_lesson`, progress circles, topic page, suggestion, search, `_topic_now_complete`, `result_out`), it now tests `learnable_lessons.learner_visible`.
  - `_levels` keeps its exact semantics by testing `publication_state = 'published'`.
  - Topic lists still filter `learnable_topics.is_archived = false AND deleted = false`, which is the topic's own state, not a rule from Content.
- **Ported SQL.** Queries are ported with mechanical renames (`Lesson` becomes `LearnableLesson`, and so on). The correlated `topic_exemptions.level >= learnable_lessons.level` comparison in `is_exempted` stays a local join.
- **Latest version.** `latest_version()` becomes a lookup on `learnable_lessons.latest_version_id`. A lesson whose latest deck has not arrived yet is invisible to learners, because queries inner-join `lesson_decks`.
- **Tolerant reader.** A new `published_doc.py` holds tolerant-reader Pydantic models for the deck. It is written from the JSON Schema contract, not copied from `lesson_doc.py`.
- **Aptitude readiness.** `_ready_topics` reads `quiz_bank`. When it is not ready, the existing `aptitude_not_ready` message is rebuilt from `quiz_bank.topics` (the topics that are not ready) and the names in `learnable_topics`. Learning no longer has any readiness rule of its own.
- **Eligibility.** `_eligible` reads `principal.user_type` and `principal.profile_completed` from the JWT. Aptitude routes always get a fresh introspection (see section 5).
- **Insights.**
  - `_runs` and `_learner_count` join or count `learners` instead of `users`.
  - The page header uses `learnable_lessons.display_title`, `publication_state` and the topic name from `learnable_topics`.
  - A lesson Learning has never seen (never published, or still in replication lag) returns today's "no versions" shape: `title: ""`, `status: "draft"`, `versions: []`. A `?version=N` request for such a lesson still returns `version_not_found`.
- **Search.** `_snippet` loops over `lesson_decks.cards_plain_text` exactly as it loops over `doc.cards` today.
- **Erasure guard.** Every write path scoped to a learner (start attempt, answer, finish, aptitude start, next, submit and skip) begins with `pg_advisory_xact_lock_shared(hashtext(user_id::text))` and then refuses ids found in `erased_learners`, returning 401 `not_signed_in`. See section 3.4.

### 2.4 Notification: outbound communication

- **Bounded context:** telling people things by email. It is a generic, supporting subdomain. Notification decides which template a fact maps to; Identity decides what happened.
- **Owned tables:** `processed_events(event_id, type, processed_at)`. No addresses are stored, so no personal data is kept at rest.
- **Public or internal API:** none. A health check from the command line is used by the compose healthcheck; it checks the database and the broker.

**Events consumed and their templates:**
- `identity.password_reset.requested`:
  - with `method=password`, it sends `password_reset_email`
  - with `method=google`, it sends `google_account_email`
- `identity.admin.invitation_issued`, for any `trigger`, sends `admin_invite_email`. The wording varies by trigger, as it does today.
- `identity.admin.removed` sends `admin_removed_email`.

**Delivery semantics: at least once.**
1. Skip the event if its `event_id` is already in `processed_events`.
2. Send the email.
3. Insert the `processed_events` row and acknowledge the message.

A crash between steps 2 and 3 sends a duplicate email; it never loses one. An SMTP failure raises an error, the message is requeued, and after 5 deliveries it is dead-lettered.

**Files moving in:** `mailer/__init__.py` (the smtp, console and memory backends) and `mailer/templates.py`, unchanged, plus the `email_*` and `smtp_*` settings.

### 2.5 API gateway (nginx)

The gateway handles:
- Routing by path.
- Forward authentication with the scope chosen by path, without forwarding the request body.
- An app-scope auth cache.
- Injecting the principal JWT as `Authorization: Bearer`. Any `Authorization` header from the client is overwritten, and it is stripped on public routes.
- Relaying the sliding `Set-Cookie`.
- The correlation id.
- JSON bodies for the 401, 404, 413 and 502/503/504 errors that the gateway itself generates.
- Body size limits.
- Streaming media: Range, 206, 304 and 416 pass through.

It holds no business logic and no durable state; the auth cache is a disposable tmpfs.

### 2.6 Deliberate boundary choices

| Choice | Why |
|---|---|
| Media stays in Content | Only lessons reference assets. `prune` must scan every draft and version. Assets are immutable. A separate Media service would add a synchronous dependency for no gain |
| Reports stay in Content | They are about content quality, and are validated against Content's versions, cards and its own `learner_visible` |
| The aptitude bank and its readiness rule stay in Content; the quiz engine goes to Learning | Authoring lives with authoring. Content publishes readiness as a fact, so Learning has no copy of the rule. The topic-delete guard stays local |
| Insights stays in Learning | It is analytics over attempts. A separate Analytics service is a future option once Learning publishes attempt events |
| Profile stays in Identity | Simplest for now. It is flagged as the seed of a future Community/Matching service |

---

## 3. Data ownership and consistency

### 3.1 Every cross-domain dependency from discovery, and how it is resolved

| # | Dependency today | Resolution | Pattern |
|---|---|---|---|
| 1 | `require_user`/`require_admin` load an ORM `User` in every router | The gateway calls Identity introspection. Identity returns an RS256 JWT. The chassis `require_principal(scope)` verifies it with Identity's public key and returns `Principal(user_id, scope, role, user_type, profile_completed)` | Gateway forward-auth plus an access token |
| 2 | Account deletion cascades into completions, attempts, answers, aptitude attempts and exemptions | Identity deletes its own rows and writes `identity.user.deleted` in one transaction. Learning purges the user's data under an exclusive per-user lock and records the user in `erased_learners` | Choreographed saga, outbox, idempotent consumers |
| 3 | `lesson_reports.reporter_id`/`resolved_by` are SET NULL | Plain UUIDs, nulled by Content's consumer on `user.deleted` | Event |
| 4 | `lesson_versions.published_by`, `media_assets.created_by` are SET NULL | Plain UUIDs from `principal.user_id`, also nulled on `user.deleted` | Opaque reference |
| 5 | `aptitude._eligible` reads `user.user_type` and `user.profile` | JWT claims. Aptitude routes always use an uncached introspection, so `profile_completed` is current right after a profile save | Claims in token |
| 6 | Insights joins `users.role`/`user_type` and counts learners | The `learners` read model (role=user only) | Replicated read model |
| 7 | `learning.published_lesson` reads `Lesson.status` and `Topic.archived_at` | Content computes `learner_visible` and publishes it. Learning filters on the flag. Content's reports call the same function | Published language: the owner evaluates its own rule |
| 8 | `learner_lesson` needs the version doc and media facts | `lesson_decks`, with `reading_seconds` and `assets` precomputed by Content | Event-carried state transfer |
| 9 | `start_attempt` needs the latest version | `learnable_lessons.latest_version_id/number`. The deck and the start check read the same rows, so they cannot disagree | Read model |
| 10 | Answer checking needs the correct options | The full deck, including correct flags, is in `lesson_decks`. It reaches Learning only over the internal broker and never leaves through the gateway | Read model (internal only) |
| 11 | `_topic_now_complete` counts published lessons in the topic | The same SQL over `learnable_lessons.learner_visible`. The quirk of ignoring exemptions is kept | Read model |
| 12 | Circles, `_levels`, `_suggestion` and `topic_lessons` join Topic, Lesson, Completion and Exemption | The same SQL over the read models | Read model |
| 13 | `is_exempted` compares `TopicExemption.level` with `Lesson.level` | `learnable_lessons.level`. A lesson's level is fixed once it is first published, and only lessons that have been published are ever sent, so this holds by construction | Read model and structural invariant |
| 14 | Search reads the latest version's text and the learner's completions | `lesson_decks.cards_plain_text[]`, one entry per card, so the first-matching-card snippet is unchanged | Read model |
| 15 | Review needs the latest version and historic versions (for removed options) | Every version is sent; versions are immutable and insert-only | Read model |
| 16 | The quiz engine reads `aptitude_questions` including `correct_option_id` | `quiz_questions` | Read model |
| 17 | `_ready_topics` calls `bank()` | Content publishes `aptitude_bank.changed {ready, topics[]}`. Learning stores it in `quiz_bank` | Published fact; no duplicated rule |
| 18 | `result_out` counts exempted and available lessons per topic | Read models | Read model |
| 19 | `topic_exemptions.topic_id` RESTRICT blocks topic deletion | Content refuses deletion once `topics.assessed_at` is set, and `assessed_at` is never cleared. Exemptions can only exist for a topic that has had questions, so no exemption can ever be orphaned. Learning parks an impossible `topic.deleted` that still has exemptions in the DLQ and does not delete them | Local guard over an irreversible fact |
| 20 | FKs from attempts and completions to lessons and versions | Plain UUIDs. Only never-published lessons can be deleted, and those were never sent to Learning | Opaque reference |
| 21 | `reports.py` imports `learning.published_lesson` | Content's own `projections.learner_visible` | Ownership |
| 22 | Learning imports `lesson_doc.py` and `media.py` | A versioned JSON Schema contract with precomputed fields, read in Learning by a tolerant reader | Published language |
| 23 | `problems.py` is shared by Content and Learning | Each service has its own error helpers. The chassis provides only the wire shape | Contract, not code |
| 24 | `admins.py` imports `ContentProblem` | The chassis `Problem` | Ownership |
| 25 | Emails sent synchronously inside requests | Identity outbox facts, consumed by Notification | Event |
| 26 | One `routers/admin.py` mixes three domains | Split by path at the gateway | Gateway routing |
| 27 | `seed.py`/`demo.py` write users, content and learning in one session | Per-service seeds, deterministic user UUIDs, natural keys resolved through Learning's read models, and `scripts/seed-all.sh` | Orchestrated, not transactional |
| 28 | One `cli.py` | One command-line tool per service | Ownership |
| 29 | Shared `conftest.py`, `make_user` and `TRUNCATE` | Per-service suites, minted test JWTs, fixtures fed by generated events, contract tests, e2e | Test isolation |
| 30 | One Alembic history | A fresh baseline per service. The monolith migration tests are retired on the branch | Ownership |
| 31 | The Home aptitude prompt combines `/me` and `/progress` | Unchanged; already composed in the browser | UI composition |
| 32 | The skipped-quiz inference uses profile and progress | Unchanged; composed in the browser | UI composition |
| 33 | `login_attempts` deleted by email on account deletion | Inside Identity's transaction | Local |
| 34 | `config.py` mixes every concern | Split per service | Ownership |
| 35 | Insights header shows the draft title, status and topic name | `lesson.changed` carries `display_title` (the current admin-facing title) and `publication_state` for every lesson that has been published | Published language, for display only |

### 3.2 Read-model design

- **Event-carried state transfer, with events designed for consumers.**
  - Each `*.changed` event carries the full current state of the aggregate, as defined by the contract rather than as a table row, so consumers can upsert without calling back.
  - The contract contains only what consumers need. It carries no `created_at`, no draft lifecycle and no unpublished lessons.
- **Ordering uses an aggregate version owned by the producer.**
  - Topics, lessons and aptitude questions carry an integer `version`, incremented in the same transaction that changes the projected state. The `UPDATE` takes the row lock, so versions follow commit order.
  - The aptitude bank uses `aptitude_bank_state.revision` in the same way.
  - The version goes into the envelope as `aggregate_version` and into the read-model row.
  - Upserts apply only when `excluded.version > current.version`, so duplicates and redeliveries that arrive out of order cannot change anything.
  - The outbox `id` is only the relay's cursor. It is not part of any contract, so pruning the outbox or migrating data cannot break ordering.
- **Decks are inserted only if absent** (`ON CONFLICT DO NOTHING`), because they are immutable.
- **`learners` rows are inserted only if absent**, and only if the id is not in `erased_learners`. Registration data never changes, so no version is needed. Erasure is permanent and wins over any replayed `registered` event.
- **Topic deletes are tombstones in the row:** `deleted=true` and the version is bumped, so a stale `changed` event cannot bring the topic back. Lessons are never deleted once sent to Learning.
- **Within one transaction, Content writes `lesson_version.published` before `lesson.changed`.** If the order is ever disturbed, the lesson is briefly invisible to learners, because queries inner-join `lesson_decks`. This repairs itself.
- **Rebuild and recovery by republishing; there are no snapshot endpoints.**
  1. Run `learning reset-read-models`, which truncates the read models but keeps `erased_learners`.
  2. Run `content republish-catalog` and `identity republish-learners`. Each writes, in one transaction, outbox events with the current state and current `version` of every aggregate.
  3. The ordinary consumer path applies them.

  The same mechanism handles recovery from a dead-lettered event. Republishing without a reset is also safe: the aggregate's current version is at least the parked event's version, which is higher than the stale read-model row's version, so the update applies.

### 3.3 Eventual consistency users could notice

| Situation | Today | After (normal) | After (Learning worker or broker down) |
|---|---|---|---|
| Admin publishes or re-publishes a lesson | Learners see it instantly | Typically under 1 s (250 ms outbox poll plus consumption) | Learners keep the previous state until recovery. Admin authoring is unaffected |
| Withdraw, restore, topic move, reorder, archive, rename | Instant | Same lag | A withdrawn lesson is still counted and can still be opened until recovery. Grading stays correct against its version |
| Aptitude bank edits | Readiness changes instantly | Same lag | Readiness is stale |
| Lesson insights after a publish, title change or topic change | Instant | Same lag. Right after a first publish, the page may briefly show "Not published yet" | Stale until recovery |
| Account deletion | Learning rows and reporter link removed in the same commit | Email freed and sign-in impossible immediately. Learning rows and `reporter_id` erased within about 1 s. Writes by the erased user are refused at once | Erasure completes on recovery (the event waits durably) |
| New learner registers | Counted in insights immediately | After the lag | Insights denominator is stale |
| Sign-out or password change on another device | That session is refused on its next request | Identity routes refuse it immediately. Learning and Content app routes may accept the old session for up to 15 s (auth cache) | Same |
| Admin removal | Refused on the next request | Unchanged: the admin scope is never cached | Unchanged |
| Password reset, invite or removal email | Sent in the request; an SMTP failure gave a 500 after commit | Request always succeeds; email within about 1 s | Email delayed. A 5-minute reset link can expire before it arrives |
| Identity down for under about 4 minutes | Everything down | Learners who recently made a request keep working (stale-if-error auth cache). Sign-in, profile and admin routes return 503 | Same |

### 3.4 Deletion propagation

**Learner account deletion: a choreographed saga that needs no compensation.**
1. Identity verifies the password or a fresh Google token.
2. In one transaction, Identity deletes `login_attempts` by email and deletes the user. That cascades to the profile, sessions, tokens and admin_events locally. The same transaction inserts the `identity.user.deleted {user_id}` outbox row.
3. Identity returns 204 and clears the cookie.
4. Learning's consumer, in one transaction:
   - takes `pg_advisory_xact_lock(hashtext(user_id::text))` (exclusive)
   - inserts the user into `erased_learners`
   - deletes attempt_answers (through attempts), lesson_attempts, lesson_completions, topic_exemptions, aptitude_attempts and the `learners` row for that user

   Every step has the same effect if repeated.
5. Content's consumer nulls `reporter_id`, `resolved_by`, `published_by` and `created_by` for that user.
6. **Race guard for requests in flight.** The deleted user may still hold a valid JWT (up to 5 minutes for the app scope). Every Learning write path for a learner takes the shared form of the same advisory lock and then checks `erased_learners`. A write either commits before the purge (and is then purged) or sees the tombstone and is refused. A `user.registered` event replayed after the deletion is ignored. Reads for an erased user return empty data, which is harmless.

**Admins are never deleted**, only closed with `removed_at`. Removal takes effect on the admin's next request, because the admin scope is never cached.

**Lesson deletion:** only lessons that were never published can be deleted, and Learning never heard of them. No event is needed.

**Topic deletion:**
- Content refuses when the topic has lessons or `assessed_at` is set. Moving a topic's last question elsewhere does not clear `assessed_at`, which closes the hole the functionality review found. Deletion is therefore possible only for a topic that never had a lesson or a question.
- `content.topic.deleted` tombstones `learnable_topics`.
- If, against the invariant, exemptions exist for that topic, the handler raises. The message goes to the DLQ for a human, and nothing is deleted.

### 3.5 Idempotency, ordering, outbox

**Outbox, in Identity and Content:**
- The table `outbox(id bigserial, event_id uuid, type, aggregate_type, aggregate_id, aggregate_version, payload jsonb, correlation_id, created_at, published_at)` is defined in each service's own models and baseline migration.
- The relay polls every 250 ms with `SELECT … WHERE published_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED`, publishes with publisher confirms, and then sets `published_at`.
- Rows that were published more than 7 days ago are pruned. This is safe because ordering does not depend on the outbox id.
- One relay runs per service. Delivery is at least once.

**Consumers:**
- **Content and Learning are naturally idempotent.** Their handlers use version-guarded upserts, insert-if-absent, tombstones, deletes by `user_id` and nulling. No inbox table is needed, and the duplicate-event and stale-version tests prove it.
- **Notification** keeps a `processed_events` inbox (see section 2.4).

**Retries and the DLQ:**
- Queues are quorum queues with `x-delivery-limit=5` and the dead-letter exchange `sgjio.dlx`, which routes to `<queue>.dlq`.
- `notification.events.dlq` has `x-message-ttl=3600000` (1 h), so expired one-time links and email addresses do not sit in the broker.
- Parked messages are replayed with the RabbitMQ management UI's "Move messages" (the shovel plugin is enabled), or by republishing the aggregate.

**Learning publishes nothing**, so it has no outbox.

---

## 4. Communication

### 4.1 Synchronous and asynchronous interactions

| Interaction | Style | Why |
|---|---|---|
| Browser to services | HTTP through the gateway | The UI is request/response |
| Gateway to Identity introspection, admin scope | Synchronous on every request, no cache | Keeps immediate admin removal (SCRUM-81 AC4) |
| Gateway to Identity introspection, app scope | Synchronous, cached 15 s per session cookie, stale-if-error 240 s | Takes Identity off most of the learner hot path, so a short Identity outage degrades gracefully |
| Gateway to Identity introspection, `/api/aptitude/*` | Synchronous, uncached | `profile_completed` must be current right after a profile save |
| Services verifying JWTs | Local; the public key comes from config | No runtime dependency on Identity |
| All cross-domain state changes | Asynchronous events through RabbitMQ | Failure isolation and loose coupling |
| Rebuild or recovery | Asynchronous: the producer republishes | One data path; no internal HTTP |

The only synchronous call between components is gateway-to-Identity authentication. No domain service calls another.

### 4.2 Broker: RabbitMQ 4.x (`rabbitmq:4-management`, shovel plugins enabled)

- There is one durable topic exchange, `sgjio.events`, and the routing key is the event type. The dead-letter exchange is `sgjio.dlx`.
- Each consumer declares its own quorum queue, bindings and DLQ arguments in code, because a consumer owns its subscription:
  - `learning.events` ← `identity.user.*`, `content.#`
  - `content.events` ← `identity.user.deleted`
  - `notification.events` ← `identity.password_reset.requested`, `identity.admin.*`
- **Users.** In Phases 0 to 2, `definitions.json` creates the vhost, both exchanges and one broker user per service with broad permissions on the vhost. Phase 3 narrows them: Identity and Content may only write to `sgjio.events`, and each consumer may only configure and read its own queues.
- **Client.** The Python client is `pika`, which is blocking. A worker that both relays and consumes (Content) runs each loop in its own thread with its own connection, because pika connections are not thread-safe.
- **Why not the alternatives:**
  - Redis Streams has no routing, DLQ or management UI out of the box.
  - NATS JetStream would work but is less familiar to the team.
  - Kafka is heavy for this scale.

### 4.3 Event envelope (a JSON body; the AMQP `message_id`, `type` and `x-correlation-id` header mirror it)

```json
{"event_id":"uuid","type":"content.lesson.changed","schema_version":1,
 "occurred_at":"2026-11-10T08:00:00Z","producer":"content",
 "aggregate_type":"lesson","aggregate_id":"uuid","aggregate_version":7,
 "correlation_id":"req-…","data":{...}}
```

### 4.4 Event catalogue (all version 1; schemas in `contracts/events/*.schema.json`)

| Event | Producer | Consumers | `data` fields | Emitted when |
|---|---|---|---|---|
| `identity.user.registered` | Identity | Learning | user_id, role, user_type (null for admins), registered_at | register, Google sign-up, admin invite, `create-admin`, seed, `republish-learners` |
| `identity.user.deleted` | Identity | Learning, Content | user_id, deleted_at | delete-account, demo cleanup |
| `identity.password_reset.requested` | Identity | Notification | user_id, email, name, audience (app or admin), method (password or google), link and expires_in_minutes (method=password), sign_in_url (method=google) | forgot-password for an existing account |
| `identity.admin.invitation_issued` | Identity | Notification | admin_id, email, name, inviter_name, link, expires_in_hours, trigger (invited, resent, restored or forgot_password) | invite, resend, restore, or forgot-password by an admin who has not yet accepted |
| `identity.admin.removed` | Identity | Notification | admin_id, email, name, remover_name | remove admin |
| `content.topic.changed` | Content | Learning | topic_id, name, description, position, is_archived | create, rename, describe, archive, restore, reorder (each moved topic), import, seed, republish |
| `content.topic.deleted` | Content | Learning | topic_id | delete (only a topic that never had lessons or questions) |
| `content.lesson.changed` | Content | Learning | lesson_id, key, topic_id, level, position, display_title, publication_state (published or withdrawn), learner_visible, first_published_at, published_at, withdrawn_at, latest_version_id, latest_version_number | Only for lessons published at least once: publish, withdraw, restore, draft title change, topic move, reorder, archive or restore of its topic, republish |
| `content.lesson_version.published` | Content | Learning | version_id, lesson_id, number, title, summary, published_at, doc (full; each question annotated with `scored` and `correct_option_id`), reading_seconds, scored_questions, assets `{id:{kind,url,width,height,duration_ms,…}}`, cards_plain_text[] (one per card, in order) | A publish that creates a version, and republish. Re-publishing a withdrawn lesson with no changes emits only `lesson.changed` |
| `content.aptitude_question.changed` | Content | Learning | question_id, topic_id, level, prompt, options[{id,text}], correct_option_id, is_active, seed_key | create, update (including a topic move), activate, deactivate, seed, republish |
| `content.aptitude_bank.changed` | Content | Learning | ready, topics[{topic_id, ready}] (in admin order) | after any question change, topic archive or restore, seed, republish |

The aggregate version travels in the envelope (`aggregate_version`). For the bank it is `revision`. Version events carry the version number in their data.

Sensitive payloads (one-time links, correct answers, email addresses) travel only on the internal broker network. Messages are not logged at INFO level, and the notification DLQ has a TTL.

### 4.5 Internal service authentication

**End-user identity is an RS256 JWT minted by Identity at introspection.**
- Claims: `iss=sgjio-identity`, `aud=sgjio-services`, `sub`, `scope` (app or admin), `role`, `user_type`, `profile_completed`, `iat`, `exp`, `jti`. The header carries a `kid`.
- `exp` is 300 s for the app scope, which covers the 15 s cache plus the 240 s stale-if-error window, and 60 s for the admin scope. 10 s of clock leeway is allowed.
- Only Identity holds the private key (`JWT_PRIVATE_KEY_FILE`). Content and Learning load the public key from `JWT_PUBLIC_KEY_FILE`.
- `scripts/dev-keys.sh` generates the key pair into `./secrets/`, which git ignores, and is required. Compose mounts the files as secrets, and CI generates a pair for each run.
- Services never trust plain identity headers.
- A JWKS endpoint with key rotation is the recorded production upgrade path.

**Gateway to introspection:**
- The gateway sends a static key in `X-Service-Key`, which Identity checks against `SERVICE_KEYS`.
- `/internal/*` is never routed by the gateway, and service host ports are bound to 127.0.0.1 in dev.
- The production upgrade path is mTLS.

---

## 5. Gateway and auth

### 5.1 How sessions work after the split

1. **Sign-in flows stay in Identity.** Sign-in, register, Google, invite-accept and reset are handled by Identity exactly as today. Identity sets `sgjio_session` (Path `/api`) or `sgjio_admin_session` (Path `/api/admin`), and nginx passes the cookie through. Names, paths, attributes and lifetimes are unchanged, and the browser still sees one origin.
2. **The scope is chosen by path** for Content and Learning routes:
   - `/api/admin/*` runs `auth_request /_auth/admin`, which reads only `sgjio_admin_session` and is never cached.
   - `/api/aptitude/*` runs `/_auth/app_fresh`, which reads `sgjio_session` and is not cached.
   - Every other app route runs `/_auth/app`, which reads `sgjio_session` and is cached.
   - An app cookie can therefore never open an admin route (SCRUM-68 AC6).
3. **The internal auth locations** are marked `internal;` and set:
   - `proxy_pass_request_body off; proxy_set_header Content-Length "";`
   - Only `Cookie`, `X-Request-ID`, `X-Forwarded-For` and `X-Service-Key` are forwarded, so uploads are never streamed to Identity.

   `/_auth/app` adds:
   - `proxy_cache auth` (a tmpfs zone) and `proxy_cache_key $cookie_sgjio_session`
   - `proxy_cache_bypass $no_session_cookie; proxy_no_cache $no_session_cookie;`
   - `proxy_ignore_headers Set-Cookie;`, which lets a response carrying a refresh be cached. Replaying the same token's refresh within 15 s is harmless.
   - `proxy_cache_use_stale error timeout updating;`. Freshness and the stale limit come from Identity's `Cache-Control: max-age=15, stale-if-error=240`, so Identity decides the cache policy.
4. **Identity runs today's `resolve_session` checks:** expiry, the sliding extension (written at most once a minute), `is_removed`, and `is_admin` for the admin scope.
5. **nginx forwards the result.** `auth_request_set` copies `X-Principal-Token` into `Authorization: Bearer …` on the proxied request, and copies the `Set-Cookie` header into the response (`add_header Set-Cookie $auth_cookie always`; an empty value is skipped). This keeps today's sliding expiry. Phase 1 stream D must check that `$upstream_http_set_cookie` is filled on cache hits. If it is not, the refresh still happens on every cache miss (at least every 15 s), which is enough.
6. **Errors.**
   - A `401` from introspection becomes `401 {"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}`, byte-identical to today.
   - If Identity is unreachable and there is no usable stale entry, the result is `503 {"detail":{"code":"service_unavailable",…}}`, so `AuthProvider` shows its error state rather than signing the person out.
7. **In the services**, `Depends(require_user)` becomes `Depends(require_principal("app"))`, and `require_admin` becomes `require_principal("admin")`. These verify the signature, `aud`, `exp` and scope, and for admin also `role=admin`. Handlers that used `user.id` use `principal.user_id`.
8. **Identity's own protected routes** (`/me`, change-password, delete-account, `/profile`, `/intro`, `/admins`) keep the in-process checks, and the gateway sends them straight through. Sign-out and password changes therefore take effect immediately on Identity routes.
9. **Google sign-in.** Only Identity needs `FIREBASE_PROJECT_ID`, google-auth and network access to Google's JWKS. Tests still patch `google._decode_token`.
10. **Client IP.** nginx overwrites rather than appends: `proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Real-IP $remote_addr;`. Identity's uvicorn trusts only the gateway's fixed address on the compose network. A forged header therefore cannot reach `login_attempts.ip_address` (String(45)). `record_attempt` also truncates to 45 characters as a backstop.
11. **Body limits.**
    - The default is `client_max_body_size 10m`. Today FastAPI has no limit, and 10 MB covers the largest lesson draft PATCH with a wide margin.
    - `/api/admin/media` allows `20m`. Files between 15 and 20 MB reach Content, which returns today's JSON `media_too_large`.
    - Anything larger hits `error_page 413 = @too_large`, which returns `{"detail":{"code":"media_too_large","message":"That file is too large. The limit is 15 MB."}}` on the media location, and `payload_too_large` elsewhere. The limit number is rendered from env.

### 5.2 Routing table (nginx; regex locations are listed first and win over prefixes)

| # | Location (nginx) | Methods | Service | Gateway auth |
|---|---|---|---|---|
| 1 | `~ ^/api/admin/lessons/[^/]+/insights$` | GET | learning | admin |
| 2 | `~ ^/api/lessons/[^/]+/reports$` | POST | content | app (cached) |
| 3 | `/api/auth/` | all | identity | none (Identity checks itself) |
| 4 | `/api/admin/auth/` | all | identity | none |
| 5 | `/api/admin/admins` | all | identity | none (in-process `require_admin`) |
| 6 | `= /api/admin/ping` | GET | identity | none |
| 7 | `/api/profile` | GET, PUT | identity | none |
| 8 | `/api/intro/` | POST | identity | none |
| 9 | `/api/admin/topics` | all | content | admin |
| 10 | `/api/admin/lessons` | all | content | admin |
| 11 | `/api/admin/media` | POST | content | admin; `client_max_body_size 20m`; read timeout 60 s; JSON 413 |
| 12 | `/api/admin/reports` | all | content | admin |
| 13 | `/api/admin/aptitude-questions` | all | content | admin |
| 14 | `/api/media/` | GET | content | public: `Authorization` stripped; Range and If-None-Match pass through; optional immutable proxy cache (Phase 3) |
| 15 | `/api/lessons/` | GET, POST | learning | app (cached) |
| 16 | `/api/attempts/` | POST | learning | app (cached) |
| 17 | `= /api/progress` | GET | learning | app (cached) |
| 18 | `/api/topics/` | GET | learning | app (cached) |
| 19 | `= /api/search` | GET | learning | app (cached) |
| 20 | `= /api/review` | GET | learning | app (cached) |
| 21 | `/api/aptitude/` | all | learning | app (uncached, `/_auth/app_fresh`) |
| 22 | `= /api/health` | GET | gateway | public `{"status":"ok"}` (gateway liveness only) |
| 23 | `/_auth/app`, `/_auth/app_fresh`, `/_auth/admin` | (internal) | identity `/internal/auth/{app,admin}` | `internal;`, no body |
| 24 | everything else | | gateway | `404 {"detail":"Not Found"}` (FastAPI's shape) |

**Implementation notes:**
- Upstreams are resolved per request (`resolver 127.0.0.11 valid=10s` with `set $upstream http://content:8000; proxy_pass $upstream;`), so nginx starts and keeps serving other routes when a service is down.
- `proxy_intercept_errors off`, so service errors pass through unchanged (409 `lesson_updated`, 429 lockout with `Retry-After`, 422 and so on). `error_page` is used only for errors the gateway itself generates (401, 413, 502, 503, 504).
- **Correlation id:** `map $http_x_request_id $req_id { "" $request_id; default $http_x_request_id; }`. It is set on the upstream request and the auth subrequest, and returned to the client.
- Logs are JSON (`log_format escape=json`).
- **Timeouts:** connect 2 s, read 15 s (60 s for media upload), auth subrequest 2 s.
- **Two configs from one image.** `templates/services.conf.template` and `templates/legacy.conf.template` are both rendered by the official image's envsubst. An entrypoint snippet links `GATEWAY_MODE=services|legacy` to the active config. Legacy mode routes every `/api/*` to `legacy-api` without `auth_request`, and is used in Phases 0 to 2 (see section 10).
- **Why nginx:**
  - It is declarative and well proven at streaming Range requests and multipart uploads.
  - `auth_request` plus `proxy_cache` express forward-auth with an introspection cache in configuration alone.
  - There is no gateway code to maintain.
  - Traefik would need extra middleware to produce JSON errors, and Kong needs plugins or a datastore.
  - A small Python gateway remains the fallback (see the open questions).

---

## 6. Repository and code layout on the branch

```
sgjio/  (branch arch/microservices)
  services/
    gateway/      Dockerfile (FROM nginx:1.27-alpine), templates/{services,legacy}.conf.template,
                  errors/*.json, docker-entrypoint.d/10-mode.sh, tests/ (curl checks vs stub upstreams)
    identity/     Dockerfile, .dockerignore, requirements.txt, requirements-dev.txt, vendor/sgjio_chassis-*.whl,
                  pyproject.toml (ruff, pytest), alembic.ini, alembic/ (0001_baseline incl. outbox),
                  app/ (main, config, db, models, schemas, auth/, admins, security, privacy, profile_options,
                  principal_token, events, worker, cli, seed, routers/{auth,profile,onboarding,admins,internal}),
                  tests/, .env.example
    content/      same skeleton; app/{topics,lessons,lesson_doc,media,reports,content_import,aptitude_bank,
                  problems,projections,events,consumers,worker,cli,seed}.py,
                  routers/{admin_topics,admin_lessons,admin_media,admin_reports,admin_aptitude,media,reports}.py
    learning/     same skeleton; app/{learning,progress,review,exemptions,insights,aptitude,demo,
                  published_doc,read_models,consumers,worker,cli,seed}.py,
                  routers/{lessons,progress,review,aptitude,insights}.py
    notification/ same skeleton without routers; app/{mailer/,consumers,worker,cli}.py
  libs/chassis/   sgjio_chassis source, tests/, CHANGELOG.md; scripts/release-chassis.sh builds the wheel
  contracts/      events/*.schema.json, events/examples/*.json (lesson_version examples GENERATED by Content's
                  test from real lessons), principal-jwt.md, errors.md, internal-api/identity.openapi.yaml
                  (introspection only), seed.md (deterministic id convention)
  e2e/            pytest suite against http://localhost:8000 + Mailpit API (public APIs only)
  infra/          rabbitmq/{definitions.json,rabbitmq.conf,enabled_plugins}, postgres/init-test-db.sql
  scripts/        dev-keys.sh, seed-all.sh, chaos-drill.sh, migrate-from-monolith.sh (optional), release-chassis.sh
  secrets/        (gitignored) jwt_private.pem, jwt_public.pem
  docker-compose.yml, docker-compose.override.yml (dev: bind mounts + --reload), docker-compose.ci.yml
  web/ admin/ packages/ content/ docs/   (front ends unchanged; content/ is the import input)
  api/            kept until the end of Phase 2 as legacy-api, then deleted on the branch
```

**Code and dependencies:**
- **Independence.** Each service is built from its own directory (`docker build services/<svc>`). Nothing outside it is copied in. Services keep the package name `app`, so moved files keep their imports. Services never import each other's code; the layout enforces this and a CI grep checks it.
- **Python 3.11 throughout.** Each service has its own `requirements.txt`:
  - Identity: fastapi, uvicorn, sqlalchemy, psycopg, alembic, pydantic-settings, argon2-cffi, email-validator, google-auth, requests, pika, chassis
  - Content: the core stack plus pillow, python-multipart, mutagen, pyyaml, pika, chassis
  - Learning: the core stack plus pika and chassis
  - Notification: sqlalchemy, psycopg, alembic, pydantic-settings, pika, chassis
- **Dockerfile per service:** `python:3.11-slim`, a non-root user, `pip install --require-hashes -r requirements.txt` (the chassis wheel comes from `./vendor`), and two commands:
  - `api` runs `alembic upgrade head` and then uvicorn.
  - `worker` runs `python -m app.worker`.
- **Alembic.** Each service has a fresh `0001_baseline` generated from its own models, with no cross-service foreign keys. `env.py` imports only that service's models. The outbox and processed_events tables belong to the service's models, so a chassis release can never change a service's schema.

**Config (one `config.py` and one `.env.example` per service):**
- **Identity:** `DATABASE_URL`, `BROKER_URL`, `WEB_URL`, `ADMIN_URL`, `COOKIE_SECURE`, `APP_SESSION_DAYS`, `ADMIN_SESSION_HOURS`, `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_MINUTES`, `RESET_TOKEN_MINUTES`, `INVITE_LINK_HOURS`, `ADMIN_EMAIL_DOMAIN`, `FIREBASE_PROJECT_ID`, `SEED_*`, `JWT_PRIVATE_KEY_FILE`, `JWT_APP_TTL_SECONDS`, `JWT_ADMIN_TTL_SECONDS`, `AUTH_CACHE_SECONDS`, `AUTH_STALE_SECONDS`, `SERVICE_KEYS`, `TRUSTED_PROXY`
- **Content:** `DATABASE_URL`, `BROKER_URL`, `JWT_PUBLIC_KEY_FILE`, `MEDIA_MAX_*`, `CONTENT_DIR`
- **Learning:** `DATABASE_URL`, `BROKER_URL`, `JWT_PUBLIC_KEY_FILE`
- **Notification:** `DATABASE_URL`, `BROKER_URL`, `EMAIL_BACKEND`, `SMTP_*`, `EMAIL_FROM`
- **Gateway:** `GATEWAY_MODE`, upstream hostnames, `GATEWAY_SERVICE_KEY`, `MEDIA_LIMIT_MB`

**The only shared code is `libs/chassis` (the microservice chassis pattern), released as a versioned wheel.**
- **Contents:**
  - (a) `Principal` and `require_principal(scope)`, which verify against a configured public key
  - (b) the `Problem` exception and handler, which produce the wire error shape
  - (c) a correlation-id middleware and a JSON log formatter
  - (d) `/health/live` and `/health/ready` routers
  - (e) `emit(session, outbox_table, …)` and `run_relay(outbox_table, …)`, which take the service's own table
  - (f) a consumer base that declares the queue, its bindings and DLQ arguments, enforces the delivery limit, uses one connection per thread, and accepts an optional `dedupe(session, event_id)` hook (used by Notification)
  - (g) test helpers: an RSA test key, `mint_token()` and an envelope factory
- **What it never contains:** no DDL, no domain types and no event payload models. Payload models live in each service; JSON Schemas live in `contracts/`.
- **Distribution.**
  - `scripts/release-chassis.sh` builds `sgjio_chassis-X.Y.Z-py3-none-any.whl` and records its sha256 in `libs/chassis/CHANGELOG.md`.
  - Each service vendors the wheel it uses in `services/<svc>/vendor/` and pins it with its hash.
  - Upgrading a service is a PR to that service only, so services move at their own pace.
  - A change to `libs/chassis` runs only the chassis tests.
  - GitHub Packages has no PyPI registry, and a git-URL dependency needs repository credentials inside every Docker build, so the vendored wheel is the simplest artefact that keeps each image self-contained.
- **Justification.** The plumbing is identical in every service, security-sensitive (token verification) and easy to get subtly wrong four times. The pure alternative is copying about 400 lines into each service. This is recorded as a trade-off.

---

## 7. Local runtime

### 7.1 docker-compose topology (one network `sgjio`; dev host ports bound to 127.0.0.1)

| Container | Image | Host port | Healthcheck | depends_on |
|---|---|---|---|---|
| gateway | services/gateway | 8000 | `wget /api/health` | services *started* (not healthy), so the gateway runs even with a service down |
| identity-api | services/identity | 8001 (`/docs`) | `/health/ready` (DB) | identity-db healthy |
| identity-worker | services/identity `worker` | – | `python -m app.cli health` | identity-api healthy, rabbitmq healthy |
| content-api | services/content | 8002 (`/docs`) | `/health/ready` | content-db healthy |
| content-worker | services/content `worker` | – | cli health | content-api healthy, rabbitmq healthy |
| learning-api | services/learning | 8003 (`/docs`) | `/health/ready` | learning-db healthy |
| learning-worker | services/learning `worker` | – | cli health | learning-api healthy, rabbitmq healthy |
| notification-worker | services/notification | – | cli health (DB and broker) | notification-db healthy, rabbitmq healthy |
| identity-db, content-db, learning-db, notification-db | postgres:16-alpine | 5433, 5434, 5435, 5436 | `pg_isready` | – |
| rabbitmq | rabbitmq:4-management | 5672, 15672 | `rabbitmq-diagnostics -q ping` | – |
| mailpit | axllent/mailpit | 1025, 8025 | – | – |
| legacy-api, legacy-db (Phases 0 to 2 only, compose profile `legacy`) | today's api/, postgres:16 | – | `/api/health` | – |

**Notes:**
- Each Postgres container also creates `<svc>_test` through `infra/postgres/init-test-db.sql`, for local pytest.
- `postgres:16-alpine` idles at about 30 to 50 MB, so four of them cost about 200 MB.
- **Startup order:** the databases and the broker, then the api containers (migrate, then serve), then the workers, then the gateway. A worker never starts against a database that has not been migrated.
- **Development:** `docker-compose.override.yml` bind-mounts `services/<svc>/app` and runs `uvicorn --reload`. The front ends still use `npm run dev:web` and `npm run dev:admin`, with Vite proxies on `localhost:8000`, which is now the gateway.
- `dev.local` runs `scripts/dev-keys.sh` if the keys are missing, then `docker compose up -d --build --wait`, then optionally `scripts/seed-all.sh`, then the two Vite servers.

### 7.2 Seed and command-line tools per service

| Service | Commands (`docker compose exec <svc>-api python -m app.cli …`) |
|---|---|
| Identity | `seed` (admin, newcomer and test personas with profiles and `intro_finished_at`); `create-admin`; `send-reset`; `seed-demo-learners --count 60`; `clear-demo-learners`; `republish-learners`; `health` |
| Content | `seed` (topics, `import-lessons --publish` from `/srv/content`, aptitude bank); `import-lessons [folder] [--publish]`; `prune-media`; `republish-catalog`; `health` |
| Learning | `seed` (seed-user completions, persona aptitude attempts and exemptions); `demo-activity`; `reset-read-models`; `wait-for-read-models`; `health` |
| Notification | `health` |

**How seeding works across services:**
- **Deterministic ids.** Seed and demo users get `uuid5(NAMESPACE_URL, "sgjio:user:" + email)` (documented in `contracts/seed.md`), so Learning's seed can refer to them without calling Identity.
- **Natural keys.** Learning finds lessons by `learnable_lessons.key`, topics by name and questions by `seed_key` in its read models. `seed` waits until the read models have caught up (60 s timeout).
- **`scripts/seed-all.sh`** runs Identity `seed`, then Content `seed`, then Learning `seed`.
- **Demo activity** runs three steps:
  1. Identity `clear-demo-learners` publishes `user.deleted`, and Learning purges those learners.
  2. Identity `seed-demo-learners` publishes `user.registered`. The deterministic ids are reused, so step 1 must purge before any new writes, and `erased_learners` must not block the demo ids. To allow that, demo learners get `uuid5(…, email + ":" + run_nonce)`, a fresh id each run, passed to Learning through an argument.
  3. Learning `demo-activity --run-nonce …` waits for the 60 learners and writes their attempts.
- The seed logins stay `newcomer@sgjio.example.com` / `UserPass123` and `admin@sgjio.example.com` / `AdminPass123`.

### 7.3 Data migration from the existing single database (optional; re-seeding is the default for the branch)

`scripts/migrate-from-monolith.sh --source postgresql://sgjio:sgjio@localhost:5432/sgjio` is a one-off, offline ETL. It is not a runtime path and adds no command to any service.
1. With `pg_dump --data-only -t <tables>`, it copies each service's own tables from the old database into that service's database, keeping the same UUIDs.
2. Content backfills `version = 1` and `aptitude_bank_state.revision = 1`. It sets `topics.assessed_at` for every topic that has a question, or that is referenced by a `topic_exemptions` row in the source. This is the one place the old shared database is read across domains, and it happens once, offline.
3. It runs Content `republish-catalog` and Identity `republish-learners`, then Learning `wait-for-read-models`.
4. It compares row counts with the source and runs the e2e smoke test.

---

## 8. Testing and CI

### 8.1 Per-service suites (porting the existing ~547 test functions / ~647 cases)

| Service | Test files ported | Approx. functions | Fixture strategy and new tests |
|---|---|---|---|
| Identity | test_auth, test_register, test_lockout, test_passwords, test_password_reset, test_password_reset_routes, test_google_sign_in, test_admins, test_profile, test_intro, test_account_security | ~135 | Its own database and `make_user`. Email assertions become "outbox row of type X with payload Y". The deletion test checks that the Identity rows are gone and a `user.deleted` row exists. New: introspection (scope separation, removed admin, sliding `Set-Cookie`, claims, `Cache-Control` per scope), `republish-learners`, and IP truncation |
| Content | test_admin_topics, test_admin_lessons, test_admin_lesson_drafts, test_lesson_doc, test_lesson_levels, test_lesson_publishing, test_media, test_content_import, test_reports, the bank part of test_aptitude | ~223 | Clients send `Authorization: Bearer mint_token(...)`. New: every mutation emits the expected event and bumps `version`; payloads validate against `contracts/events`; topic archive fans out `lesson.changed`; `learner_visible` truth table; `aptitude_bank.changed` after question edits; moving a topic's last question away and then deleting the topic gives `topic_not_empty`; the `user.deleted` consumer; `republish-catalog`. A generator test projects every lesson in `content/` and writes or validates `contracts/events/examples/content.lesson_version.published.*.json` |
| Learning | test_learning, test_progress, test_topic_lessons, test_exempted_lessons, test_exemptions, test_levels, test_suggestion, test_lesson_search, test_review, test_aptitude_results, the engine part of test_aptitude, test_insights, test_demo | ~170 | Fixture factories build envelopes from the contract examples (generated ones for decks) and **run them through the real consumer handlers**. Principals come from minted tokens. New: duplicate event, stale version ignored, topic tombstone, an impossible topic delete raises, `user.deleted` purge, `user.registered` after erasure is ignored, a finish interleaved with the purge (two connections) leaves no rows, reset and republish, insights for an unseen lesson returns the empty shape, a not-ready `quiz_bank` gives today's message, the search snippet comes from the second card |
| Notification | (new) | ~12 | Example events in, memory backend: template, recipient and link checked; a duplicate event sends once; an SMTP failure is nacked and lands in the DLQ; `method=google` uses the Google template |
| Chassis | (new) | ~25 | Token verification (expiry, audience, scope, leeway), relay against a fake channel, consumer DLQ arguments, dedupe hook |
| Gateway | (new) | ~15 curl checks | Against stub upstreams: routing table rows 1–24, the auth subrequest has an empty body, JSON 401/413/503, `X-Forwarded-For` overwritten, `Authorization` stripped on `/api/media`, an app-scope cache hit within 15 s, admin never cached |
| Retired | test_migration_0004/0005/0007/0012 (monolith history). test_health_and_schema and test_seed are rewritten per service | | |

### 8.2 Contracts

- **Event contracts** live in `contracts/events/*.schema.json`, with at least one example per event. Producer tests validate every emitted payload against its schema, and consumer tests feed every example through their handler. A schema change therefore breaks whichever side is out of date. The deck examples are generated from real lessons by Content's test, so Learning's fixtures cannot drift from what Content really emits.
- **The internal HTTP contract** is `contracts/internal-api/identity.openapi.yaml` (introspection only). Identity tests its responses against it, and the gateway's stub upstream serves its examples.
- The shared aptitude-readiness fixture from the first draft is removed, because readiness now has a single owner.

### 8.3 End-to-end (`e2e/`, against the full compose stack through `:8000`, public APIs only)

1. Register, `/me`, save the profile, finish the intro, `GET /api/progress`, then `POST /api/aptitude/start` immediately after the profile save (proves the uncached aptitude auth).
2. Scope separation: an app cookie on `/api/admin/topics` gives 401, and an admin cookie on insights gives 200.
3. Admin removal: the removed admin's next Content request gives 401 at once.
4. Sliding cookie: a Learning response carries `Set-Cookie: sgjio_session` when a refresh is due. Identity's refresh interval is lowered by a CI env var.
5. The admin creates and publishes a lesson. The learner polls `GET /api/lessons/{id}` until 200 (and the body has no `correct` flags), starts an attempt, answers (graded on the server) and finishes. The progress circle goes up.
6. Withdraw: the circle drops after polling. Re-publish: the completion is still there.
7. Report a card: the admin lists it.
8. Deletion through public APIs:
   - The learner completes a lesson and files a report, then deletes the account.
   - The email can be registered again at once.
   - Polling the admin insights for that lesson shows the run and learner counts drop.
   - `GET /api/admin/reports` shows the report with no reporter.
9. Forgot password: the Mailpit API shows the email, and the link resets the password. A Google-only account gets the Google reminder.
10. Upload media. `Range: bytes=0-99` gives 206, and `If-None-Match` gives 304. A 21 MB upload gives a JSON `media_too_large`.
11. Run `demo-activity`; insights shows the figures and the Newcomer/Singaporean split.
12. Move an aptitude question out of its topic, then try to delete the topic: 409 `topic_not_empty`.

**Resilience drills** (`e2e/test_resilience.py`, marked `resilience`, and `scripts/chaos-drill.sh` for the live demo) stop one container at a time and check the degradation described in section 9. One drill stops Identity and shows that a learner who signed in just before keeps working for a few minutes.

### 8.4 CI (`.github/workflows/ci.yml` on the branch; triggers on `pull_request` and on pushes to `main` and `arch/microservices`)

- **`contracts`:** `check-jsonschema` validates the schemas and examples.
- **`chassis`:** ruff, pytest, a wheel build, and a check that each `services/*/vendor/*.whl` hash appears in `CHANGELOG.md`.
- **`service`** (matrix over identity, content, learning and notification):
  - a `postgres:16` service container
  - `pip install -r services/$svc/requirements-dev.txt`
  - `ruff check` and `ruff format --check`
  - `alembic upgrade head && alembic check`
  - `pytest`
  - `docker build services/$svc`, which proves the service builds on its own
  - `dorny/paths-filter` runs a service's job only when `services/$svc/**` or `contracts/**` changed. A chassis change does not trigger the services, because they pin their own wheel.
- **`gateway`:** render both templates, run `nginx -t`, and run the curl checks against stub upstreams.
- **`e2e`** (needs every job above):
  - `scripts/dev-keys.sh`
  - `docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait`
  - `scripts/seed-all.sh`
  - `pytest e2e -m "not resilience"`
  - On failure, upload `docker compose logs`.
- **`resilience`:** nightly or `workflow_dispatch`.
- **`web`:** unchanged.

---

## 9. Observability and resilience

**Correlation ids:**
- nginx takes the client's `X-Request-ID` or generates one.
- It sends the id upstream and to the auth subrequest, and returns it to the client.
- The chassis middleware binds it to the logs and stores it in outbox rows. From there it goes into the event envelope and the AMQP header, and consumers bind it while handling the event.
- One id therefore follows a request from the browser through the gateway, the service, the outbox, the broker and the consumer, and on to Notification.

**Logging:**
- One JSON line per log entry on stdout, with `ts`, `level`, `service`, `request_id`, `user_id` (when known), `event_id`, `type` and `aggregate_version` (in workers), and `msg`.
- nginx logs JSON too, including `upstream_cache_status` for the auth subrequest.
- `docker compose logs -f | grep <request_id>` follows a request from end to end.
- Loki and Grafana are a future step.

**Health checks:**
- `/health/live` means the process is up.
- `/health/ready` means the database answers. For workers, the command-line check also requires an open broker connection.
- Compose uses the ready checks.
- The gateway's `/api/health` reports only the gateway's own liveness.
- The RabbitMQ UI shows queue depth and the DLQs.

**Timeouts and retries:**
- **Gateway:** the timeouts in section 5. It never retries, because routes such as finish attempt and publish are not idempotent.
- **Auth cache:** serves stale entries for up to 240 s when Identity errors.
- **Relay:** exponential backoff up to 5 s while the broker is down. Rows stay in the outbox until published.
- **Consumers:** requeue up to a delivery limit of 5, then the DLQ.
- **Recovery:** republish, or move the messages in the RabbitMQ UI.

**Behaviour when a component is down:**

| Down | Still works | Degrades | User sees |
|---|---|---|---|
| Identity | Media (public). Learners who made a request in the last ~4 min keep using Learning and Content routes (stale auth cache). Events already in the outbox are sent once it recovers | Sign-in, registration, profile, admin (the admin scope is never cached), the aptitude test, and app routes for sessions not in the cache | `AuthProvider` error state (503 JSON), not a sign-out |
| Content | Learners: decks, answering, finishing, progress, topic page, search, review, the aptitude test (all from Learning's read models); auth; profile | Admin authoring, report-a-problem, media files (unless the optional gateway media cache has them) | Admin pages show `ErrorState`. Lesson images and audio fail to load, but text and questions work |
| Learning | Auth, profile, intro, all admin authoring, reports, media | Learner pages, insights | Existing `ErrorState` with retry. Events queue and apply on recovery |
| Notification | Everything else | Email | Email arrives late. A 5-minute reset link may expire |
| RabbitMQ | All HTTP | Replication and email | Learners see the catalogue as it was. The outboxes drain automatically when it returns |
| One service's DB | The other services | That service only | As for that service |
| Gateway | Nothing for browsers (the single entry point) | Everything | Network error. This is inherent and the same as the monolith being down |

---

## 10. Migration plan

**Approach: build in parallel against agreed contracts, run the new stack beside the monolith, and switch between them with one flag until the new stack is proven.**
- During Phases 0 to 2 the gateway can front either the untouched monolith (`GATEWAY_MODE=legacy`) or the new services (`GATEWAY_MODE=services`).
- The old test suite stays the behaviour oracle throughout.
- A route-by-route strangler with a shared database was rejected, because it would break database-per-service for a long time.

Rough timeline: about 7 working days for 4 to 5 people with AI help.

### Phase 0: Foundations (day 1, three people in parallel; the lead reviews)

1. **Lead.** Agree the branch base (see the open questions) and create `arch/microservices` from it. Feature branches come off it, and PRs go into it with green CI. Nothing is pushed without Yash asking.
2. **Person 1 (contracts).**
   - Write `contracts/`: the 11 event schemas, with hand-written minimal examples (the deck examples are replaced by generated ones on day 2), the principal JWT claims, `identity.openapi.yaml` (introspection), the error shape and the seed id convention.
   - Owners review the contracts at the end of the day. After that, a contract change needs the approval of its producer and its consumers.
3. **Person 2 (runtime).**
   - `infra/` and `docker-compose.yml` with the 4 service databases, RabbitMQ (definitions, shovel), Mailpit, `legacy-api` and `legacy-db` (profile `legacy`), and the gateway in `legacy` mode.
   - `scripts/dev-keys.sh`.
4. **Person 3 (chassis v0.1.0).** `require_principal`, `Problem`, logging and correlation, health, `mint_token`, their tests, `release-chassis.sh`, and the CI skeleton (contracts and chassis jobs).
5. **Lead.** One-paragraph ADR stubs in `docs/architecture/` for:
   - boundaries
   - database per service
   - RabbitMQ
   - outbox and natural idempotency
   - forward-auth with JWT and the auth cache
   - the chassis
   - read models in Learning
   - the deletion saga
   - version-based ordering

   They are finished in Phase 3.

**Exit check:**
- `docker compose --profile legacy up` runs, and both front ends work end to end through the gateway on `:8000` with no front-end change. This proves nginx handles `Set-Cookie`, Range and multipart.
- The chassis and contracts jobs are green.

### Phase 1: Build the services (days 2 to 4, four parallel streams)

**Chassis v0.2.0 on day 2** (stream D's owner or the lead): `emit` and `run_relay` (which take the service's table), and the consumer base with DLQ arguments and the dedupe hook. Streams port their tests before they need the relay and consumer loops, so this does not block them.

**A. Identity (1 person)**
1. Create the skeleton, move the files, split the models and schemas, and generate the baseline (including outbox).
2. Port the ~135 tests.
3. Add the outbox events, `routers/internal.py` (introspection with `Cache-Control`), JWT minting, IP handling, `republish-learners` and `seed`.

Exit:
- The Identity CI job is green.
- The image is healthy in compose.
- `curl` against `:8001` shows introspection returning a JWT plus `Set-Cookie`.
- `seed` creates the personas.

**B. Content (1 person)**
1. Day 2: `projections.py` and `events.py` first, plus the generator test that writes the deck examples from real lessons into `contracts/`.
2. Create the skeleton, move the files, drop the user FKs, and add the `version` and `assessed_at` columns and `aptitude_bank_state`. Generate the baseline.
3. Port the ~223 tests and add the emission and contract tests.
4. Add the `user.deleted` consumer, `republish-catalog`, `seed`, the topic-delete guard and `require_principal`.

Exit:
- The Content CI job is green.
- `seed` puts events on the exchange (visible in the RabbitMQ UI).

**C. Learning (1 to 2 people; the highest-risk stream)**
1. Create the read-model tables, `published_doc.py` and the consumers (version guard, tombstones, erasure locks), plus `reset-read-models` and `wait-for-read-models`.
2. Port `learning.py`, `progress.py`, `review.py`, `exemptions.py`, `insights.py` and the aptitude engine onto the read models and the principal.
3. Port the ~170 tests with event-fed fixtures (generated deck examples from day 3 onwards).
4. Write `seed` and `demo-activity`.

Exit:
- The Learning CI job is green.
- With Content's events flowing in compose, `GET /api/progress` on `:8003` with a minted token returns circles.
- `seed` works after Content's seed.

**D. Notification, gateway and integration scaffolding (1 person)**
1. The Notification service: consumers, templates, inbox and tests.
2. The gateway `services` template: the final routing table, the three auth locations with the app cache, JSON errors, the correlation id, `X-Forwarded-For`, body limits, and the curl checks against stub upstreams (including the `Set-Cookie`-on-cache-hit check).
3. `scripts/seed-all.sh` and the e2e harness skeleton.

Exit:
- The Notification and gateway CI jobs are green.

### Phase 2: Integration and switch-over (days 5 to 6, everyone)

1. Run the full topology beside `legacy-api`. Set `GATEWAY_MODE=services`, run `seed-all.sh`, and fix integration bugs. If something blocks the team, set `GATEWAY_MODE=legacy` and keep working against the monolith.
2. Write e2e scenarios 1 to 12 and get them green in CI.
3. Run a manual front-end checklist in both apps:
   - Learner: register (password and Google), intro, profile, aptitude test, lesson, review, search, topic page, settings, change password, delete account.
   - Admin: invite, accept, remove and restore an admin; topics; lessons (draft, publish, withdraw, reorder, move); media; reports; aptitude bank; insights.
4. Only after steps 2 and 3 are green:
   - remove the `legacy` profile and `legacy.conf.template`
   - delete `api/` on the branch
   - update `dev.local`, README, CLAUDE.md (commands, layout, the auth section), `docs/data-model.md` (one ERD per service) and CONTRIBUTING (CI)

**Exit check:** full CI including e2e is green, the checklist is signed off, and `./dev.local --seed` works from a clean clone.

### Phase 3: Hardening and presentation (day 7; items in parallel)

1. Resilience drills, automated as tests and as `scripts/chaos-drill.sh` for the live demo.
2. Least-privilege permissions for each broker user, and the DLQ runbook (move messages in the UI, or republish).
3. Optional: an immutable gateway media cache (`proxy_cache` plus `proxy_cache_use_stale error timeout`).
4. Optional: `scripts/migrate-from-monolith.sh`.
5. Finish the ADRs. Prepare the presentation material: the architecture diagram, sequence diagrams for publish-to-learner, account deletion and forward-auth with the cache, and the trade-off slide.

**Exit check:** the drills pass, and the ADRs and diagrams are done.

**Parallelisation summary:**
- Phase 0 runs 3 people in parallel (contracts, runtime, chassis), with the lead reviewing.
- Phase 1 runs streams A to D fully in parallel, because they depend only on `contracts/` and chassis releases.
- Phase 2 is joint work.
- Phase 3 is split by item.

---

## 11. Risks and trade-offs (what the course presentation should say)

1. **Eventual consistency replaces instant consistency.**
   - Publishing, withdrawing, reordering and bank edits reach learners and insights after a short delay. Account erasure completes within seconds rather than in the same commit.
   - Mitigations: the outbox, durable queues, naturally idempotent consumers, aggregate versions, tombstones, rebuild by republishing, and an erasure lock that refuses late writes.
   - We chose availability and isolation, so learners keep learning while authoring is down.
2. **Data duplication by design.**
   - Learning stores read models of the catalogue (including correct answers) and a learner directory. This is CQRS across service boundaries.
   - The alternative, synchronous composition on every learner page, would put Content on the hot path and couple their uptime.
   - Because events are designed for consumers, Content's rules (visibility, readiness) are not duplicated. Learning stores facts, not rules.
3. **Authentication remains a shared dependency.**
   - Sign-in and admin requests need Identity.
   - The app-scope cache (15 s fresh, 240 s stale-if-error) keeps learners working through short outages.
   - The cost: on Learning and Content routes, a sign-out or password change on another device takes up to 15 s to apply, and the JWT lives 5 minutes.
   - Admin removal stays immediate because the admin scope is never cached.
4. **The shared chassis is a pragmatic exception** to "share nothing". It holds plumbing only, owns no DDL, and is versioned and vendored per service, so each service upgrades independently. The pure alternative is copying it into each service.
5. **Asynchronous email.** A request never fails because of SMTP any more. During an outage, though, email can be delayed past the 5-minute reset window, and a crash can produce a duplicate email (at-least-once delivery).
6. **Security surface.**
   - One-time links, email addresses and correct answers flow over the internal broker.
   - Mitigations: network isolation, per-service broker users (least privilege in Phase 3), a TTL on the notification DLQ, short-lived signed principals, overwritten forwarding headers, and auth subrequests that carry no body.
   - Production next steps: mTLS, JWKS rotation and a secrets manager.
7. **Operational complexity.**
   - About 14 containers instead of 3, distributed debugging (correlation ids and JSON logs help), and slower cross-service tests (e2e).
   - This is the honest price at SGJio's scale, where a modular monolith is the pragmatic choice. The branch demonstrates the pattern; the load does not demand it.
8. **Branch divergence.** `main` keeps evolving (for example the personalization/levels PR), and every later change must be re-applied by hand to the right service. The team needs to agree a freeze or porting policy.
9. **Test rewrite effort and fidelity.** About 550 test functions move, and roughly 30 change their assertions (email outbox, cascades, cross-scope). Parity is proven by the ported unit tests, generated-example contract tests and the public-API e2e suite.
10. **Small, declared behaviour changes** (section 3.3 and the functionality changes). Each one is the price of a principle, and each is listed so the team can accept it consciously.
11. **Course framing: patterns, one slide each:**
    - database per service
    - API gateway with forward-auth
    - access token
    - transactional outbox
    - idempotent consumer
    - event-carried state transfer
    - CQRS read model
    - published language
    - choreographed saga
    - microservice chassis
    - health check API
    - correlation id
    - consumer-driven contracts
    - plus a resilience demo

---

## 12. Review resolutions

No issue was marked as a blocker. Every major issue and every minor issue is listed below.

### Purist lens

| # | Issue | Severity | Resolution |
|---|---|---|---|
| P1 | The ordering key `seq` was the outbox id, which breaks after pruning or migration | major | **Accepted.** Topics, lessons, questions and the bank carry an aggregate `version`/`revision`, bumped in the same transaction and sent as `aggregate_version`. Read models compare versions. The outbox id is only the relay cursor. Users need no version, because `learners` rows are immutable and erasure is permanent (insert-if-absent plus the `erased_learners` check). Sections 3.2 and 7.3 updated |
| P2 | The chassis moved in lockstep, owned DDL, and images were built from the repo root | major | **Accepted.** The chassis is a versioned wheel vendored and hash-pinned per service. Each image builds from `services/<svc>` alone. The outbox and processed_events tables live in each service's models, and the chassis takes the table as a parameter. A chassis change runs only the chassis tests. GitHub Packages has no PyPI registry, so a vendored wheel was chosen over a registry. The `content/` folder is mounted at runtime, not copied into the image |
| P3 | Events were table dumps; Content's rules were duplicated in Learning | major | **Accepted, with one functionality-preserving adjustment.** (a) `lesson.changed` carries `learner_visible`, computed by Content; topic archive and restore fan out to its lessons. (b) `content.aptitude_bank.changed` publishes readiness, and Learning's copy of the rule and the shared fixture are removed. (c) Lessons are sent only after their first publish. No `created_at`, no draft lifecycle. Tables are renamed for Learning's purpose. Adjustment: insights shows the draft title, status and topic name, so the event keeps `display_title` and `publication_state` (published or withdrawn) as display facts. Removing them would lose functionality, and they encode no rule |
| P4 | A synchronous Identity call on every request, with no degradation | major | **Accepted.** The app scope is cached in nginx per session cookie (15 s fresh, `stale-if-error=240`), with Identity setting `Cache-Control`. App JWTs last 300 s to cover the window. Admin is never cached (SCRUM-81 AC4). Aptitude routes use an uncached auth location, so the `profile_completed` claim is fresh right after a profile save; a plain cache would have broken this. The 15 s lag for sign-out and password changes is declared |
| P5 | Resurrecting a learner after a replay; check-then-insert race on erasure | minor | **Accepted.** `erased_learners` makes `user.registered` a no-op for erased users. Learner write paths take `pg_advisory_xact_lock_shared` and the purge takes the exclusive lock. An interleaving test is added |
| P6 | Notification commands named as events; inbox semantics for SMTP; personal data in the DLQ | minor | **Accepted.** `password_reset.requested {method}` replaces `google_reminder.requested`, and `admin.invitation_issued {trigger}` replaces `admin.invited`. Notification is at least once (send, then record). The notification DLQ has a 1 h TTL |
| P7 | e2e read learning-db directly | minor | **Accepted.** Scenario 8 checks erasure through admin insights and reports. Row-level erasure is covered by the consumer unit tests |
| P8 | The auth subrequest inherited the request body | minor | **Accepted.** `proxy_pass_request_body off`, an empty `Content-Length` and a header allow-list on every `/_auth/*` location, plus a gateway check |

### Functionality lens

| # | Issue | Severity | Resolution |
|---|---|---|---|
| F1 | The topic-delete invariant was false, because questions can move topics (confirmed in `schemas.py` `AptitudeQuestionUpdate.topic_id` and `aptitude.update_question`) | major | **Accepted.** `topics.assessed_at` is set when a question is first created or moved in, and never cleared. `delete_topic` refuses when the topic has lessons or `assessed_at` is set, which covers everything the FK blocked. The false invariant is removed. Learning parks an impossible `topic.deleted` in the DLQ instead of deleting exemptions. Content test and e2e scenario 12 added. The migration backfills `assessed_at` from questions and exemptions |
| F2 | HTML 413 instead of JSON `media_too_large`; body forwarded to auth | minor | **Accepted.** Media allows `client_max_body_size 20m`, and the service returns JSON for 15 to 20 MB. A JSON `error_page 413` covers larger files. The default limit is 10m with JSON `payload_too_large`. The body is not sent on auth. Added to e2e scenario 10 |
| F3 | Trusting a forged `X-Forwarded-For` could cause a 500 on String(45) | minor | **Accepted.** The gateway overwrites `X-Forwarded-For` and `X-Real-IP` with `$remote_addr`. uvicorn trusts only the gateway's address. `record_attempt` truncates as a backstop |
| F4 | The erasure race guard did not cover answer and finish, and was not serialised | minor | **Accepted.** Same fix as P5, applied to every learner write path (start, answer, finish, aptitude start, next, submit and skip) |
| F5 | Insights 404 for deleted lessons; insights lag undeclared | minor | **Resolved differently.** Deleted lessons are never sent to Learning, because only lessons that were never published can be deleted (`lessons.delete_lesson`) and those are never sent. A lesson Learning does not know returns the existing "Not published yet" shape. The UI never reaches it, because the menu hides Insights until a version exists. The insights lag and the unknown-id shape are now declared in section 3.3 and the functionality changes |
| F6 | `search_text` versus `cards_plain_text` mismatch | minor | **Accepted.** `cards_plain_text` is a JSONB array, named the same in the event, schema and table. `_snippet` loops over it unchanged, and a contract example has the match in the second card |

### Simplicity lens

| # | Issue | Severity | Resolution |
|---|---|---|---|
| S1 | Snapshot rebuild was inconsistent and over-built | major | **Accepted.** Both snapshot endpoints, their OpenAPI files, Learning's HTTP client and its service key are removed. Rebuild is `reset-read-models` followed by `republish-catalog` and `republish-learners`, through the ordinary consumer path. Combined with P1, this is consistent after pruning |
| S2 | Phase 2 left the app non-runnable | major | **Accepted.** Each stream's `seed` is part of its Phase 1 exit check, and stream D writes `seed-all.sh`. `GATEWAY_MODE=legacy` or `services` lets the new stack run beside `legacy-api` with a one-flag fallback. `legacy-api` and `api/` are removed only after e2e and the checklist are green |
| S3 | Phase 0 was overloaded and serial | major | **Accepted.** Split across three people (contracts, runtime, chassis v0.1.0). The relay and consumer base move to chassis v0.2.0 on day 2. ADRs are stubs until Phase 3. The missing `legacy-db` is added |
| S4 | Hand-written deck examples would drift | major | **Accepted.** Content builds `projections.py` and `events.py` first on day 2, with a test that generates the deck examples from the real lessons in `content/`. Learning uses those, with a minimal hand-written example until then |
| S5 | Redundant inbox in Content and Learning | minor | **Accepted.** `processed_events` stays only in Notification. Content and Learning are documented as naturally idempotent and keep their duplicate-event tests |
| S6 | JWKS fetching, refresh and ephemeral keys | minor | **Accepted.** `dev-keys.sh` is required. Identity holds the private key, and verifiers load `JWT_PUBLIC_KEY_FILE`. The `kid` stays in the header. JWKS and rotation are the production path |
| S7 | Too many containers; pika thread safety | minor | **Partly accepted.** Each loop gets its own pika connection in its own thread, as stated in section 4.2. **Rejected:** making one shared Postgres server the default. The user asked for every decision to embody a true microservice architecture, and principles beat simplicity. Separate containers show isolation (stopping one DB in the drill), and `postgres:16-alpine` costs only about 200 MB for four. Workers stay separate processes, as the reviewer agreed |
| S8 | Broker hardening too early | minor | **Partly accepted.** Phases 0 to 2 use a simple user per service with broad vhost permissions, and queues and DLQ arguments are declared in code. Least-privilege permissions move to Phase 3. `replay-dlq` is dropped in favour of the management UI's move-messages (shovel) or republishing |
| S9 | `import-from-monolith` in every service | minor | **Accepted.** Removed from every command-line tool. The optional one-off `scripts/migrate-from-monolith.sh` does a per-table data copy, then republishes |


---

## Appendix A. Decision log

| Topic | Choice | Alternatives | Rationale |
|---|---|---|---|
| Service decomposition | Four business services (Identity, Content, Learning, Notification) plus an nginx gateway. Media, reports and the aptitude bank (including its readiness rule) stay in Content. The quiz engine and insights go to Learning. Profiles stay in Identity | Separate Media, Assessment, Analytics or Community services; splitting progress from attempts | Each rejected split would add a synchronous call or a second read model without an independent business reason. Keeping readiness with the bank gives one owner for the rule. The rejected splits are recorded as future candidates |
| Shape of events between Content and Learning | A published language designed for consumers. Content computes learner_visible and aptitude-bank readiness and publishes them. Lessons are sent only after their first publish. Learning's read models are named for its own use (learnable_topics, learnable_lessons, lesson_decks, quiz_questions, quiz_bank). display_title and publication_state are kept as display facts for insights | Row-dump events mirroring Content's tables (the first draft); dropping the draft title from insights | It removes the duplicated rules and the schema coupling the purist review found. Keeping the two display facts preserves the insights header, because functionality beats simplicity, and they encode no rule |
| Read-model ordering | An aggregate version column (topics, lessons, aptitude_questions) and a bank revision, bumped in the same transaction and sent as aggregate_version. Decks and learners are insert-if-absent. The outbox id is only the relay cursor | The outbox bigserial id as seq (the first draft); timestamps | It survives outbox pruning and data migration, follows commit order through the row lock, and makes rebuilding a plain idempotent upsert |
| Rebuild and recovery | Producers republish their current state through the outbox (content republish-catalog, identity republish-learners) after an optional Learning reset-read-models | Internal snapshot HTTP endpoints pulled by Learning | One data path. No internal HTTP between domain services. Fewer contracts and less code |
| Database per service | A separate postgres:16-alpine container per service, with no cross-service foreign keys | One Postgres server with a database and role per service | It is the clearest form of the principle, the isolation can be demonstrated, and four containers cost about 200 MB. The user asked for true microservice decisions over simplicity |
| Broker | RabbitMQ 4: a topic exchange, quorum queues owned by each consumer, a delivery limit of 5, a DLX and a TTL on the notification DLQ, the management UI with shovel for replay. Least-privilege users in Phase 3 | Redis Streams, NATS JetStream, Kafka | The simplest option with durable per-consumer queues, routing, dead-lettering and a demo-friendly UI |
| Reliable publishing and consuming | A transactional outbox in Identity and Content. Content and Learning consumers are naturally idempotent (version guards, insert-if-absent, tombstones). Notification has a processed_events inbox and at-least-once delivery | An inbox in every consumer; publishing after commit; CDC | No event is lost or sent for a rolled-back change. An inbox is kept only where the side effect cannot safely repeat |
| Gateway and auth propagation | nginx auth_request to Identity introspection, with no request body, returning an RS256 JWT. App scope cached 15 s per session cookie with stale-if-error 240 s (Identity sets Cache-Control). Aptitude routes use uncached auth. Admin scope never cached. Services verify with a configured public key | Uncached per-request introspection (the first draft); long-lived JWT cookies; trusted plain headers; JWKS fetched at runtime; a custom Python gateway | Keeps immediate admin removal, the scope separation, sliding cookies, and fresh profile_completed for the aptitude test, while letting learners ride out short Identity outages. A static public key removes the runtime JWKS dependency |
| Account deletion | A choreographed saga. Identity deletes and emits user.deleted through the outbox. Learning purges under an exclusive per-user advisory lock and records erased_learners. Learner write paths take the shared lock and check erasure. Content nulls actor ids | An orchestrated saga; synchronous fan-out deletes | No step needs compensation. The locks close the in-flight write race, and the tombstone stops a replayed registration from bringing the learner back |
| Topic delete guard | topics.assessed_at is set once a question is first created or moved in, and never cleared. Deletion is refused when the topic has lessons or assessed_at is set | Relying on the invariant that questions are never deleted (false, because questions can move topics); a synchronous call to Learning | It rests on an irreversible fact local to Content and covers everything today's RESTRICT FK blocked |
| Email events | Domain facts: identity.password_reset.requested {method, audience, link or sign_in_url}, identity.admin.invitation_issued {trigger}, identity.admin.removed. Notification maps facts to templates | Notification commands named as events; a synchronous POST to Notification | Identity states what happened and Notification decides how to tell people. An SMTP outage never fails an auth flow |
| Shared code | libs/chassis as a versioned wheel vendored and hash-pinned per service. Plumbing only (principal verification, error shape, logging and correlation, health, outbox emit and relay taking the service's table, consumer base), with no DDL and no domain types | Copying about 400 lines into each service; a chassis built from the repo root and moving in lockstep (the first draft); a git-URL or registry dependency | Security-sensitive plumbing is written once, yet each service builds from its own directory and upgrades on its own schedule |
| Migration approach | Phase 0 split across three people; Phase 1 four parallel streams with seeds in each exit check; Phase 2 runs the new stack beside legacy-api with GATEWAY_MODE=legacy\|services as a fallback, and deletes api/ only after e2e and the checklist are green; Phase 3 hardens | A big-bang cutover; a strangler pattern over a shared database | Every step ends in a runnable state, there is a one-flag fallback, and the team is never idle behind Phase 0 |
| Testing | Per-service suites with minted JWTs and event-fed fixtures; deck contract examples generated from real lessons; JSON Schema checks on both producer and consumer; curl checks for the gateway; a public-API-only e2e suite; resilience drills | A Pact broker; e2e probes into service databases; one shared test database | Behaviour parity with about 550 ported tests, contracts that cannot silently drift, and e2e that respects encapsulation |

## Appendix B. Functionality changes

- Content changes (publish, withdraw, restore, topic move, reorder, archive, rename, aptitude bank edits) reach learners after a short replication delay, usually under a second, instead of instantly. If the broker or the Learning worker is down, learners see the last state until it recovers.
- Lesson insights reflect publishes, title changes and topic changes after the same delay. Right after a first publish the page may briefly show 'Not published yet'. Insights for a lesson id Learning has never seen (never published, or an id that does not exist) now returns the empty 'not published yet' shape instead of a 404. The admin UI never reaches such a page, because the menu hides Insights until a version exists.
- Account deletion: the email is freed and sign-in stops immediately, and any write by the erased user is refused at once. Learning data and lesson_reports.reporter_id are erased by event within seconds instead of in the same commit.
- Sign-out or a password change on one device stops that session immediately on Identity routes, but on Learning and Content app routes the old session may still be accepted for up to 15 seconds because of the gateway's auth cache. Admin removal is unchanged (immediate), because the admin scope is never cached.
- When Identity is briefly down (up to about 4 minutes), learners who were recently active keep using lessons, progress, search and review. Today everything fails together. Sign-in, profile, admin routes and the aptitude test still need Identity.
- Emails (password reset, Google sign-in reminder, admin invite/resend/restore, admin removed) are sent asynchronously by Notification. Requests always succeed even when SMTP fails (today an SMTP failure gave a 500 after commit). Email can be delayed, a 5-minute reset link may expire during an outage, and a crash can rarely produce a duplicate email.
- The insights learner denominator and the Newcomer/Singaporean split come from Learning's learners read model, so a newly registered learner is counted after the replication delay.
- Topic deletion is now refused for any topic that has ever had an aptitude question (even if all questions were moved away), with the same topic_not_empty code. This covers everything today's foreign key blocks, and closes a gap where a split system could have orphaned exemptions.
- Request bodies now have explicit gateway limits: 10 MB by default (today unlimited), with a JSON payload_too_large error; 20 MB on media upload, where anything over the 15 MB service limit still returns today's JSON media_too_large.
- A single /api/docs Swagger page becomes one docs page per service on development host ports. /api/health reports gateway liveness only. The front ends use neither.
- Failure isolation improves: with Content down, learners can still take lessons and see progress, review, search and the aptitude test (media and report-a-problem are unavailable). With Learning down, sign-in, profile and all admin authoring still work.
- The developer workflow changes from running uvicorn plus 'python -m app.cli' in api/ to scripts/dev-keys.sh, 'docker compose up', per-service command-line tools and scripts/seed-all.sh. dev.local, README and CLAUDE.md are rewritten. The front ends' npm scripts and Vite proxy target (:8000) are unchanged.
- Tests that relied on one TestClient holding both cookies, or on cross-domain writes in one database, move to public-API e2e tests. The monolith migration tests (test_migration_0004/0005/0007/0012) are retired on the branch.
- Existing quirks are kept on purpose: _topic_now_complete ignores exemptions, and _levels counts lessons by published state regardless of topic archive.

## Appendix C. Open questions for the team

1. Branch base: should arch/microservices start from main after the personalization (levels per skill) PR is merged or rejected, so we do not port it by hand later? While the branch lives, should main be frozen, or should later main changes be ported?
2. Branch naming: CONTRIBUTING expects SCRUM-<n> branches and commit messages. Should we create a Jira epic for the microservices work, or is a non-SCRUM long-lived branch acceptable?
3. Team allocation: Phase 0 needs three people on day 1 (contracts, runtime, chassis), and Phase 1 needs four streams. Can two people take Learning?
4. Is a 15-second lag acceptable for a sign-out or password change on another device to take effect on Learning and Content routes (Identity routes and admin removal stay immediate)? The trade-off is that learners survive short Identity outages.
5. Is committing a small vendored chassis wheel in each service acceptable, or would the team rather copy the chassis source into each service (zero shared code, more drift)?
6. nginx (configuration only) or a small Python gateway that the team can read and unit-test?
7. Async email: is it acceptable that a 5-minute reset link might expire if email is delayed by an outage? Should RESET_TOKEN_MINUTES go to 15 on this branch (a product decision for docs/decisions.md)?
8. Re-seed only, or should we also build the optional migrate-from-monolith script for existing local or demo data?
9. Swagger: are per-service docs on :8001/:8002/:8003 acceptable, or should the gateway expose /api/docs/<service>?
10. Should Learning publish learning.lesson.completed now (no consumer yet, but it shows the pattern for Portfolio/tiers, SCRUM-27), or wait until a consumer exists?
11. Is a cloud deployment needed for the presentation, or only docker compose locally?
