"""How learners do on a lesson, for administrators (SCRUM-84).

Routes stay thin: they call lesson_insights() and turn a ContentProblem into an HTTP error.

- every figure is for one published version (AC4), worked out from the attempts and
  answers recorded by SCRUM-16. Only learners count: administrators never do.
- "right first time" and how often each option was chosen come from each learner's first
  finished run of the version. A retake comes after the explanation, so counting it would
  hide a confusing question. The best score is each learner's best run of the version.
- no figure about a version is shown until 5 learners have finished it (AC3). The same rule
  holds for every smaller group the page shows: newcomers or Singaporeans alone, the
  learners who retook a question, and each week of the trend.
- nothing returned names a learner or carries their id (AC5).
"""

import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import lesson_doc, media
from app.lesson_doc import ChoiceQuestion, LessonDoc
from app.models import (
    AttemptAnswer,
    Lesson,
    LessonAttempt,
    LessonStatus,
    LessonVersion,
    User,
    UserRole,
    UserType,
)
from app.problems import lesson_not_found, version_not_found

MIN_LEARNERS = 5
# Weeks start on Monday in Singapore, where the learners are.
TIMEZONE = ZoneInfo("Asia/Singapore")

Learners = Literal["all", "newcomer", "singaporean"]


@dataclass(frozen=True)
class VersionRef:
    number: int
    published_at: datetime


@dataclass(frozen=True)
class Previous:
    """The version before, when 5 learners finished it too."""

    number: int
    average_best: float
    right_first_time: float | None


@dataclass(frozen=True)
class Summary:
    learners: int
    # Of every learner in the group on SGJio.
    share_of_learners: float
    average_best: float
    # None when the version has nothing to score (only one-option taps).
    right_first_time: float | None
    # Runs that reached the end, out of runs started.
    finish_rate: float
    previous: Previous | None


@dataclass(frozen=True)
class OptionFigures:
    id: str
    text: str
    correct: bool
    # Share of learners who chose it on their first run.
    chosen: float


@dataclass(frozen=True)
class QuestionFigures:
    id: str
    # Its place among the questions, and its card's place in the deck, from 1.
    number: int
    card_number: int
    # The card's Markdown, with its {{blank}}.
    text: str
    right_first_time: float
    # The same question in the version before, when that version has figures.
    previous_right_first_time: float | None
    # Of the learners who got it wrong first time and took the lesson again, the share
    # who got it right on a later run. None when fewer than 5 retook it.
    fixed_on_retake: float | None
    # Right first time for each group, when the page shows everyone and the group has 5.
    newcomers: float | None
    singaporeans: float | None
    options: list[OptionFigures]


@dataclass(frozen=True)
class FunnelStep:
    # The question answered (from 1), or None for reaching the end.
    question: int | None
    runs: int


@dataclass(frozen=True)
class ScoreBucket:
    correct: int
    learners: int


@dataclass(frozen=True)
class TrendSeries:
    """One version's figures for each week in `Trend.weeks`. Learners finishing it are per
    week; the rest are running figures, None until 5 learners have finished it."""

    version: int
    finished: list[int | None]
    average_best: list[float | None]
    right_first_time: list[float | None]
    finish_rate: list[float | None]


@dataclass(frozen=True)
class Trend:
    # Mondays, Singapore time, from the first week with figures to this week.
    weeks: list[date]
    series: list[TrendSeries]


@dataclass(frozen=True)
class LessonInsights:
    id: uuid.UUID
    title: str
    status: LessonStatus
    topic_name: str | None
    # Newest first.
    versions: list[VersionRef]
    version: int | None
    learners: Learners
    min_learners: int
    # Whether 5 learners have finished this version; if not, the figures below are None.
    enough: bool
    summary: Summary | None
    questions: list[QuestionFigures] | None
    funnel: list[FunnelStep] | None
    scores: list[ScoreBucket] | None
    trend: Trend
    # The version's deck and files, so the page can preview exactly what learners saw.
    doc: dict | None
    assets: dict
    reading_seconds: int


# --- Reading the runs ----------------------------------------------------------------------


@dataclass(frozen=True)
class _Run:
    user_id: uuid.UUID
    user_type: UserType | None
    version_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    correct: int
    scored: int
    answers: dict[str, AttemptAnswer]

    @property
    def share(self) -> Fraction:
        # Nothing to score is nothing to get wrong, as in app/learning.py.
        return Fraction(self.correct, self.scored) if self.scored else Fraction(1)


def _runs(db: Session, lesson_id: uuid.UUID, learners: Learners) -> list[_Run]:
    query = (
        select(LessonAttempt, User.user_type)
        .join(User, User.id == LessonAttempt.user_id)
        .where(LessonAttempt.lesson_id == lesson_id, User.role == UserRole.USER)
        .options(selectinload(LessonAttempt.answers))
    )
    if learners != "all":
        query = query.where(User.user_type == UserType(learners))
    return [
        _Run(
            user_id=attempt.user_id,
            user_type=user_type,
            version_id=attempt.version_id,
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            correct=attempt.correct or 0,
            scored=attempt.scored or 0,
            answers={answer.question_id: answer for answer in attempt.answers},
        )
        for attempt, user_type in db.execute(query).all()
    ]


def _learner_count(db: Session, learners: Learners) -> int:
    query = select(func.count()).select_from(User).where(User.role == UserRole.USER)
    if learners != "all":
        query = query.where(User.user_type == UserType(learners))
    return db.scalar(query) or 0


def _scored_questions(doc: LessonDoc) -> list[tuple[int, int, str, ChoiceQuestion]]:
    """(question number, card number, card text, question) for each scored question."""
    found = []
    number = 0
    for card_number, card in enumerate(doc.cards, start=1):
        if card.question is None:
            continue
        number += 1
        if lesson_doc.is_scored(card.question):
            found.append((number, card_number, card.text, card.question))
    return found


# --- One version's figures -----------------------------------------------------------------


class _Figures:
    """What one group of runs on one version says. Runs are a version's, already filtered
    to the group the page shows."""

    def __init__(self, runs: list[_Run]):
        self.runs = runs
        finished = sorted(
            (run for run in runs if run.finished_at is not None),
            key=lambda run: (run.finished_at, run.started_at),
        )
        self.finished = finished
        self.first: dict[uuid.UUID, _Run] = {}
        self.best: dict[uuid.UUID, Fraction] = {}
        for run in finished:
            self.first.setdefault(run.user_id, run)
            self.best[run.user_id] = max(self.best.get(run.user_id, Fraction(0)), run.share)

    @property
    def learners(self) -> int:
        return len(self.first)

    @property
    def enough(self) -> bool:
        return self.learners >= MIN_LEARNERS

    def average_best(self) -> float:
        return _share(sum(self.best.values(), Fraction(0)) / len(self.best))

    def right_first_time(self) -> float | None:
        scored = sum(run.scored for run in self.first.values())
        if not scored:
            return None
        return _share(Fraction(sum(run.correct for run in self.first.values()), scored))

    def finish_rate(self) -> float:
        return _share(Fraction(len(self.finished), len(self.runs)))

    def question_right(self, question_id: str) -> float | None:
        answers = [run.answers.get(question_id) for run in self.first.values()]
        answered = [answer for answer in answers if answer is not None]
        if len(answered) < MIN_LEARNERS:
            return None
        return _share(Fraction(sum(answer.correct for answer in answered), len(answered)))

    def chosen(self, question_id: str) -> Counter[str]:
        return Counter(
            run.answers[question_id].option_id
            for run in self.first.values()
            if question_id in run.answers
        )

    def fixed_on_retake(self, question_id: str) -> float | None:
        retook = fixed = 0
        for user_id, first in self.first.items():
            answer = first.answers.get(question_id)
            if answer is None or answer.correct:
                continue
            later = [
                run
                for run in self.finished
                if run.user_id == user_id and run is not first and question_id in run.answers
            ]
            if later:
                retook += 1
                fixed += any(run.answers[question_id].correct for run in later)
        return _share(Fraction(fixed, retook)) if retook >= MIN_LEARNERS else None


def _share(value: Fraction) -> float:
    return round(float(value), 4)


def _group(runs: list[_Run], user_type: UserType) -> _Figures:
    return _Figures([run for run in runs if run.user_type == user_type])


def _questions(
    doc: LessonDoc, figures: _Figures, previous: _Figures | None, learners: Learners
) -> list[QuestionFigures]:
    newcomers = _group(figures.runs, UserType.NEWCOMER) if learners == "all" else None
    singaporeans = _group(figures.runs, UserType.SINGAPOREAN) if learners == "all" else None
    found = []
    for number, card_number, text, question in _scored_questions(doc):
        assert question.id is not None  # ids are assigned when a lesson is saved
        chosen = figures.chosen(question.id)
        answered = sum(chosen.values())
        found.append(
            QuestionFigures(
                id=question.id,
                number=number,
                card_number=card_number,
                text=text,
                right_first_time=figures.question_right(question.id) or 0.0,
                previous_right_first_time=(
                    previous.question_right(question.id) if previous else None
                ),
                fixed_on_retake=figures.fixed_on_retake(question.id),
                newcomers=newcomers.question_right(question.id) if newcomers else None,
                singaporeans=singaporeans.question_right(question.id) if singaporeans else None,
                options=[
                    OptionFigures(
                        id=option.id or "",
                        text=option.text,
                        correct=option.correct,
                        chosen=_share(Fraction(chosen[option.id], answered)) if answered else 0.0,
                    )
                    for option in question.options
                ],
            )
        )
    return found


def _funnel(doc: LessonDoc, figures: _Figures) -> list[FunnelStep]:
    question_ids = [card.question.id for card in doc.cards if card.question is not None]
    steps = [
        FunnelStep(number, sum(1 for run in figures.runs if question_id in run.answers))
        for number, question_id in enumerate(question_ids, start=1)
    ]
    return [*steps, FunnelStep(None, len(figures.finished))]


def _scores(doc: LessonDoc, figures: _Figures) -> list[ScoreBucket]:
    most = len(_scored_questions(doc))
    counts = Counter(run.correct for run in figures.first.values())
    return [ScoreBucket(correct, counts[correct]) for correct in range(most + 1)]


# --- Over time -----------------------------------------------------------------------------


def _week(moment: datetime) -> date:
    day = moment.astimezone(TIMEZONE).date()
    return day - timedelta(days=day.weekday())


def _trend(versions: list[LessonVersion], runs: list[_Run], now: datetime) -> Trend:
    """Week by week, for each version that has figures: how many learners finished it for
    the first time, and its running average best, right first time and finish rate."""
    with_figures = []
    for version in versions:
        figures = _Figures([run for run in runs if run.version_id == version.id])
        if figures.enough:
            with_figures.append((version, figures))
    if not with_figures:
        return Trend(weeks=[], series=[])

    start = min(_week(figures.finished[0].finished_at) for _, figures in with_figures)  # type: ignore[arg-type]
    this_week = _week(now)
    weeks = []
    week = start
    while week <= this_week:
        weeks.append(week)
        week += timedelta(days=7)

    series = []
    for version, figures in with_figures:
        first_weeks = Counter(_week(run.finished_at) for run in figures.first.values())  # type: ignore[arg-type]
        active_from = min(first_weeks)
        active_to = max(_week(run.finished_at) for run in figures.finished)  # type: ignore[arg-type]
        points: dict[str, list] = {"finished": [], "best": [], "right": [], "rate": []}
        for week in weeks:
            if not active_from <= week <= active_to:
                for values in points.values():
                    values.append(None)
                continue
            end = datetime.combine(week + timedelta(days=7), datetime.min.time(), TIMEZONE)
            so_far = _until(figures.runs, end)
            points["finished"].append(first_weeks.get(week, 0))
            if so_far.enough:
                points["best"].append(so_far.average_best())
                points["right"].append(so_far.right_first_time())
                points["rate"].append(so_far.finish_rate())
            else:
                points["best"].append(None)
                points["right"].append(None)
                points["rate"].append(None)
        series.append(
            TrendSeries(
                version=version.number,
                finished=points["finished"],
                average_best=points["best"],
                right_first_time=points["right"],
                finish_rate=points["rate"],
            )
        )
    return Trend(weeks=weeks, series=series)


def _until(runs: list[_Run], end: datetime) -> _Figures:
    """The runs as they stood at `end`: started by then, and finished only if by then."""
    return _Figures(
        [
            run
            if run.finished_at is None or run.finished_at < end
            else replace(run, finished_at=None)
            for run in runs
            if run.started_at < end
        ]
    )


# --- The page ------------------------------------------------------------------------------


def lesson_insights(
    db: Session,
    lesson_id: uuid.UUID,
    version_number: int | None = None,
    learners: Learners = "all",
    now: datetime | None = None,
) -> LessonInsights:
    """Everything the lesson's insights page shows, for one version (the latest if none is
    given) and one group of learners."""
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise lesson_not_found()
    versions = list(
        db.scalars(
            select(LessonVersion)
            .where(LessonVersion.lesson_id == lesson.id)
            .order_by(LessonVersion.number)
        )
    )
    runs = _runs(db, lesson.id, learners)
    base = {
        "id": lesson.id,
        "title": lesson.title,
        "status": lesson.status,
        "topic_name": lesson.topic.name if lesson.topic else None,
        "versions": [VersionRef(v.number, v.published_at) for v in reversed(versions)],
        "learners": learners,
        "min_learners": MIN_LEARNERS,
        "trend": _trend(versions, runs, now or datetime.now(UTC)),
    }
    if not versions:
        if version_number is not None:
            raise version_not_found()
        return LessonInsights(
            **base,
            version=None,
            enough=False,
            summary=None,
            questions=None,
            funnel=None,
            scores=None,
            doc=None,
            assets={},
            reading_seconds=0,
        )

    by_number = {v.number: v for v in versions}
    version = by_number.get(version_number or versions[-1].number)
    if version is None:
        raise version_not_found()
    doc = LessonDoc.model_validate(version.doc)
    figures = _Figures([run for run in runs if run.version_id == version.id])
    before = by_number.get(version.number - 1)
    previous = _Figures([run for run in runs if run.version_id == before.id]) if before else None
    if previous is not None and not previous.enough:
        previous = None

    shown = {
        "version": version.number,
        "enough": figures.enough,
        "doc": version.doc,
        "assets": media.assets_for(db, doc),
        "reading_seconds": lesson_doc.stats(doc, media.facts_for(db, doc)).reading_seconds,
    }
    if not figures.enough:
        return LessonInsights(
            **base, **shown, summary=None, questions=None, funnel=None, scores=None
        )

    total = _learner_count(db, learners)
    summary = Summary(
        learners=figures.learners,
        share_of_learners=_share(Fraction(figures.learners, total)) if total else 0.0,
        average_best=figures.average_best(),
        right_first_time=figures.right_first_time(),
        finish_rate=figures.finish_rate(),
        previous=(
            Previous(
                number=before.number,  # type: ignore[union-attr]
                average_best=previous.average_best(),
                right_first_time=previous.right_first_time(),
            )
            if previous
            else None
        ),
    )
    return LessonInsights(
        **base,
        **shown,
        summary=summary,
        questions=_questions(doc, figures, previous, learners),
        funnel=_funnel(doc, figures),
        scores=_scores(doc, figures),
    )
