"""Reading what Identity emitted. Identity sends no email itself: each email is an event in
the outbox (app/events.py), so the monolith's `mailer.outbox` checks read these instead."""

from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models import outbox
from app.platform.outbox import envelope

EMAIL_EVENTS = (
    "identity.password_reset.requested",
    "identity.admin.invitation_issued",
    "identity.admin.removed",
)


def outbox_events(type: str | None = None) -> list[dict]:
    """Every event in the outbox, oldest first, as the relay would publish it."""
    with SessionLocal() as session:
        rows = session.execute(select(outbox).order_by(outbox.c.id)).all()
    return [envelope(row) for row in rows if type is None or row.type == type]


def emails() -> list[dict]:
    """The events Notification turns into emails, oldest first."""
    return [event for event in outbox_events() if event["type"] in EMAIL_EVENTS]


def recipients() -> list[str]:
    return [event["data"]["email"] for event in emails()]


def last_email() -> dict:
    """The newest email event's `data`."""
    return emails()[-1]["data"]


def link_from_last_email() -> str:
    data = last_email()
    return data.get("link") or data["sign_in_url"]


def token_from_last_email() -> str:
    return parse_qs(urlparse(link_from_last_email()).query)["token"][0]
