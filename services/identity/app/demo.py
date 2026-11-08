"""Demo learners for lesson insights (SCRUM-84): Identity's part.

    python -m app.cli clear-demo-learners
    python -m app.cli seed-demo-learners --count 60 [--run-nonce abc123]

- `seed-demo-learners` replaces the demo learners: it deletes any that exist (as
  `clear-demo-learners` does), then adds `count` of them (two thirds Newcomers, the rest
  Singaporeans, 40 and 20 by default) at demo.sgjio.example.com, with a random password
  nobody knows, so they can never sign in.
- Each demo learner's id is uuid5(NAMESPACE_URL, "sgjio:user:" + email + ":" + nonce)
  (contracts/README.md). A fresh nonce each run means a new run never reuses an id that
  Learning has already erased; Learning's `demo-activity --run-nonce <nonce>` works the
  same ids out and writes their lesson runs.
- Adding is identity.user.registered per learner, and deleting identity.user.deleted, in
  the same transaction as the change. Nobody else's account is touched.
"""

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import events
from app.models import User, UserRole, UserType
from app.security import hash_password
from app.seed import seed_user_id

DOMAIN = "demo.sgjio.example.com"
DEFAULT_COUNT = 60  # 40 newcomers and 20 Singaporeans, as in the monolith


def demo_email(n: int) -> str:
    return f"learner{n:02}@{DOMAIN}"


def new_nonce() -> str:
    return secrets.token_hex(4)


def clear_demo_learners(db: Session) -> int:
    """Delete every demo learner, each with its identity.user.deleted. Commits."""
    learners = db.scalars(select(User).where(User.email.like(f"%@{DOMAIN}"))).all()
    now = datetime.now(UTC)
    for learner in learners:
        events.user_deleted(db, learner.id, now)
        db.delete(learner)
    db.commit()
    return len(learners)


def seed_demo_learners(
    db: Session, count: int = DEFAULT_COUNT, nonce: str | None = None
) -> tuple[str, list[str]]:
    """Replace the demo learners. Returns the run's nonce and a short log. Commits."""
    nonce = nonce or new_nonce()
    removed = clear_demo_learners(db)
    newcomers = round(count * 2 / 3)
    password = hash_password(secrets.token_urlsafe(24))
    now = datetime.now(UTC)
    for n in range(1, count + 1):
        email = demo_email(n)
        learner = User(
            id=seed_user_id(email, nonce),
            name=f"Demo learner {n:02}",
            email=email,
            password_hash=password,
            role=UserRole.USER,
            user_type=UserType.NEWCOMER if n <= newcomers else UserType.SINGAPOREAN,
            intro_finished_at=now,
        )
        db.add(learner)
        events.user_registered(db, learner)
    db.commit()
    log = [
        f"{count} demo learners at {DOMAIN} ({newcomers} newcomers, "
        f"{count - newcomers} Singaporeans), run nonce {nonce}"
    ]
    if removed:
        log.insert(0, f"removed {removed} earlier demo learners")
    return nonce, log
