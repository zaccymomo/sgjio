"""Request and response shapes shared across routers."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    AwareDatetime,
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
from app.models import LessonStatus, UserRole, UserType

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
    position: int
    lesson_count: int
    published_count: int


# --- Content order (SCRUM-66) -------------------------------------------------------------

# Far more than the portal will ever hold, but a bound on what one request can send.
MAX_ORDER_IDS = 1000


class LessonSummaryOut(BaseModel):
    """A lesson as the admin portal lists it. The body is left out to keep the list light."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    updated_at: datetime
    position: int


class OrderRequest(BaseModel):
    """A list's ids in the new order, and in the order the page showed before the move.

    The second list is how the server notices a page that is out of date (check_reorder).
    """

    ids: list[uuid.UUID] = Field(max_length=MAX_ORDER_IDS)
    previous_ids: list[uuid.UUID] = Field(max_length=MAX_ORDER_IDS)


class TopicOrderRequest(OrderRequest):
    """Every active topic, in the new order and in the order the page showed."""


class LessonOrderRequest(OrderRequest):
    """Every lesson's id in one topic, in the new order and in the order the page showed.

    `topic_id` is required but may be null, meaning the lessons with no topic. Requiring it
    means a request that forgets it is refused instead of reordering the wrong group.
    """

    topic_id: uuid.UUID | None


# --- Lessons (SCRUM-64) -------------------------------------------------------------------
# What a lesson "is" lives here and, in the admin portal, in admin/src/lib/lessons.ts and
# admin/src/components/LessonForm.tsx. A change to the lesson's fields should touch these,
# not every route and page.

# Matches lessons.title (String(200)).
MAX_LESSON_TITLE = 200
# A lesson should take under 2 minutes to read: about 400 words, or 2,500 characters.
# Drafts get ten times that, for pasted notes, while still bounding one request.
MAX_LESSON_CONTENT = 20_000

LessonTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_LESSON_TITLE)]
LessonContent = Annotated[str, Field(max_length=MAX_LESSON_CONTENT)]


class LessonFields(BaseModel):
    """A draft's fields as the editor saves them. Any may be empty: required fields are
    checked when publishing (SCRUM-56, SCRUM-70). `topic_id: null` means no topic yet."""

    title: LessonTitle = ""
    content: LessonContent = ""
    topic_id: uuid.UUID | None = None


class LessonCreateRequest(LessonFields):
    """A new draft. Every field is optional."""


class LessonUpdateRequest(LessonFields):
    """Change a draft. Fields left out keep their value.

    `updated_at` is the "last updated" time the editor loaded. If the lesson has changed
    since, the save is refused (lesson_out_of_date) rather than overwriting that change.
    """

    updated_at: AwareDatetime

    def changes(self) -> dict:
        """Only the lesson fields the request actually sent."""
        return self.model_dump(include=self.model_fields_set & set(LessonFields.model_fields))


class LessonOut(BaseModel):
    """One lesson, body included, for the editor. `deletable` is true only for a draft
    that has never been published."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    published_at: datetime | None
    withdrawn_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime
    deletable: bool
