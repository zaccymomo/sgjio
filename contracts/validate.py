"""Check the event contracts.

    python contracts/validate.py                 every schema, example and negative case
    python contracts/validate.py a.json b.json   also validate these envelopes (by their type),
                                                 e.g. events a service's test wrote out

Needs `pip install -r contracts/requirements.txt`. Exits non-zero on any failure.
"""

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
EVENTS = HERE / "events"
EXAMPLES = EVENTS / "examples"

# The catalogue (contracts/README.md). Adding an event means adding it here, a schema and an
# example.
CATALOGUE = [
    "identity.user.registered",
    "identity.user.deleted",
    "identity.password_reset.requested",
    "identity.admin.invitation_issued",
    "identity.admin.removed",
    "content.topic.changed",
    "content.topic.deleted",
    "content.lesson.changed",
    "content.lesson_version.published",
    "content.aptitude_question.changed",
    "content.aptitude_bank.changed",
]


def load(path: Path):
    return json.loads(path.read_text())


def build() -> tuple[dict[str, Draft202012Validator], Draft202012Validator]:
    schemas = {path.name: load(path) for path in sorted(EVENTS.glob("*.schema.json"))}
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        assert schema["$id"].endswith("/" + name), f"{name}: $id does not end with its file name"
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )

    def validator(schema: dict) -> Draft202012Validator:
        return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())

    envelope = validator(schemas.pop("envelope.schema.json"))
    events = {schema["title"]: validator(schema) for schema in schemas.values()}
    return events, envelope


def errors(validator: Draft202012Validator, instance) -> list[str]:
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '(root)'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    ]


def check_instance(events, envelope, instance, label: str) -> list[str]:
    problems = [f"{label}: envelope: {e}" for e in errors(envelope, instance)]
    validator = events.get(instance.get("type"))
    if validator is None:
        return problems + [f"{label}: unknown event type {instance.get('type')!r}"]
    return problems + [f"{label}: {e}" for e in errors(validator, instance)]


def negative_cases(example: dict):
    """Changes that must make a valid event invalid, so the schemas are known to be strict."""
    data = example["data"]
    for key in data:
        case = copy.deepcopy(example)
        del case["data"][key]
        if key not in ("link", "expires_in_minutes", "sign_in_url"):  # conditional fields
            yield f"without data.{key}", case
    case = copy.deepcopy(example)
    case["data"]["unexpected"] = 1
    yield "with an unknown data field", case
    case = copy.deepcopy(example)
    case["surprise"] = 1
    yield "with an unknown envelope field", case
    case = copy.deepcopy(example)
    case["event_id"] = "not-a-uuid"
    yield "with a bad event_id", case
    case = copy.deepcopy(example)
    case["occurred_at"] = "yesterday"
    yield "with a bad occurred_at", case
    case = copy.deepcopy(example)
    case["producer"] = "learning" if example["producer"] != "learning" else "content"
    yield "from the wrong producer", case
    case = copy.deepcopy(example)
    case["aggregate_type"] = "something_else"
    yield "with the wrong aggregate_type", case


def variants(example: dict):
    """Other valid shapes of the same event (positive), and mixes of them (negative)."""
    data = example["data"]
    if example["type"] == "identity.password_reset.requested":
        google = {k: v for k, v in data.items() if k not in ("link", "expires_in_minutes")}
        google |= {"method": "google", "sign_in_url": "http://localhost:5173/sign-in"}
        yield "google method", True, {**example, "data": google}
        yield "google method with a link", False, {**example, "data": {**google, "link": data["link"]}}
        yield "password method without a link", False, {
            **example, "data": {k: v for k, v in data.items() if k != "link"}}
    if example["type"] == "identity.user.registered":
        yield "an admin", True, {**example, "data": {**data, "role": "admin", "user_type": None}}
        yield "an admin with a user type", False, {**example, "data": {**data, "role": "admin"}}
        yield "a learner without a user type", False, {**example, "data": {**data, "user_type": None}}
    if example["type"] == "identity.admin.invitation_issued":
        asked = {**data, "trigger": "forgot_password", "inviter_name": None}
        yield "asked for by the admin", True, {**example, "data": asked}
        yield "asked for, with an inviter", False, {**example, "data": {**asked, "inviter_name": "X"}}
        yield "invited by nobody", False, {**example, "data": {**data, "inviter_name": None}}
    if example["type"] == "content.lesson_version.published":
        bad = copy.deepcopy(example)
        bad["data"]["doc"]["cards"][0]["question"]["options"][0]["correct"] = "yes"
        yield "a doc with a malformed option", False, bad
        bad = copy.deepcopy(example)
        bad["data"]["assets"]["not-a-uuid"] = bad["data"]["assets"].popitem()[1]
        yield "an asset keyed by something other than its id", False, bad


def main(extra: list[str]) -> int:
    events, envelope = build()
    problems: list[str] = []
    checked = 0

    missing = sorted(set(CATALOGUE) ^ set(events))
    if missing:
        problems.append(f"catalogue and schemas differ: {missing}")

    for event_type in CATALOGUE:
        path = EXAMPLES / f"{event_type}.json"
        if not path.exists():
            problems.append(f"no example for {event_type}")
            continue
        example = load(path)
        checked += 1
        if example.get("type") != event_type:
            problems.append(f"{path.name}: type is {example.get('type')!r}")
        problems += check_instance(events, envelope, example, path.name)
        for description, case in negative_cases(example):
            checked += 1
            if not check_instance(events, envelope, case, path.name):
                problems.append(f"{path.name}: still valid {description}")
        for description, valid, case in variants(example):
            checked += 1
            found = check_instance(events, envelope, case, f"{path.name} ({description})")
            if valid and found:
                problems += found
            elif not valid and not found:
                problems.append(f"{path.name}: {description} should be invalid")

    for name in extra:
        checked += 1
        problems += check_instance(events, envelope, load(Path(name)), name)

    for problem in problems:
        print("FAIL", problem)
    print(f"{len(events)} event schemas; {checked} instances checked; {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
