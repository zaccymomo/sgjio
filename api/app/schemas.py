"""Request and response shapes shared across routers."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

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
from app.lesson_doc import LessonDoc
from app.models import LessonStatus, UserRole, UserType
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


class TopicLessonOut(BaseModel):
    """One lesson in a topic's list (SCRUM-53). Never says which options are right."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    questions: int
    completed: bool
    best_correct: int | None
    best_scored: int | None
    last_attempted_at: datetime | None


class TopicLessonsOut(BaseModel):
    """A topic opened from its circle: its figure and its published lessons (SCRUM-53), and
    its description, empty if it has none (SCRUM-86)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    completed: int
    available: int
    lessons: list[TopicLessonOut]


TopicName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
# Matches topics.description (String(200)). Empty means the topic has none.
TopicDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class TopicRequest(BaseModel):
    """Create or edit a topic (SCRUM-57, SCRUM-86). Both fields are trimmed before the length
    check. Leaving `description` out keeps the current one (empty for a new topic); an empty
    string clears it."""

    name: TopicName
    description: TopicDescription | None = None


class TopicOut(BaseModel):
    """A topic as the admin portal lists it. Counts cover lessons of every status."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    archived_at: datetime | None
    position: int
    lesson_count: int
    published_count: int


# --- Content order (SCRUM-66) -------------------------------------------------------------

# Far more than the portal will ever hold, but a bound on what one request can send.
MAX_ORDER_IDS = 1000


class LessonSummaryOut(BaseModel):
    """A lesson as the admin portal lists it. The cards are left out to keep the list light."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    updated_at: datetime
    position: int
    deletable: bool
    has_unpublished_changes: bool
    version: int | None
    cards: int
    questions: int
    cover_asset_id: uuid.UUID | None


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


# --- Lessons (SCRUM-19, SCRUM-64, SCRUM-52) ------------------------------------------------
# What a lesson "is" lives in app/lesson_doc.py and, for both front ends, in
# packages/ui/src/lesson/types.ts. A change to the lesson's fields should touch those, not
# every route and page.

# Matches lessons.title (String(200)) and lessons.summary (String(160)).
MAX_LESSON_TITLE = 200
MAX_LESSON_SUMMARY = 160

LessonTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_LESSON_TITLE)]
LessonSummaryText = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=MAX_LESSON_SUMMARY)
]


class LessonFields(BaseModel):
    """A draft's fields as the editor saves them. Any may be empty: what publishing needs
    is reported as issues instead (SCRUM-56, SCRUM-70). `topic_id: null` means no topic."""

    title: LessonTitle = ""
    summary: LessonSummaryText = ""
    topic_id: uuid.UUID | None = None
    doc: LessonDoc = Field(default_factory=LessonDoc)


class LessonCreateRequest(LessonFields):
    """A new draft. Every field is optional, so a script can create a whole lesson in one
    request and then publish it."""


class LessonUpdateRequest(LessonFields):
    """Change a draft. Fields left out keep their value.

    `updated_at` is the "last updated" time the editor loaded. If the lesson has changed
    since, the save is refused (lesson_out_of_date) rather than overwriting that change.
    """

    updated_at: AwareDatetime

    def changes(self) -> dict:
        """Only the lesson fields the request actually sent, `doc` still as a model."""
        sent = self.model_fields_set & set(LessonFields.model_fields)
        return {name: getattr(self, name) for name in sent}


class LessonChangeRequest(BaseModel):
    """Publish, discard changes, withdraw or restore, naming the version the page loaded."""

    updated_at: AwareDatetime


class IssueOut(BaseModel):
    """Something that stops the lesson being published (blocker) or is worth a look."""

    model_config = ConfigDict(from_attributes=True)

    severity: Literal["blocker", "warning"]
    code: str
    message: str
    card_id: str | None
    field: str | None


class StatsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cards: int
    questions: int
    scored_questions: int
    words: int
    audio_seconds: int
    reading_seconds: int


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    published_at: datetime


class AssetOut(BaseModel):
    """An image or audio file, with what a page needs to show it before it has loaded."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: Literal["image", "audio"]
    mime: str
    url: str
    size: int
    width: int | None
    height: int | None
    duration_ms: int | None
    # A tiny blurred copy as a data: URL, and the image's main colour as #rrggbb.
    placeholder: str | None
    color: str | None
    filename: str


class LessonOut(BaseModel):
    """One lesson as the editor needs it: the draft, what still blocks publishing, counts,
    and the images and audio its cards use. `deletable` is true only for a lesson that has
    never been published; `version` is the latest published one."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str | None
    title: str
    summary: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    published_at: datetime | None
    withdrawn_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime
    deletable: bool
    has_unpublished_changes: bool
    version: VersionOut | None
    doc: LessonDoc
    issues: list[IssueOut]
    stats: StatsOut
    assets: dict[str, AssetOut]


# --- Learners (SCRUM-15, SCRUM-16) ---------------------------------------------------------


class LearnerOptionOut(BaseModel):
    """An option as a learner receives it: whether it is right stays on the server."""

    id: str
    text: str


class LearnerQuestionOut(BaseModel):
    type: Literal["choice"]
    id: str
    options: list[LearnerOptionOut]
    # False for a one-option tap, which always succeeds and isn't counted.
    scored: bool


class LearnerImageOut(BaseModel):
    asset_id: uuid.UUID
    alt: str


class LearnerAudioOut(BaseModel):
    asset_id: uuid.UUID
    transcript: str


class LearnerCardOut(BaseModel):
    type: Literal["story"]
    id: str
    text: str
    image: LearnerImageOut | None
    audio: LearnerAudioOut | None
    question: LearnerQuestionOut | None


class TopicRefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class LearnerLessonOut(BaseModel):
    """A published lesson's latest version as learners see it (packages/ui LearnerCard)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    title: str
    summary: str
    topic: TopicRefOut
    reading_seconds: int
    cards: list[LearnerCardOut]
    assets: dict[str, AssetOut]


class AttemptStartRequest(BaseModel):
    """The version the learner was shown; refused if a newer one has been published."""

    version: int = Field(ge=1)


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID


class AnswerRequest(BaseModel):
    question_id: str = Field(min_length=1, max_length=40)
    option_id: str = Field(min_length=1, max_length=40)


class CheckResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correct: bool
    correct_option_id: str
    why_not: str
    explanation: str


class ScoreOut(BaseModel):
    """First-try correct answers out of the scored questions."""

    model_config = ConfigDict(from_attributes=True)

    correct: int
    scored: int


class AttemptResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attempt_id: uuid.UUID
    lesson_id: uuid.UUID
    score: ScoreOut
    best: ScoreOut
    first_completion: bool
