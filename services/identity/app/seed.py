"""Development seed data: Identity's part (SCRUM-72, Epic 6). Safe to run more than once.

Creates, when missing:
- one administrator (administrators are not created through registration, SCRUM-68)
- the Newcomer seed account, with a profile
- the test personas the aptitude stories use, each with a profile

Every seed user gets a deterministic id, uuid5(NAMESPACE_URL, "sgjio:user:" + email)
(contracts/README.md, "Seed and demo ids"), so Learning's seed can give the Newcomer its
completions and the personas their aptitude results without asking Identity. Each account
created here is also an identity.user.registered event, in the same transaction.

Topics, lessons and the question bank are Content's seed; progress and aptitude results
are Learning's (scripts/seed-all.sh runs all three in order).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events
from app.auth import normalise_email
from app.config import get_settings
from app.models import Profile, User, UserRole, UserType
from app.security import hash_password

# The aptitude personas (Learning seeds their results). Same emails, names and password
# as the monolith's seed.
TEST_USERS: dict[str, str] = {
    "starter@sgjio.example.com": "Starter Newcomer",
    "mixed@sgjio.example.com": "Mixed Placement Newcomer",
    "advanced@sgjio.example.com": "Advanced Newcomer",
    "skipped@sgjio.example.com": "Skipped Quiz Newcomer",
}
TEST_USER_PASSWORD = "UserPass123"


def seed_user_id(email: str, nonce: str | None = None) -> uuid.UUID:
    """The deterministic id of a seed user, or (with the run's nonce) of a demo learner."""
    name = f"sgjio:user:{normalise_email(email)}"
    if nonce is not None:
        name += f":{nonce}"
    return uuid.uuid5(uuid.NAMESPACE_URL, name)


def _get_or_create_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    role: UserRole,
    user_type: UserType | None,
) -> tuple[User, bool]:
    email = normalise_email(email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        id=seed_user_id(email),
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        user_type=user_type,
        # The seed login goes straight to Home; register to see the introduction (SCRUM-94).
        intro_finished_at=datetime.now(UTC) if role == UserRole.USER else None,
    )
    db.add(user)
    return user, True


def seed(db: Session) -> list[str]:
    """Insert anything missing and return a short log of what was created."""
    settings = get_settings()
    log: list[str] = []
    created_users: list[User] = []

    admin, created = _get_or_create_user(
        db,
        settings.seed_admin_email,
        settings.seed_admin_password,
        "SGJio Admin",
        UserRole.ADMIN,
        None,
    )
    if created:
        created_users.append(admin)
        log.append(f"admin account {admin.email}")

    user, created = _get_or_create_user(
        db,
        settings.seed_user_email,
        settings.seed_user_password,
        "Siddharth Sharma",
        UserRole.USER,
        UserType.NEWCOMER,
    )
    if created:
        user.profile = Profile(
            neighbourhood="Tampines",
            interests=["Food", "Football"],
            languages=["English", "Hindi"],
        )
        created_users.append(user)
        log.append(f"user account {user.email}")

    for email, name in TEST_USERS.items():
        person, created = _get_or_create_user(
            db, email, TEST_USER_PASSWORD, name, UserRole.USER, UserType.NEWCOMER
        )
        if created:
            person.profile = Profile(
                neighbourhood="Tampines", interests=["Food"], languages=["English"]
            )
            created_users.append(person)
            log.append(f"test user {email}")

    for person in created_users:
        events.user_registered(db, person)
    db.commit()
    return log
