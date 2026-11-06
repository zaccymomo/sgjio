"""Validate envelopes against the published event contracts (contracts/events in the
repository; CONTRACTS_DIR overrides where they are). Built like contracts/validate.py."""

import json
import os
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "contracts" / "events"


def events_dir() -> Path:
    return Path(os.environ.get("CONTRACTS_DIR") or DEFAULT_DIR)


def available() -> bool:
    return (events_dir() / "envelope.schema.json").is_file()


@lru_cache
def _validators() -> dict[str, Draft202012Validator]:
    schemas = [json.loads(path.read_text()) for path in events_dir().glob("*.schema.json")]
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return {
        schema["title"]: Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas
    }


def errors(envelope: dict) -> list[str]:
    validators = _validators()
    validator = validators.get(envelope.get("type"))
    if validator is None:
        return [f"no contract for event type {envelope.get('type')!r}"]
    found = [
        f"{'/'.join(map(str, error.absolute_path)) or '(root)'}: {error.message}"
        for error in validator.iter_errors(envelope)
    ]
    found += [
        f"envelope: {error.message}" for error in validators["Event envelope"].iter_errors(envelope)
    ]
    return found


def assert_valid(envelope: dict) -> None:
    problems = errors(envelope)
    assert not problems, f"{envelope['type']} breaks its contract:\n" + "\n".join(problems)
