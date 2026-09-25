"""Password hashing, password rules and random tokens (SCRUM-73)."""

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()

# Hash of a random password, checked when an email is not registered so that a sign-in
# for an unknown email takes as long as one for a known email. Otherwise response time
# would reveal which emails have accounts (SCRUM-62 AC2, SCRUM-68 AC2).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

# --- Password rules (proposed default for SCRUM-61; see docs/decisions.md) ----------------
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def password_rule_failures(password: str) -> list[str]:
    """Return a human-readable message for each password rule the password breaks.

    An empty list means the password is acceptable. SCRUM-61 AC4 needs to tell the user
    which rule failed, so this returns every failure rather than a yes/no.
    """
    failures = []
    if len(password) < PASSWORD_MIN_LENGTH:
        failures.append(f"Use at least {PASSWORD_MIN_LENGTH} characters.")
    if len(password) > PASSWORD_MAX_LENGTH:
        failures.append(f"Use no more than {PASSWORD_MAX_LENGTH} characters.")
    if not re.search(r"[A-Za-z]", password):
        failures.append("Include at least one letter.")
    if not re.search(r"\d", password):
        failures.append("Include at least one number.")
    return failures


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Check a password. Pass `None` for an unknown user to keep timing constant."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# --- Opaque tokens (sessions and reset links) ----------------------------------------------


def new_token() -> str:
    """A random, URL-safe token for a cookie or an emailed link."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are stored hashed, so a leaked database cannot be used to sign in."""
    return hashlib.sha256(token.encode()).hexdigest()
