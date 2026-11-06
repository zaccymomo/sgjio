# ADR 0007: Learning keeps read models of content and learners

**Status:** accepted, built

## Context

Almost every learner page combines the learner's own progress with published content: the home page circles count completed lessons out of published ones per topic; a lesson must be served from its latest published version, with answers checked on the server; the quiz asks questions from the bank. If Learning asked Content over HTTP for this, every learner page would fail whenever Content was down, and it would cost a call per request.

## Decision

Learning keeps its own copies, written only by its event consumer (`app/consumers.py`):

| Read model                                                                                                | From                                                                 |
| --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `learnable_topics` (name, description, position, archived, deleted)                                       | `content.topic.changed`, `content.topic.deleted`                     |
| `learnable_lessons` (topic, level, position, title, visibility, latest version)                           | `content.lesson.changed`                                             |
| `lesson_decks` (the published deck, which options are right, reading time, assets, plain text for search) | `content.lesson_version.published`                                   |
| `quiz_questions`, `quiz_bank` (readiness, topic order)                                                    | `content.aptitude_question.changed`, `content.aptitude_bank.changed` |
| `learners` (user type, registered at), `erased_learners`                                                  | `identity.user.registered`, `identity.user.deleted`                  |

Content's events carry **conclusions, not rules**: `learner_visible`, each question's `scored` and `correct_option_id`, the reading time including audio, the readiness of the bank (`services/content/app/projections.py`). Learning therefore never needs Content's lesson rules or media code.

## Consequences

- Learner pages work, and keep working while Content is down (only lesson images and audio, served by Content, and reporting a problem, which Content records, fail).
- Admin changes reach learners after the event arrives, usually within a second (declared behaviour change). The e2e suite waits for it with `eventually(...)`.
- Read models can be rebuilt at any time: `learning reset-read-models`, then `content republish-catalog` and `identity republish-learners`. Version guards make replays safe (ADR 0004).
- `scripts/seed-all.sh` seeds Identity and Content first, then waits (`learning wait-for-read-models`) before seeding learner data.
- More storage (each published deck is stored twice) and more code in the consumer, paid for with availability and no runtime coupling.
