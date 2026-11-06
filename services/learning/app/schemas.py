"""Request and response shapes for Learning's routes, as the monolith's app/schemas.py
defined them (the front ends read exactly these)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    exempted: int
    available: int
    # SCRUM-100: the level reached in the topic, 0 to 5, drawn on the Profile tab's chart.
    level: int


class SuggestionOut(BaseModel):
    """The suggested next lesson beside the circles (SCRUM-6, SCRUM-106)."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    topic_id: uuid.UUID
    topic_name: str
    # SCRUM-107: one line on why this lesson, never mentioning a level.
    reason: str


class ProgressOut(BaseModel):
    """Every circle plus the overall figure, as defined in SCRUM-16 AC7, and the suggested
    next lesson, null once everything available is completed (SCRUM-6)."""

    model_config = ConfigDict(from_attributes=True)

    topics: list[TopicProgressOut]
    completed: int
    exempted: int
    available: int
    suggestion: SuggestionOut | None
    aptitude_taken: bool


class MistakeOut(BaseModel):
    """A question answered wrongly, as its lesson reads now (SCRUM-44)."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: uuid.UUID
    lesson_title: str
    topic_name: str
    question_id: str
    text: str
    chosen: str
    correct: str
    explanation: str
    why_not: str
    answered_at: datetime


class ReviewOut(BaseModel):
    mistakes: list[MistakeOut]


class TopicLessonOut(BaseModel):
    """One lesson in a topic's list (SCRUM-53). Never says which options are right."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    summary: str
    reading_seconds: int
    questions: int
    completed: bool
    exempted: bool
    best_correct: int | None
    best_scored: int | None
    last_attempted_at: datetime | None
    level: int


class TopicLessonsOut(BaseModel):
    """A topic opened from its circle: its figure and its published lessons (SCRUM-53), and
    its description, empty if it has none (SCRUM-86)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    completed: int
    exempted: int
    available: int
    lessons: list[TopicLessonOut]


class LessonSearchResultOut(BaseModel):
    """One lesson found by search (SCRUM-85): its title, topic and whether this user has
    completed it, and the card text that matched. Never says which options are right."""

    model_config = ConfigDict(from_attributes=True)

    lesson_id: uuid.UUID
    title: str
    topic_id: uuid.UUID
    topic_name: str
    completed: bool
    snippet: str | None


class AptitudeOptionOut(BaseModel):
    id: str
    text: str


class AptitudeQuizQuestionOut(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID
    topic: str
    level: int
    prompt: str
    options: list[AptitudeOptionOut]
    topic_index: int
    topic_count: int


class AptitudeStepOut(BaseModel):
    done: bool
    question: AptitudeQuizQuestionOut | None


class AptitudeAnswerIn(BaseModel):
    question_id: uuid.UUID
    option_id: str = Field(min_length=1, max_length=40)


class AptitudeSubmitIn(BaseModel):
    answers: list[AptitudeAnswerIn] = Field(min_length=1, max_length=30)


class AptitudeNextIn(AptitudeSubmitIn):
    pass


class AptitudePlacementOut(BaseModel):
    topic_id: uuid.UUID
    topic: str
    level: int
    # SCRUM-100 AC1: "4 of 12 exempted", counting currently published lessons only.
    exempted: int
    available: int


class AptitudeResultOut(BaseModel):
    correct: int
    total: int
    taken_at: datetime
    placements: list[AptitudePlacementOut]


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


# --- Lesson insights (SCRUM-84) ------------------------------------------------------------
# Shares are fractions from 0 to 1. Figures are None where fewer than 5 learners are behind
# them, and nothing here names a learner.


class InsightsPreviousOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    average_best: float
    right_first_time: float | None


class InsightsSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    learners: int
    share_of_learners: float
    average_best: float
    right_first_time: float | None
    finish_rate: float
    previous: InsightsPreviousOut | None


class InsightsOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    correct: bool
    chosen: float


class InsightsQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    number: int
    card_number: int
    text: str
    right_first_time: float
    previous_right_first_time: float | None
    fixed_on_retake: float | None
    newcomers: float | None
    singaporeans: float | None
    options: list[InsightsOptionOut]


class InsightsFunnelStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question: int | None
    runs: int


class InsightsScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    correct: int
    learners: int


class InsightsTrendSeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    finished: list[int | None]
    average_best: list[float | None]
    right_first_time: list[float | None]
    finish_rate: list[float | None]


class InsightsTrendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weeks: list[date]
    series: list[InsightsTrendSeriesOut]


class LessonInsightsOut(BaseModel):
    """How learners do on one version of a lesson. `enough` is false until 5 learners have
    finished that version, and then every figure is null. `doc` and `assets` are the
    version's deck, for previewing exactly what learners saw."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    # "draft" only for a lesson Learning has never seen published.
    status: Literal["draft", "published", "withdrawn"]
    topic_name: str | None
    versions: list[VersionOut]
    version: int | None
    learners: Literal["all", "newcomer", "singaporean"]
    min_learners: int
    enough: bool
    summary: InsightsSummaryOut | None
    questions: list[InsightsQuestionOut] | None
    funnel: list[InsightsFunnelStepOut] | None
    scores: list[InsightsScoreOut] | None
    trend: InsightsTrendOut
    doc: dict | None
    assets: dict[str, AssetOut]
    reading_seconds: int


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
    # This completion finished every published lesson in the topic (SCRUM-55 AC1).
    topic_completed: bool
