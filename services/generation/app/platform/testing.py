"""Helpers for a service's tests.

client.get("/api/progress", headers=app_headers(user_id))
consumer.handle(json.dumps(make_envelope("content.topic.changed", {...}, topic_id, 3)))
"""

import uuid
from datetime import UTC, datetime

from .config import get_config
from .principal import Principal


def make_envelope(
    type: str,
    data: dict,
    aggregate_id: uuid.UUID | str | None = None,
    aggregate_version: int = 1,
    *,
    aggregate_type: str | None = None,
    producer: str | None = None,
    event_id: uuid.UUID | None = None,
    correlation_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict:
    """An event as a consumer receives it. `type` "content.topic.changed" defaults the
    producer to "content" and the aggregate type to "topic"."""
    parts = type.split(".")
    return {
        "event_id": str(event_id or uuid.uuid4()),
        "type": type,
        "schema_version": 1,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat().replace("+00:00", "Z"),
        "producer": producer or parts[0],
        "aggregate_type": aggregate_type or parts[1],
        "aggregate_id": str(aggregate_id or uuid.uuid4()),
        "aggregate_version": aggregate_version,
        "correlation_id": correlation_id,
        "data": data,
    }


def headers_for(principal: Principal, gateway_key: str | None = None) -> dict[str, str]:
    """The headers the gateway sets for this principal."""
    headers = {
        "X-Gateway-Key": gateway_key if gateway_key is not None else get_config().gateway_key,
        "X-User-Id": str(principal.user_id),
        "X-User-Scope": principal.scope,
        "X-User-Role": principal.role,
        "X-Profile-Completed": "true" if principal.profile_completed else "false",
    }
    if principal.user_type:
        headers["X-User-Type"] = principal.user_type
    return headers


def app_headers(
    user_id: uuid.UUID | None = None, user_type: str = "newcomer", profile_completed: bool = True
) -> dict[str, str]:
    return headers_for(
        Principal(user_id or uuid.uuid4(), "app", "user", user_type, profile_completed)
    )


def admin_headers(user_id: uuid.UUID | None = None) -> dict[str, str]:
    return headers_for(Principal(user_id or uuid.uuid4(), "admin", "admin", None, False))
