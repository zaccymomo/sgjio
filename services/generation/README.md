# Generation

Writes AI lessons (docs/ai-lessons-plan.md; why it is a separate worker: [ADR 0010](../../docs/architecture/decisions/0010-generation-worker.md)). Learning (for learners) and Content (for administrator drafts) send a request event; Generation writes the lesson with the model, checks it, and answers with an event. It has no HTTP API and no gateway route: it is one worker process (`python -m app.worker`) consuming `generation.events` and relaying its outbox. It never learns who asked: requests carry a request id, a brief and lesson text only.

## Owns

Database `generation` (compose `generation-db`, host port 5438; tests use `generation_test`). It keeps no lessons.

| Table              | What                                                                                      |
| ------------------ | ----------------------------------------------------------------------------------------- |
| `outbox`           | events to publish (the platform relay)                                                    |
| `processed_events` | the inbox: the `event_id` of every request answered, so a redelivery isn't paid for twice |

## Events

Consumed (queue `generation.events`): `learning.lesson_generation.requested`, `content.lesson_generation.requested`. `requester` in every answer is the request's producer.

| Published                     | `aggregate_version` | When                                                       |
| ----------------------------- | ------------------- | ---------------------------------------------------------- |
| `generation.lesson.progress`  | 1 `writing`         | before the write call (committed at once, on its own)      |
| `generation.lesson.progress`  | 2 `checking`        | before the checks and the answer check (committed at once) |
| `generation.lesson.generated` | 3                   | the lesson, in the shape of a published version's `doc`    |
| `generation.lesson.failed`    | 3                   | `off_topic`, `invalid_output`, `unsafe` or `provider`      |

## How a request runs (`app/pipeline.py`)

0. **Screening** (learners' typed text only, `SCREEN_RULES` in `app/prompt.py`): the check model decides whether the text is a usable request about everyday life in Singapore. Gibberish, vague, off-topic or harmful text, requests for immigration help and attempts to change our instructions are refused at once (`off_topic`, usually 1 to 2 s). An unreadable verdict lets the request go on. Added because the fast writer doesn't follow refusal rules reliably (`docs/ai-model-evaluation.md`, finding 6).
1. **Write call** (`app/prompt.py`): our rules, then the brief and grounding as a data block. The learner's `ask` and the admin's `notes` are JSON-quoted data, never instructions. The model returns lesson JSON, or a refusal (`off_topic`).
2. **Checks in code** (`app/checks.py`): shape, card and question counts, 2 to 4 options with exactly one right, explanations, one `{{blank}}` at most (and only with a question), lengths, no HTML or links, banned phrases (PR, permanent residence, citizenship, ICA, immigration outcomes, "guarantee", "improve your chances", "tap" as an instruction). On failure, one retry with the problems listed; a second failure is `invalid_output`.
3. **Answer check** (only when `brief.check_answers`, i.e. learners): a second short call; not ok is `unsafe`.
4. **Result**: ids `c1`, `q1`, `o1`..., per-question facts, reading time, plain text for search.

Model trouble (timeouts, HTTP errors, empty replies) is `provider` and is acknowledged, never redelivered (beyond the one call to the fallback model), so it can't run up cost. Only bugs and database trouble raise (and are retried by the consumer). Requests are handled one at a time; the consumer keeps the broker connection alive during long model calls (`app/consumer.py`).

## The model (`app/llm.py`)

- **Fake** (default, `GENERATION_FAKE=true`): no key, no network, deterministic. Builds a valid lesson from the brief (topic name, the ask, the mistakes' correct answers). It **refuses** when the ask or notes contain, ignoring case: `pr application`, `essay`, `ignore previous`, `ignore all`, `password`, `hack`. End-to-end tests use these. Its answer check always says ok.
- **Real**: any OpenAI-compatible API over httpx (no SDK): `POST {GENERATION_BASE_URL}/chat/completions`, bearer `GENERATION_API_KEY`, temperature 0.4. If a call to the write or check model fails as `provider` (down, withdrawn, timed out), it is tried once more with `GENERATION_FALLBACK_MODEL`, when that is set and different. JSON is asked for in the prompt (no `response_format`); a reasoning model's `<think>` block and code fences are stripped from the reply and the first `{...}` is validated with pydantic. Provider: NUS SoC LaaS (https://soclaas-api.comp.nus.edu.sg/, NUS network or VPN only). With fake off and the URL or key missing, every request fails `provider` and the worker logs a warning. The key is never logged; prompts and replies are logged only at DEBUG.

## Settings

| Variable                     | Default | What                                                       |
| ---------------------------- | ------- | ---------------------------------------------------------- |
| `GENERATION_ENABLED`         | `true`  | `false` is the kill switch: every request fails `provider` |
| `GENERATION_FAKE`            | `true`  | the fake model                                             |
| `GENERATION_BASE_URL`        | empty   | the part before `/chat/completions`                        |
| `GENERATION_API_KEY`         | empty   | never commit it                                            |
| `GENERATION_MODEL`           | empty   | the write model                                            |
| `GENERATION_CHECK_MODEL`     | empty   | the answer-check model (empty: same as above)              |
| `GENERATION_FALLBACK_MODEL`  | empty   | tried once when a call to the write or check model fails   |
| `GENERATION_TIMEOUT_SECONDS` | `60`    | per model call                                             |

Compose passes each from the host's environment (or the root `.env`), e.g. `GENERATION_FAKE=false GENERATION_BASE_URL=... GENERATION_API_KEY=... docker compose up -d generation`. Setting up the key and the models chosen: the root README's "AI-generated lessons" section. Why those models: `docs/ai-model-evaluation.md`.

Learning and Content each give up on a request after their own `GENERATION_TIMEOUT_SECONDS` (180 in compose) and give the learner or administrator their slot back; keep that longer than this worker's calls (a write, perhaps a retry, and the answer check).

## Commands and tests

`docker compose exec generation python -m app.cli health` checks the database and the broker (the container's healthcheck).

```bash
docker compose up -d generation-db
cd services/generation
uv venv -p 3.11 .venv && uv pip install -p .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest                              # 114 tests, generation_test on :5438
.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
.venv/bin/python -m alembic upgrade head && .venv/bin/python -m alembic check
```

The tests run every check, the fake model at 4, 6 and 8 cards with 1 to 3 questions, each failure code with a scripted model, the real client and its fallback against a stub transport, the event order and versions, and validate every emitted event against `contracts/events`. They never call a real model.

## Evaluation harness (`evaluation/`)

How the SoC LaaS models were chosen, kept so the comparison can be run again when SoC changes its models. It sends fixed requests (learner and admin briefs, and hostile or odd ones) through the real pipeline (`app/prompt.py`, `app/checks.py`, the retry, the answer check), gives labelled good and flawed lessons to candidate check models, and makes the tables. It needs the real key in your shell and the NUS network; its raw output goes to the git-ignored `evaluation/results/`. How to run it: [evaluation/README.md](evaluation/README.md); the results and the decision: `docs/ai-model-evaluation.md`. It is not part of `pytest` or CI.
