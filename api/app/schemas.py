"""Request and response shapes shared across routers."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)

from app.auth import normalise_email
from app.models import UserRole, UserType

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


TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class TopicRequest(BaseModel):
    """Create or rename a topic (SCRUM-57). The name is trimmed before the length check."""

    name: TopicName


class TopicOut(BaseModel):
    """A topic as the admin portal lists it. Counts cover lessons of every status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    archived_at: datetime | None
    lesson_count: int
    published_count: int
