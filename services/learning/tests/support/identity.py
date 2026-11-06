"""A stand-in for Identity: registers and deletes accounts by publishing its events through
the real consumer, and gives the headers the gateway would send for a signed-in user.

Ids are Identity's deterministic seed ids (contracts/README.md), uuid5 of the email, so a
test can name the same user twice without keeping the object around.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.platform.testing import admin_headers, app_headers
from tests.support.events import EventBus, stamp


def user_id_for(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "sgjio:user:" + email.lower())


@dataclass
class User:
    id: uuid.UUID
    email: str
    name: str
    role: str  # "user" or "admin"
    user_type: str | None  # "newcomer" or "singaporean"; None for administrators
    profile_completed: bool = True

    def headers(self) -> dict[str, str]:
        if self.role == "admin":
            return admin_headers(self.id)
        return app_headers(self.id, self.user_type, self.profile_completed)


class FakeIdentity:
    def __init__(self, bus: EventBus):
        self.bus = bus

    def register(
        self,
        email: str = "user@example.com",
        *,
        role: str = "user",
        user_type: str | None = "newcomer",
        name: str = "Test User",
        profile_completed: bool = True,
        user_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            user_id or user_id_for(email),
            email,
            name,
            role,
            user_type if role == "user" else None,
            profile_completed,
        )
        self.bus.publish(
            "identity.user.registered",
            {
                "user_id": str(user.id),
                "role": role,
                "user_type": user.user_type,
                "registered_at": stamp(),
            },
            user.id,
            1,
        )
        return user

    def delete(self, user: User) -> dict:
        return self.bus.publish(
            "identity.user.deleted",
            {"user_id": str(user.id), "deleted_at": stamp(datetime.now(UTC))},
            user.id,
            2,
        )
