"""Feeding events to Learning the way the broker does: through the real consumer.

Every envelope is first checked against contracts/events (as contracts/validate.py checks
them), so a fixture can only send what Identity and Content are allowed to publish. Then it
goes through `consumer.handle(...)`, the same code path a message from RabbitMQ takes, and
the test fails unless the consumer acknowledged it.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from app.consumers import consumer
from app.platform.consumer import Outcome
from app.platform.testing import make_envelope

# services/learning/tests/support/events.py -> the repository's contracts/events.
CONTRACTS = Path(
    os.environ.get("CONTRACTS_DIR", Path(__file__).resolve().parents[4] / "contracts" / "events")
)

BANK_ID = uuid.UUID("d69a3dc8-6470-5484-a156-901c82a34f06")


@lru_cache
def _validators() -> dict:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource

    if not CONTRACTS.is_dir():
        raise RuntimeError(f"contracts not found at {CONTRACTS}; set CONTRACTS_DIR")
    schemas = [json.loads(path.read_text()) for path in sorted(CONTRACTS.glob("*.schema.json"))]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return {
        schema["title"]: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas
    }


def validate(envelope: dict) -> None:
    """Raise if the envelope breaks its event's contract."""
    validator = _validators()[envelope["type"]]
    problems = [
        f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
        for e in validator.iter_errors(envelope)
    ]
    assert not problems, f"{envelope['type']} breaks its contract: {problems}"


def stamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")


class EventBus:
    """Sends events to the consumer, keeping a copy of each for tests that replay them."""

    def __init__(self):
        self.sent: list[dict] = []

    def envelope(
        self, type: str, data: dict, aggregate_id, version: int, aggregate_type=None
    ) -> dict:
        envelope = make_envelope(
            type,
            data,
            aggregate_id,
            version,
            producer=type.split(".")[0],
            aggregate_type=aggregate_type,
        )
        validate(envelope)
        return envelope

    def deliver(self, envelope: dict, expect: Outcome = Outcome.ACK) -> Outcome:
        outcome = consumer.handle(json.dumps(envelope).encode())
        assert outcome is expect, f"{envelope['type']}: {outcome} (expected {expect})"
        return outcome

    def publish(self, type: str, data: dict, aggregate_id, version: int) -> dict:
        envelope = self.envelope(type, data, aggregate_id, version)
        self.sent.append(envelope)
        self.deliver(envelope)
        return envelope
