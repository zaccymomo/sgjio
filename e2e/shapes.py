"""Response shapes, checked against the monolith (the behaviour oracle).

`oracle/monolith-openapi.json` is the monolith's own OpenAPI document (regenerate with
oracle/export_monolith_openapi.py while api/ exists). For a route and status it declares,
`check` validates the body against that response model, made strict: every object must
have exactly the properties the monolith's model has (no missing keys, no extra ones), so
a service that drops, adds or renames a field fails here even if the front end would not
notice at once.
"""

import copy
import json
from functools import cache
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator

ORACLE = Path(__file__).with_name("oracle") / "monolith-openapi.json"

NOT_SIGNED_IN = {"detail": {"code": "not_signed_in", "message": "Please sign in to continue."}}


def _strict(node):
    """Close every object schema that lists its properties (the response models)."""
    if isinstance(node, dict):
        if "properties" in node and "additionalProperties" not in node:
            node["additionalProperties"] = False
            node.setdefault("required", list(node["properties"]))
        for value in node.values():
            _strict(value)
    elif isinstance(node, list):
        for value in node:
            _strict(value)
    return node


@cache
def _spec() -> dict:
    return json.loads(ORACLE.read_text())


@cache
def _components() -> dict:
    return _strict(copy.deepcopy(_spec()["components"]))


def response_schema(route: str, status: int) -> dict | None:
    """The monolith's schema for `route` ("GET /api/topics/{topic_id}") at `status`, or None
    when it answers that status with no JSON body."""
    method, path = route.split(" ", 1)
    operation = _spec()["paths"][path][method.lower()]
    response = operation["responses"].get(str(status))
    assert response is not None, f"the monolith never answers {route} with {status}"
    content = response.get("content", {}).get("application/json")
    if content is None or not content.get("schema"):
        return None
    return _strict(copy.deepcopy(content["schema"]))


def check(response: httpx.Response, route: str, status: int | None = None):
    """Assert the status (if given) and that the body has the monolith's shape. Returns the
    parsed body (None for an empty one)."""
    if status is not None:
        assert response.status_code == status, (
            f"{route}: expected {status}, got {response.status_code}: {response.text[:500]}"
        )
    assert response.status_code < 400, (
        f"{route}: {response.status_code} {response.text[:500]} (use problem() for errors)"
    )
    schema = response_schema(route, response.status_code)
    if schema is None:
        assert not response.content, f"{route}: expected no body, got {response.text[:200]}"
        return None
    body = response.json()
    validator = Draft202012Validator({**schema, "components": _components()})
    errors = sorted(validator.iter_errors(body), key=lambda error: list(error.path))
    assert not errors, f"{route} {response.status_code} does not match the monolith:\n" + "\n".join(
        f"  at {list(error.path)}: {error.message[:300]}" for error in errors[:10]
    )
    return body


def problem(response: httpx.Response, status: int, code: str) -> dict:
    """Assert a broken-rule error in the monolith's shape: {"detail": {"code", "message", ...}}."""
    assert response.status_code == status, (
        f"expected {status} {code}, got {response.status_code}: {response.text[:500]}"
    )
    assert response.headers["content-type"].startswith("application/json")
    detail = response.json()["detail"]
    assert isinstance(detail, dict), response.text
    assert detail["code"] == code, response.text
    assert isinstance(detail["message"], str) and detail["message"]
    return detail


def not_signed_in(response: httpx.Response) -> None:
    """The exact 401 body every signed-out request gets, byte for byte."""
    assert response.status_code == 401, response.text
    assert response.json() == NOT_SIGNED_IN


def validation_error(response: httpx.Response) -> list:
    """FastAPI's own 422 body, unchanged."""
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert isinstance(detail, list) and detail
    for item in detail:
        assert {"type", "loc", "msg"} <= set(item), item
    return detail
