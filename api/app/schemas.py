"""Request and response shapes shared across routers."""

import uuid
from datetime import datetime

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
from app.models import UserRole, UserType
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


class RegisterRequest(BaseModel):
    """A new main-app account (SCRUM-61). Administrators are made with `app.cli`, not here."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=254)
    # Length only: which password rule failed is reported by password_rule_failures() so the
    # user is told the rule rather than a schema message (SCRUM-61 AC4).
    password: str = Field(min_length=1, max_length=256)
    password_confirmation: str = Field(min_length=1, max_length=256)
    # Required, so leaving it unselected is refused (SCRUM-61 AC6). Self-reported.
    user_type: UserType

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


class RegisterResponse(BaseModel):
    """Registration signs the new user in, so it answers like sign-in (SCRUM-61 AC1)."""

    user: UserOut


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


class TopicProgressOut(BaseModel):
    """One progress circle on the landing page (SCRUM-43)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    completed: int
    available: int


class ProgressOut(BaseModel):
    """Every circle plus the overall figure, as defined in SCRUM-16 AC7."""

    model_config = ConfigDict(from_attributes=True)

    topics: list[TopicProgressOut]
    completed: int
    available: int
