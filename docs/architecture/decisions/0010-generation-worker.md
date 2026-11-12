# ADR 0010: AI generation as a separate worker, reached only by events

**Status:** accepted, built (AI-generated lessons, docs/ai-lessons-plan.md D11 to D13, D18)

## Context

Learners generate private practice lessons in Learning, and administrators generate Draft lessons in Content (docs/ai-lessons-plan.md). Both need the same work done: build a prompt from a brief and our published lessons, call a model (NUS SoC LaaS, an OpenAI-compatible API reachable only from the NUS network), check the reply in code, retry once, ask a second model to check the answers, and turn the result into a deck. A request takes 10 seconds to over a minute and can fail in ways we don't control: the provider is down, a model is withdrawn, the reply is not valid JSON. The work also needs an API key and prompts that we want kept in one place and out of reach of the internet.

## Decision

- **A fifth service, `generation`** (`services/generation/`), a worker with no HTTP API and no gateway route, like Notification. It consumes `learning.lesson_generation.requested` and `content.lesson_generation.requested` (queue `generation.events`) and answers with `generation.lesson.progress` (writing, then checking), then `generation.lesson.generated` or `generation.lesson.failed`, all with the requester's `request_id` as the aggregate and versions 1, 2 and 3 (contracts/README.md).
- **All the AI code is here:** the prompts and rules (`app/prompt.py`), the checks (`app/checks.py`), the model client with its fallback model (`app/llm.py`) and the pipeline (`app/pipeline.py`). The API key is set only in this container's environment. Learning and Content only build the brief and the grounding, and store the result.
- **No user ids.** A request carries a request id, a brief and lesson text (the learner's mistakes are lesson text too), never a user id, name or email. Each requester keeps the link between its request and the person; Generation and the model never learn who asked.
- **Its own small database** (`generation-db`, 5438) with only the platform's `outbox` and a `processed_events` inbox. The inbox row is written in the same transaction as the result, so a redelivered request is skipped instead of paying for the model twice. It keeps no lessons.
- **A fake model by default** (`GENERATION_FAKE=true`): deterministic lessons, and refusals for a few marker phrases, with no key and no network. Unit, contract and end-to-end tests and CI all run on it; the real model is switched on by settings only.
- **Failures are answers, not retries.** Model trouble becomes `failed` with code `provider` and is acknowledged, so a broken provider can't run up cost; Learning and Content refund the slot. Each requester also times out a request it has waited too long for, so a request lost in Generation never leaves anyone waiting.

## Consequences

- No public surface: nothing outside Docker can reach Generation, and no network but RabbitMQ's joins it. A prompt-injection attempt can only produce a reply that is checked and thrown away.
- Generation being down, or the model, stops only new generated lessons and AI drafts. Requests wait in the durable queue; Learning and Content show them as failed after their timeout (180 s in compose) and give the slot back. Everything else works (diagrams.md, section 5).
- Changing provider or model, or re-running the model comparison (`services/generation/evaluation/`), touches one service.
- The cost: one more service to build, run and test (its own Dockerfile, migrations, CI job and copy of `app/platform/`), one more small Postgres, and five more event types. Learning gained an outbox and relay, since it now publishes.
- Results arrive asynchronously, so both front ends poll a status endpoint every 1.5 s instead of waiting on one request.
- Alternatives rejected:
  - **A module inside Learning and Content.** Two copies of the prompts, checks and client, or shared code, which ADR 0006 avoids between services; the key in two services that are on the gateway's network; and minute-long model calls on the API processes' threads.
  - **A synchronous HTTP call** from Learning and Content to a generation service. A browser request would hang for up to a minute, the gateway's 15 s timeout would cut it off, Generation being down would fail the request, and a retried call could pay for the model twice. Events give the queue, the inbox and the progress steps for free.
