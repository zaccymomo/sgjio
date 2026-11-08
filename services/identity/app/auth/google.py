"""Signing in and registering with Google (SCRUM-92).

The main app opens Google's sign-in window with Firebase Authentication, which hands the
browser a short-lived ID token signed by Google. The browser sends that token here; once
it checks out, the person gets an ordinary main-app session, exactly as after a password
sign-in. Firebase keeps no session of its own: the front end signs out of it straight away.

- A Google account already linked to an SGJio account signs in to it.
- Otherwise a learner account with the same, Google-verified email is linked and signed
  in to; its password keeps working too. Administrator and removed accounts are never
  reached this way: they sign in with their password.
- Otherwise nobody is created until the person has said whether they are a Newcomer or a
  Singaporean and agreed to the privacy notice. The browser keeps the token meanwhile
  (it lasts an hour) and sends it again with those answers, so nothing waits on the server.

Accounts created with Google have no password (`users.password_hash` is NULL).
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import events
from app.auth import normalise_email
from app.config import get_settings
from app.models import User, UserRole, UserType
from app.privacy import NOTICE_VERSION

logger = logging.getLogger("sgjio.auth.google")

# Firebase signs its ID tokens with these keys, and names the project as issuer.
_FIREBASE_ISSUER = "https://securetoken.google.com/{project_id}"
_GOOGLE_PROVIDER = "google.com"
# How far this server's clock may be behind or ahead of Google's. A token is used within a
# second of being issued, so with no allowance a clock even a second slow (common under
# WSL, and after a laptop sleeps) refuses it as "used too early".
_CLOCK_SKEW_SECONDS = 60


class GoogleUnavailable(Exception):
    """FIREBASE_PROJECT_ID is not set, so no token can be checked."""


class GoogleTokenInvalid(Exception):
    """The token is malformed, expired, for another project, or not from Google sign-in."""


@dataclass(frozen=True)
class GoogleIdentity:
    """Who Google says signed in. `sub` is Google's own id for the account, not Firebase's."""

    sub: str
    email: str
    email_verified: bool
    name: str


@lru_cache
def _http_request():
    # Imported here so the API starts, and tests run, without touching the network.
    import requests
    from google.auth.transport.requests import Request

    return Request(session=requests.Session())


def _decode_token(token: str, project_id: str) -> Mapping[str, Any]:
    """Check the signature, expiry and audience against Google's published keys.

    The only function that talks to Google; tests replace it.
    """
    from google.auth.exceptions import GoogleAuthError
    from google.oauth2 import id_token

    try:
        return id_token.verify_firebase_token(
            token,
            _http_request(),
            audience=project_id,
            clock_skew_in_seconds=_CLOCK_SKEW_SECONDS,
        )
    except (ValueError, GoogleAuthError) as error:
        raise GoogleTokenInvalid(str(error)) from error


def verify_google_token(token: str) -> GoogleIdentity:
    project_id = get_settings().firebase_project_id
    if not project_id:
        raise GoogleUnavailable
    try:
        return _identity(_decode_token(token, project_id), project_id)
    except GoogleTokenInvalid as error:
        # The person only sees "couldn't confirm"; the reason is for whoever runs the API.
        logger.warning("Google sign-in token refused: %s", error)
        raise


def _identity(claims: Mapping[str, Any], project_id: str) -> GoogleIdentity:
    if claims.get("iss") != _FIREBASE_ISSUER.format(project_id=project_id):
        raise GoogleTokenInvalid("issued for another project")
    firebase = claims.get("firebase") or {}
    if firebase.get("sign_in_provider") != _GOOGLE_PROVIDER:
        raise GoogleTokenInvalid("not a Google sign-in")
    google_ids = (firebase.get("identities") or {}).get(_GOOGLE_PROVIDER) or []
    email = normalise_email(claims.get("email") or "")
    if not google_ids or not email:
        raise GoogleTokenInvalid("no Google account or email in the token")

    return GoogleIdentity(
        sub=str(google_ids[0]),
        email=email,
        email_verified=claims.get("email_verified") is True,
        name=(claims.get("name") or "").strip(),
    )


# --- Signing in and registering -----------------------------------------------------------


@dataclass(frozen=True)
class GoogleRefusal:
    code: str
    message: str


EMAIL_UNVERIFIED = GoogleRefusal(
    "google_email_unverified",
    "Google hasn't verified the email address on that Google account, so it can't be used "
    "for SGJio. Register with your email and a password instead.",
)
# Telling someone this only reveals the account to the person who has just proven, through
# Google, that they own its email address.
PASSWORD_ONLY = GoogleRefusal(
    "google_not_available",
    "This account can't use Google sign-in. Sign in with your email and password.",
)
OTHER_GOOGLE_ACCOUNT = GoogleRefusal(
    "google_account_mismatch",
    "This email's SGJio account is linked to a different Google account. "
    "Sign in with that Google account, or with your email and password.",
)
NOTICE_CHANGED = GoogleRefusal(
    "privacy_notice_changed",
    "The privacy notice has changed. Please read the current version and agree again.",
)


@dataclass
class GoogleSignInResult:
    user: User | None = None
    refusal: GoogleRefusal | None = None
    #: Nobody uses this Google account or email yet: ask for user type and consent.
    needs_signup: bool = False
    created: bool = False


@dataclass(frozen=True)
class GoogleSignup:
    """What a new Google user is asked before their account is created."""

    name: str
    user_type: UserType
    privacy_notice_version: str


def _usable(user: User) -> bool:
    return user.role == UserRole.USER and not user.is_removed


def find_account(db: Session, identity: GoogleIdentity) -> GoogleSignInResult:
    """The account this Google identity signs in to, linking it by email if need be."""
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is not None:
        return (
            GoogleSignInResult(user=user)
            if _usable(user)
            else GoogleSignInResult(refusal=PASSWORD_ONLY)
        )

    # An email Google has not checked could be anybody's, so it never links or registers.
    if not identity.email_verified:
        return GoogleSignInResult(refusal=EMAIL_UNVERIFIED)

    user = db.scalar(select(User).where(User.email == identity.email))
    if user is None:
        return GoogleSignInResult(needs_signup=True)
    if not _usable(user):
        return GoogleSignInResult(refusal=PASSWORD_ONLY)
    if user.google_sub is not None:
        return GoogleSignInResult(refusal=OTHER_GOOGLE_ACCOUNT)

    user.google_sub = identity.sub
    db.commit()
    return GoogleSignInResult(user=user)


def sign_in_with_google(
    db: Session, identity: GoogleIdentity, signup: GoogleSignup | None = None
) -> GoogleSignInResult:
    """Sign in, link, or (given the answers to the sign-up step) create the account."""
    found = find_account(db, identity)
    if not found.needs_signup or signup is None:
        return found

    if signup.privacy_notice_version != NOTICE_VERSION:
        return GoogleSignInResult(refusal=NOTICE_CHANGED)

    user = User(
        name=signup.name.strip(),
        email=identity.email,
        password_hash=None,
        google_sub=identity.sub,
        role=UserRole.USER,
        user_type=signup.user_type,
        privacy_agreed_at=datetime.now(UTC),
        privacy_notice_version=NOTICE_VERSION,
    )
    db.add(user)
    try:
        events.user_registered(db, user)
        db.commit()
    except IntegrityError:
        # The same person finishing sign-up in two tabs at once: the other tab won, so
        # sign in to the account it created.
        db.rollback()
        return find_account(db, identity)
    db.refresh(user)
    return GoogleSignInResult(user=user, created=True)
