"""Shared authentication plumbing (SCRUM-73).

Stories add their pages and rules on top of these building blocks:

- sessions.py  create, look up, extend and end signed-in sessions
- lockout.py   block repeated failed sign-ins
- service.py   sign in (credentials + lockout + session) for either front end
- reset.py     one-time password reset links (used with app.mailer)
- google.py    sign in and register with a Google ID token (SCRUM-92)
- deps.py      FastAPI guards: require_user, require_admin
"""


def normalise_email(email: str) -> str:
    """Emails are compared and stored lower-case with surrounding spaces removed."""
    return email.strip().lower()
