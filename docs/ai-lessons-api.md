# AI-generated lessons: HTTP API

The agreed shapes between `web/`, `admin/`, Learning and Content for docs/ai-lessons-plan.md. Errors use the usual `{"detail": {"code", "message", ...}}` body (contracts/README.md). Times are ISO 8601 UTC. Ids are UUIDs.

## Learning (app sign-in: `require_principal("app")`)

### Shared shapes

```jsonc
// GeneratedStatus: one request, as the Generating and Ready screens need it
{
  "id": "uuid",
  "status": "requested" | "writing" | "checking" | "ready" | "failed" | "cancelled",
  "topic": { "id": "uuid", "name": "Singlish" },
  "focus": "new" | "mistakes",
  "difficulty": "easier" | "right" | "harder",
  "length": "short" | "usual",
  "level": 2,                          // the level the brief used (1 to 5)
  "ask": "My colleagues keep asking…" | null,
  "covers": [                          // focus = mistakes: the mistakes it was built from (written by Learning)
    { "lesson_id": "uuid", "lesson_title": "Could, Can and One", "correct": "Can!" }
  ],
  "lesson": null | {                   // present once status = ready
    "title": "Can or Not? Lunch with Colleagues",
    "summary": "…",
    "learning_points": ["…", "…"],
    "cards": 6,
    "questions": 2,
    "reading_seconds": 95
  },
  "failure": null | {                  // present once status = failed
    "code": "off_topic" | "invalid_output" | "unsafe" | "provider" | "timeout",
    "message": "We can only make lessons about everyday life in Singapore, like small talk at work or ordering food."
  },
  "created_at": "…",
  "left_today": 2
}
```

`failure.message` is written by Learning, in plain language, per code (never the model's text):

| code                       | message                                                                                                                                                                 |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `off_topic`                | We couldn't create a lesson from that request. Lessons cover everyday life in Singapore, such as small talk at work or ordering food. Please rephrase it and try again. |
| `invalid_output`, `unsafe` | This lesson did not pass our quality checks, so it was not shown.                                                                                                       |
| `provider`, `timeout`      | We couldn't create this lesson right now. Please try again shortly.                                                                                                     |

Every failed or cancelled request is refunded: it never counts toward the daily limit.

**Timeout:** a request still `requested`, `writing` or `checking` `GENERATION_TIMEOUT_SECONDS` (90 by default; 180 in `docker-compose.yml`) after `created_at` is turned into `failed` / `timeout` (and saved) whenever it is read. No scheduler.

### `GET /api/generate/options`

```jsonc
{
  "daily_limit": 3,
  "left_today": 2,
  "has_generated": true,              // false: show the first-time notice
  "mistakes_total": 3,
  "pick_for_me": { "new": "uuid" | null, "mistakes": "uuid" | null },
  "topics": [                          // topics with at least one lesson learners can open, in topic order
    { "id": "uuid", "name": "Singlish", "mistakes": 3, "level": 2 }
  ]
}
```

- `topics[].mistakes`: count of `mistakes_for(user)` in that topic.
- `topics[].level`: the aptitude test's exemption level for the topic if at least 1; else the highest level among lessons the user completed there; else 1.
- `pick_for_me.mistakes`: the topic with the most mistakes (ties: the most recent mistake), or null with none.
- `pick_for_me.new`: the topic with the lowest completed/available share, the same rule as the Home suggestion's weakest topic (ties: topic order).

### `POST /api/generate` → 202 `GeneratedStatus`

```jsonc
{ "topic_id": "uuid" | null,          // null = Pick for me
  "focus": "new" | "mistakes",
  "ask": "…" | null,                   // trimmed; empty means null; at most 200 characters
  "difficulty": "easier" | "right" | "harder",
  "length": "short" | "usual" }
```

- Level: the topic's level (as above) −1 for easier (at least 1), +1 for harder (at most 5).
- Length: short = 4 cards, 1 question; usual = 6 cards, 2 questions.
- Mistakes: the topic's mistakes, newest first, at most 5.
- Errors:
  - 429 `daily_limit_reached` ("You have reached today's limit of 3 generated lessons. You can generate more tomorrow."), with `left_today: 0`;
  - 409 `no_mistakes` (focus mistakes with none in the topic);
  - 404 `topic_not_found` (no lesson learners can open in it);
  - 422 for a bad body.
- Writes the row and `learning.lesson_generation.requested` in one transaction.

### `GET /api/generate/{id}` → `GeneratedStatus`

404 `generated_not_found` for another user's or unknown id.

### `POST /api/generate/{id}/cancel` → `GeneratedStatus`

Marks a waiting request `cancelled` (refunded). A finished one is returned unchanged.

### `GET /api/generated` → list, newest first

Failed and cancelled requests are left out.

```jsonc
[ { "id": "uuid", "status": "writing" | "checking" | "requested" | "ready",
    "title": "…" | null, "topic": { "id": "uuid", "name": "…" },
    "created_at": "…", "best": { "correct": 2, "scored": 2 } | null } ]
```

### `GET /api/generated/{id}/lesson`: the deck, `ready` only (else 404 `generated_not_found`)

The same shape as `GET /api/lessons/{id}` (`LearnerLessonOut`), so `LessonDeck` takes it unchanged: `id`, `version` (always 1), `title`, `summary`, `topic`, `reading_seconds`, `cards` (no right answers; options shuffled where `shuffle`), `assets` (`{}`).

### Playing: mirrors lesson attempts exactly

- `POST /api/generated/{id}/attempts` → `{ "id": "uuid" }`
- `POST /api/generated/attempts/{attempt_id}/answers` with `{ question_id, option_id }` → `CheckResult` (`correct`, `correct_option_id`, `why_not`, `explanation`). Only the first answer to a question in an attempt counts; a repeat returns the same result.
- `POST /api/generated/attempts/{attempt_id}/finish` → `{ "attempt_id", "score": {correct, scored}, "best": {correct, scored} }`. Needs every scored question answered, as for lessons.

Nothing here touches `lesson_attempts`, `lesson_completions` or `/api/progress`.

### `POST /api/generated/{id}/rating` → 204

```jsonc
{ "useful": true | false,
  "reasons": ["right_level" | "clear" | "more_like_this" | "too_easy" | "too_hard" | "not_relevant" | "something_wrong"] }
```

At most 4 reasons. Saving again replaces the rating.

### `POST /api/generated/{id}/reports` → 201

`{ card_id, reason, note }`, with the reasons and note limit of `ReportProblemDialog` (Content's `ReportReason`). Stored in Learning; no admin screen yet.

## Content (admin sign-in: `require_principal("admin")`)

### `POST /api/admin/lessons/generate` → 202 `GenerationJob`

```jsonc
{ "topic_id": "uuid", "level": 1-5, "notes": "1 to 2000 characters", "cards": 4 | 6 | 8 }
```

- Questions: 4 cards → 1, 6 → 2, 8 → 3.
- Errors: 429 `daily_limit_reached` (20 a day per admin, Singapore date, failed ones refunded); 404 `topic_not_found` (no such active topic).
- Writes `generation_jobs` and `content.lesson_generation.requested` in one transaction.
- `check_answers` is false: a person reviews the draft.

### `GET /api/admin/generation` → `{ "daily_limit": 20, "left_today": 17 }`

The signed-in administrator's own limit, for the dialog's "N of 20 drafts remaining today" before any request exists.

### `GET /api/admin/generation/{id}` → `GenerationJob`

Any administrator can read any job (all administrators have the same access); 404 `generation_not_found` for an unknown id. Failure messages are written for administrators, per code, in `services/content/app/generation.py`.

```jsonc
{ "id": "uuid", "status": "requested" | "writing" | "done" | "failed",
  "lesson_id": "uuid" | null,          // set when done: open the editor at it
  "failure": null | { "code": "…", "message": "…" },
  "left_today": 17 }
```

The same timeout rule as Learning (`GENERATION_TIMEOUT_SECONDS`: 90 by default, 180 in `docker-compose.yml`). If the topic was archived or deleted before the result arrives, no draft is created and the job fails with `invalid_output`. When `generation.lesson.generated` arrives, Content creates the Draft through its existing lesson-creating code: same title, summary, topic, level, the `doc` with Content's own ids (`lesson_doc.assign_ids`), and `origin = "ai"`. Then it sets the job `done` with the lesson id.

### Lessons

- The admin lesson response gains `"origin": "authored" | "ai"` and `"ai_reviewed_at": "…" | null`.
- Publishing a lesson whose `origin` is `ai` and that has never been published needs `{"reviewed": true}` in the publish body. Without it: 409 `review_required` ("Tick “I have reviewed every card” before publishing an AI draft."). The first such publish stores `ai_reviewed_at` and `ai_reviewed_by`.
