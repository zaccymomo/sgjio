"""Request and response shapes for Identity's routes (moved unchanged from the monolith)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from app.auth import normalise_email
from app.models import AdminAction, UserRole, UserType
from app.profile_options import INTERESTS, LANGUAGES, NEIGHBOURHOODS

# Email syntax check for registration. Built once: TypeAdapter compiles a validator.
_EMAIL = TypeAdapter(EmailStr)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    user_type: UserType | None
    created_at: datetime
    # Accounts created with Google have no password: they always sign in with Google
    # (SCRUM-92). Settings uses these to show what applies.
    has_password: bool
    google_linked: bool
    # Empty until the introduction is finished or skipped; the main app shows it until
    # then (SCRUM-94).
    intro_finished_at: datetime | None


class RegisterRequest(BaseModel):
    """A new main-app account (SCRUM-61). Administrators are invited from the portal."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=254)
    # Length only: which password rule failed is reported by password_rule_failures() so the
    # user is told the rule rather than a schema message (SCRUM-61 AC4).
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(min_length=1, max_length=256)
    # Required, so leaving it unselected is refused (SCRUM-61 AC6). Self-reported.
    user_type: UserType
    privacy_consent: bool
    privacy_notice_version: str

    @field_validator("privacy_consent")
    @classmethod
    def _require_privacy_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Agree to the privacy notice before creating an account.")
        return value

    @field_validator("name")
    @classmethod
    def _require_a_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter your name.")
        return value

    @field_validator("email")
    @classmethod
    def _require_a_valid_email(cls, value: str) -> str:
        """SCRUM-61 AC3. Checked with email-validator, but reported in plain language."""
        value = normalise_email(value)
        try:
            _EMAIL.validate_python(value)
        except ValidationError:
            raise ValueError("Enter an email address like name@example.com.") from None
        return value


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(min_length=1, max_length=256)


class DeleteAccountRequest(BaseModel):
    """Confirmed with the password, or with Google for an account that has none (SCRUM-92)."""

    password: str | None = Field(default=None, max_length=256)
    id_token: str | None = Field(default=None, max_length=4096)


class GoogleSignup(BaseModel):
    """The sign-up step for someone new to SGJio who continued with Google (SCRUM-92).
    Their email comes from Google; the name starts as Google's and can be changed."""

    name: str = Field(min_length=1, max_length=120)
    user_type: UserType
    privacy_consent: bool
    privacy_notice_version: str

    @field_validator("name")
    @classmethod
    def _require_a_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter your name.")
        return value

    @field_validator("privacy_consent")
    @classmethod
    def _require_privacy_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Agree to the privacy notice before creating an account.")
        return value


class GoogleSignInRequest(BaseModel):
    # The Firebase ID token from Google's sign-in window.
    id_token: str = Field(min_length=1, max_length=4096)
    # Sent only after an answer of "needs_signup", with the same token.
    signup: GoogleSignup | None = None


class GoogleSignInResponse(BaseModel):
    """Either signed in, or the name and email to greet a new person with at sign-up."""

    status: Literal["signed_in", "needs_signup"]
    user: UserOut | None = None
    # True when this request created the account, so the page goes to profile setup.
    created: bool = False
    name: str | None = None
    email: str | None = None


class RegisterResponse(BaseModel):
    """Registration signs the new user in, so it answers like sign-in (SCRUM-61 AC1)."""

    user: UserOut


class AdminInviteRequest(BaseModel):
    """A new administrator, invited from the portal (SCRUM-81 AC2)."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=254)
    # Set once the person adding them has confirmed an email outside ADMIN_EMAIL_DOMAIN.
    allow_other_domain: bool = False

    @field_validator("name")
    @classmethod
    def _require_a_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter their name.")
        return value

    @field_validator("email")
    @classmethod
    def _require_a_valid_email(cls, value: str) -> str:
        value = normalise_email(value)
        try:
            _EMAIL.validate_python(value)
        except ValidationError:
            raise ValueError("Enter an email address like name@example.com.") from None
        return value


class AdminOut(BaseModel):
    """An administrator on the Administrators page (SCRUM-81 AC1)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    status: Literal["active", "invited", "removed"]
    added_at: datetime
    added_by: str | None = Field(description="Who invited them; empty if seeded or unknown")
    last_sign_in_at: datetime | None
    invited_at: datetime | None = Field(description="When the latest invite was sent")
    invite_expires_at: datetime | None
    removed_at: datetime | None
    removed_by: str | None
    is_you: bool


class AdminActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: AdminAction
    at: datetime
    admin_id: uuid.UUID
    admin_name: str
    actor_id: uuid.UUID | None = Field(description="Empty: the person themselves, or the CLI")
    actor_name: str | None


class AdminsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    admins: list[AdminOut] = Field(description="Active and invited, by name")
    removed: list[AdminOut] = Field(description="Most recently removed first")
    activity: list[AdminActivityOut] = Field(description="Latest changes first")
    email_domain: str | None = Field(description="Emails outside it need confirming")
    invite_hours: int


class InviteOut(BaseModel):
    """Who an invite link is for, so its page can greet them (SCRUM-81)."""

    name: str
    email: str
    invited_by: str | None


class SignInRequest(BaseModel):
    # Not validated as an email on purpose: any wrong input gets the same general
    # "email or password is incorrect" message (SCRUM-62 AC2, SCRUM-68 AC2).
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SignInResponse(BaseModel):
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    # Not validated as an email, and never refused for an unknown one: the answer is the
    # same whatever is sent, so the page cannot be used to check who has an account
    # (SCRUM-63 AC2, SCRUM-69 AC2).
    email: str = Field(min_length=1, max_length=254)


class ResetTokenRequest(BaseModel):
    """The token from an emailed reset link. Sent in the body so it stays out of logs."""

    token: str = Field(min_length=1, max_length=256)


class ResetPasswordRequest(ResetTokenRequest):
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(min_length=1, max_length=256)


class ProfileOptionsOut(BaseModel):
    interests: list[str]
    languages: list[str]
    neighbourhoods: list[str]


class ProfileOut(BaseModel):
    """The signed-in user's own matching preferences. Empty until profile setup is done."""

    model_config = ConfigDict(from_attributes=True)

    interests: list[str] = []
    languages: list[str] = []
    neighbourhood: str | None = None


def _choices(values: list[str], allowed: list[str], what: str) -> list[str]:
    """Keep the order given, drop repeats, and refuse anything not offered."""
    unique = list(dict.fromkeys(values))
    unknown = [value for value in unique if value not in allowed]
    if unknown:
        raise ValueError(f"Choose {what} from the list.")
    return unique


class ProfileIn(BaseModel):
    """Profile setup and editing (SCRUM-14 AC1, AC4). Every field is required (AC2)."""

    interests: list[str] = Field(max_length=len(INTERESTS))
    languages: list[str] = Field(max_length=len(LANGUAGES))
    # Validated even when left out, so a missing neighbourhood gets the plain message.
    neighbourhood: str | None = Field(default=None, validate_default=True)

    @field_validator("interests")
    @classmethod
    def _check_interests(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Select at least one interest.")
        return _choices(value, INTERESTS, "interests")

    @field_validator("languages")
    @classmethod
    def _check_languages(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Select at least one language you speak.")
        return _choices(value, LANGUAGES, "languages")

    @field_validator("neighbourhood")
    @classmethod
    def _check_neighbourhood(cls, value: str | None) -> str:
        if not value:
            raise ValueError("Select your neighbourhood.")
        if value not in NEIGHBOURHOODS:
            raise ValueError("Choose a neighbourhood from the list.")
        return value


class ErrorDetail(BaseModel):
    """Shape of `detail` in every error response the front ends need to understand."""

    code: str
    message: str
