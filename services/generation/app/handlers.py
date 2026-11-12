"""Answer a lesson generation request (learning.* or content.lesson_generation.requested).

For one request, Generation emits (all with aggregate_id = request_id and requester = the
request's producer, "learning" or "content"):

    generation.lesson.progress  stage writing    aggregate_version 1   own transaction
    generation.lesson.progress  stage checking   aggregate_version 2   own transaction
    generation.lesson.generated | generation.lesson.failed  version 3  the handler's

The progress events are committed at once, each in a new session, so the relay publishes
them while the model is still working. The result and the inbox row (processed_events)
go in the consumer's transaction, committed when the handler returns: a redelivered
request is then skipped by the consumer's `dedupe` hook instead of costing another model
call. A crash before that commit repeats the request (and its progress events, which the
requester's version guard ignores).

Generation is switched off (GENERATION_ENABLED=false) or the model can't be reached:
failed with code "provider". The handler only raises for bugs and database trouble.
"""

import functools
import logging
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app import pipeline
from app.config import get_settings
from app.llm import LLM, build_llm
from app.models import ProcessedEvent
from app.platform.outbox import emit

log = logging.getLogger("sgjio.generation")

LEARNING_REQUESTED = "learning.lesson_generation.requested"
CONTENT_REQUESTED = "content.lesson_generation.requested"
REQUEST_TYPES = (LEARNING_REQUESTED, CONTENT_REQUESTED)

PROGRESS = "generation.lesson.progress"
STAGE_VERSIONS = {"writing": 1, "checking": 2}
RESULT_VERSION = 3
AGGREGATE_TYPE = "lesson_generation"


def already_processed(session: Session, event_id: uuid.UUID) -> bool:
    """The consumer's dedupe hook: True skips the event."""
    return session.get(ProcessedEvent, event_id) is not None


def make_handler(
    session_factory: Callable[[], Session], llm_factory: Callable[[], LLM] | None = None
) -> Callable[[Session, dict], None]:
    """The consumer's handler. `session_factory` opens the progress events' own
    transactions; `llm_factory` gives the model (default: built once from settings)."""
    llm_factory = llm_factory or functools.cache(lambda: build_llm(get_settings()))

    def handle(session: Session, envelope: dict) -> None:
        data = envelope["data"]
        request_id = data["request_id"]
        requester = envelope["producer"]
        settings = get_settings()

        def event(type_: str, version: int, payload: dict, into: Session) -> None:
            emit(
                into,
                type=type_,
                aggregate_type=AGGREGATE_TYPE,
                aggregate_id=request_id,
                aggregate_version=version,
                data={"request_id": request_id, "requester": requester, **payload},
            )

        def on_stage(stage: str) -> None:
            with session_factory() as own, own.begin():
                event(PROGRESS, STAGE_VERSIONS[stage], {"stage": stage}, own)

        if not settings.generation_enabled:
            result = pipeline.failed("provider", "generation is switched off")
        else:
            result = pipeline.run(data["brief"], data["grounding"], llm_factory(), on_stage)
        log.info("request %s from %s %s", request_id, requester, pipeline.describe(result))
        event_type, payload = result
        event(event_type, RESULT_VERSION, payload, session)
        session.add(ProcessedEvent(event_id=uuid.UUID(envelope["event_id"]), type=envelope["type"]))

    return handle
