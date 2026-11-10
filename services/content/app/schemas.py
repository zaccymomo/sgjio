"""Request and response shapes for Content's routes, moved from the monolith's schemas.py
unchanged (the front ends depend on them byte for byte)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.lesson_doc import LessonDoc
from app.models import (
    MAX_LEVEL,
    MIN_LEVEL,
    LessonOrigin,
    LessonStatus,
    ReportReason,
    ReportStatus,
)

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
    # Published lessons at Level 1 to 5, in that order (SCRUM-103 AC5).
    published_by_level: list[int]


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
    level: int
    deletable: bool
    has_unpublished_changes: bool
    version: int | None
    cards: int
    questions: int
    cover_asset_id: uuid.UUID | None
    open_reports: int


# --- Aptitude quiz (SCRUM-96, SCRUM-97) -------------------------------------------------


class AptitudeOptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=300)
    correct: bool = False


class AptitudeQuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_id: uuid.UUID
    level: int = Field(ge=1, le=5)
    prompt: str = Field(min_length=1, max_length=1000)
    options: list[AptitudeOptionIn] = Field(min_length=2, max_length=6)
    is_active: bool = True


class AptitudeQuestionUpdate(BaseModel):
    """Level is deliberately absent and extra fields are rejected: it is immutable."""

    model_config = ConfigDict(extra="forbid")

    topic_id: uuid.UUID | None = None
    prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    options: list[AptitudeOptionIn] | None = Field(default=None, min_length=2, max_length=6)
    is_active: bool | None = None


class AptitudeOptionOut(BaseModel):
    id: str
    text: str


class AptitudeQuestionOut(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    topic_name: str
    level: int
    prompt: str
    options: list[AptitudeOptionOut]
    correct_option_id: str
    is_active: bool
    updated_at: datetime


class AptitudeBankOut(BaseModel):
    ready: bool
    topics: list["AptitudeTopicReadinessOut"]
    questions: list[AptitudeQuestionOut]


class AptitudeTopicReadinessOut(BaseModel):
    topic_id: uuid.UUID
    topic_name: str
    ready: bool
    counts_by_level: dict[int, int]


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
LessonLevel = Annotated[int, Field(ge=MIN_LEVEL, le=MAX_LEVEL)]


class LessonFields(BaseModel):
    """A draft's fields as the editor saves them. Any may be empty: what publishing needs
    is reported as issues instead (SCRUM-56, SCRUM-70). `topic_id: null` means no topic."""

    title: LessonTitle = ""
    summary: LessonSummaryText = ""
    topic_id: uuid.UUID | None = None
    doc: LessonDoc = Field(default_factory=LessonDoc)


class LessonCreateRequest(LessonFields):
    """A new draft. Only `level` is required (SCRUM-103 AC1); the rest may be filled in
    later, or all sent at once so a script can create a whole lesson and then publish it."""

    level: LessonLevel


class LessonUpdateRequest(LessonFields):
    """Change a draft. Fields left out keep their value.

    `updated_at` is the "last updated" time the editor loaded. If the lesson has changed
    since, the save is refused (lesson_out_of_date) rather than overwriting that change.
    """

    updated_at: AwareDatetime
    # Can change only until the lesson is first published (level_locked).
    level: LessonLevel | None = None

    def changes(self) -> dict:
        """Only the lesson fields the request actually sent, `doc` still as a model."""
        sent = self.model_fields_set & {*LessonFields.model_fields, "level"}
        if self.level is None:
            sent.discard("level")  # "level": null changes nothing, like leaving it out
        return {name: getattr(self, name) for name in sent}


class LessonChangeRequest(BaseModel):
    """Publish, discard changes, withdraw or restore, naming the version the page loaded."""

    updated_at: AwareDatetime


class LessonPublishRequest(LessonChangeRequest):
    """`reviewed` is the editor's "I have reviewed every card" tick, needed only for an AI
    draft's first publish (review_required); other lessons may leave it out."""

    reviewed: bool = False


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
    never been published, which is also when its `level` can still change; `version` is the
    latest published one."""

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
    level: int
    created_at: datetime
    updated_at: datetime
    deletable: bool
    has_unpublished_changes: bool
    version: VersionOut | None
    # "ai" for a draft the AI wrote; `ai_reviewed_at` is when its first publish was reviewed.
    origin: LessonOrigin
    ai_reviewed_at: datetime | None
    doc: LessonDoc
    issues: list[IssueOut]
    stats: StatsOut
    assets: dict[str, AssetOut]


# --- AI drafts (docs/ai-lessons-api.md, "Content") -----------------------------------------

GenerationNotes = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class GenerationRequest(BaseModel):
    """ "Generate draft": topic, level, what to teach, and length in cards."""

    topic_id: uuid.UUID
    level: LessonLevel
    notes: GenerationNotes
    cards: Literal[4, 6, 8]


class GenerationFailureOut(BaseModel):
    code: str
    message: str


class GenerationJobOut(BaseModel):
    """A request as the dialog polls it. `lesson_id` is set once `status` is done;
    `left_today` is the signed-in administrator's remaining requests."""

    id: uuid.UUID
    status: Literal["requested", "writing", "done", "failed"]
    lesson_id: uuid.UUID | None
    failure: GenerationFailureOut | None
    left_today: int


class GenerationQuotaOut(BaseModel):
    daily_limit: int
    left_today: int


# --- Reported problems (SCRUM-82, SCRUM-83) ------------------------------------------------

MAX_REPORT_NOTE = 500


class ReportRequest(BaseModel):
    """A problem on one card of the version the learner was shown (SCRUM-82)."""

    version: int = Field(ge=1)
    card_id: str = Field(min_length=1, max_length=40)
    reason: ReportReason
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_REPORT_NOTE)] = ""


class ReportSentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class ReportOut(BaseModel):
    """A reported problem as administrators see it: never who sent it (SCRUM-83 AC1)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lesson_id: uuid.UUID
    lesson_title: str
    topic_name: str | None
    version: int
    card_id: str
    card_number: int | None
    card_excerpt: str
    card_in_draft: bool
    reason: ReportReason
    note: str
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None


class ReportStatusRequest(BaseModel):
    """Fixed or Dismissed takes a report off the open list (AC3); Open puts it back."""

    status: ReportStatus
