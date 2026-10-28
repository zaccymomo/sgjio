"""Learners taking lessons: reading a lesson, checking answers and recording attempts
(SCRUM-15, SCRUM-16).

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- learners only ever see a published lesson in a topic that is not archived, and always its
  latest version. Their copy never says which option is right: answers are checked here,
  on the server (SCRUM-16 AC1).
- an attempt is one run through the deck. The page starts one at the first answer, naming
  the version it was shown; if a newer version has been published since, it is refused, so
  the learner reloads and gets the newest one.
- the first answer to each question in an attempt is the one that counts. Sending it again,
  or sending another answer to the same question, records nothing and returns the first
  result (AC6). An answer that is not one of the question's options, or to a lesson that is
  no longer published, is refused and records nothing (AC2).
- finishing needs every question answered. It completes the lesson the first time, right or
  wrong (AC3), and keeps the best score: first-try correct answers out of the scored
  questions, compared as a percentage, a tie keeping the most recent (AC4, AC5). Finishing
  the same attempt again changes nothing.
- the finish that completes the last lesson still open in a topic says so, so the page can
  acknowledge the topic (SCRUM-55 AC1). Only a first completion can do that, so retakes in a
  finished topic do not repeat it.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import lesson_doc, media
from app.lesson_doc import ChoiceQuestion, LessonDoc
from app.lessons import latest_version
from app.models import (
    AttemptAnswer,
    Lesson,
    LessonAttempt,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
)
from app.problems import (
    attempt_finished,
    attempt_not_found,
    lesson_unavailable,
    lesson_updated,
    option_not_found,
    question_not_found,
    questions_unanswered,
)


@dataclass(frozen=True)
class TopicRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class LearnerLesson:
    id: uuid.UUID
    version: int
    title: str
    summary: str
    topic: TopicRef
    reading_seconds: int
    # Cards as app/schemas.py's LearnerCardOut, with options shuffled where the lesson says.
    cards: list[dict]
    assets: dict


@dataclass(frozen=True)
class CheckResult:
    correct: bool
    correct_option_id: str
    # Why the chosen option isn't the norm, when it is wrong and the lesson says.
    why_not: str
    explanation: str


@dataclass(frozen=True)
class Score:
    correct: int
    scored: int


@dataclass(frozen=True)
class AttemptResult:
    attempt_id: uuid.UUID
    lesson_id: uuid.UUID
    score: Score
    best: Score
    # True when this attempt is the one that completed the lesson.
    first_completion: bool
    # True when that completion was the last one the topic needed (SCRUM-55 AC1).
    topic_completed: bool = False


# --- Reading -------------------------------------------------------------------------------


def published_lesson(db: Session, lesson_id: uuid.UUID) -> Lesson:
    """The lesson if learners may see it: published, in a topic that is not archived."""
    lesson = db.get(Lesson, lesson_id)
    if (
        lesson is None
        or lesson.status != LessonStatus.PUBLISHED
        or lesson.topic is None
        or lesson.topic.archived_at is not None
    ):
        raise lesson_unavailable()
    return lesson


def _learner_question(question: ChoiceQuestion, rng: random.Random) -> dict:
    options = [{"id": option.id, "text": option.text} for option in question.options]
    if question.shuffle:
        rng.shuffle(options)
    return {
        "type": question.type,
        "id": question.id,
        "options": options,
        "scored": lesson_doc.is_scored(question),
    }


def learner_lesson(
    db: Session, lesson_id: uuid.UUID, rng: random.Random | None = None
) -> LearnerLesson:
    """The latest version of a published lesson as a learner sees it (SCRUM-15 AC1)."""
    lesson = published_lesson(db, lesson_id)
    version = latest_version(db, lesson.id)
    if version is None:
        raise lesson_unavailable()
    doc = LessonDoc.model_validate(version.doc)
    rng = rng or random.Random()
    cards = [
        {
            "type": card.type,
            "id": card.id,
            "text": card.text,
            "image": card.image.model_dump(mode="json") if card.image else None,
            "audio": card.audio.model_dump(mode="json") if card.audio else None,
            "question": _learner_question(card.question, rng) if card.question else None,
        }
        for card in doc.cards
    ]
    topic: Topic = lesson.topic  # type: ignore[assignment]  # checked in published_lesson
    return LearnerLesson(
        id=lesson.id,
        version=version.number,
        title=version.title,
        summary=version.summary,
        topic=TopicRef(topic.id, topic.name),
        reading_seconds=lesson_doc.stats(doc, media.facts_for(db, doc)).reading_seconds,
        cards=cards,
        assets=media.assets_for(db, doc),
    )


# --- Attempts ------------------------------------------------------------------------------


def start_attempt(
    db: Session, user_id: uuid.UUID, lesson_id: uuid.UUID, version: int
) -> LessonAttempt:
    """Start a run through the version the learner was shown, which must be the latest."""
    lesson = published_lesson(db, lesson_id)
    latest = latest_version(db, lesson.id)
    if latest is None:
        raise lesson_unavailable()
    if latest.number != version:
        raise lesson_updated()
    attempt = LessonAttempt(user_id=user_id, lesson_id=lesson.id, version_id=latest.id)
    db.add(attempt)
    db.commit()
    return attempt


def _locked_attempt(db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID) -> LessonAttempt:
    """The user's own attempt, locked so two requests for it run one after the other.

    Another user's attempt is answered as missing, so ids cannot be probed."""
    attempt = db.scalar(
        select(LessonAttempt)
        .where(LessonAttempt.id == attempt_id, LessonAttempt.user_id == user_id)
        .with_for_update()
    )
    if attempt is None:
        raise attempt_not_found()
    return attempt


def _questions(version: LessonVersion) -> list[ChoiceQuestion]:
    doc = LessonDoc.model_validate(version.doc)
    return [card.question for card in doc.cards if card.question is not None]


def _result(question: ChoiceQuestion, option_id: str) -> CheckResult:
    answer = lesson_doc.correct_option(question)
    correct = answer is not None and answer.id == option_id
    chosen = next(option for option in question.options if option.id == option_id)
    return CheckResult(
        correct=correct,
        correct_option_id=answer.id if answer else "",
        why_not="" if correct else chosen.why_not,
        explanation=question.explanation,
    )


def answer(
    db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID, question_id: str, option_id: str
) -> CheckResult:
    """Check one answer and record it, if it is the first for that question."""
    attempt = _locked_attempt(db, user_id, attempt_id)
    published_lesson(db, attempt.lesson_id)
    if attempt.finished_at is not None:
        raise attempt_finished()
    question = next((q for q in _questions(attempt.version) if q.id == question_id), None)
    if question is None:
        raise question_not_found()
    if not any(option.id == option_id for option in question.options):
        raise option_not_found()

    earlier = db.get(AttemptAnswer, (attempt.id, question_id))
    if earlier is not None:
        db.commit()  # release the lock
        return _result(question, earlier.option_id)

    result = _result(question, option_id)
    db.add(
        AttemptAnswer(
            attempt_id=attempt.id,
            question_id=question_id,
            option_id=option_id,
            correct=result.correct,
            scored=lesson_doc.is_scored(question),
        )
    )
    db.commit()
    return result


def _share(score: Score) -> Fraction:
    # Nothing to score is nothing to get wrong.
    return Fraction(score.correct, score.scored) if score.scored else Fraction(1)


def _topic_now_complete(db: Session, user_id: uuid.UUID, lesson: Lesson) -> bool:
    """Whether this user has completed every published lesson in the lesson's topic, by the
    same rules as the topic's circle (app/progress.py)."""
    not_completed = db.scalar(
        select(func.count(Lesson.id))
        .outerjoin(
            LessonCompletion,
            and_(LessonCompletion.lesson_id == Lesson.id, LessonCompletion.user_id == user_id),
        )
        .where(
            Lesson.topic_id == lesson.topic_id,
            Lesson.status == LessonStatus.PUBLISHED,
            LessonCompletion.id.is_(None),
        )
    )
    return not_completed == 0


def finish(db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID) -> AttemptResult:
    """Finish an attempt: complete the lesson and keep the best score."""
    attempt = _locked_attempt(db, user_id, attempt_id)
    completion_query = (
        select(LessonCompletion)
        .where(LessonCompletion.user_id == user_id, LessonCompletion.lesson_id == attempt.lesson_id)
        .with_for_update()
    )

    if attempt.finished_at is not None:
        # Already recorded (a repeated request): report it again, changing nothing.
        completion = db.scalar(completion_query)
        db.commit()
        score = Score(attempt.correct or 0, attempt.scored or 0)
        return AttemptResult(
            attempt_id=attempt.id,
            lesson_id=attempt.lesson_id,
            score=score,
            best=Score(completion.best_correct, completion.best_scored) if completion else score,
            first_completion=False,
        )

    lesson = published_lesson(db, attempt.lesson_id)
    answers = {a.question_id: a for a in attempt.answers}
    missing = [q.id for q in _questions(attempt.version) if q.id not in answers]
    if missing:
        raise questions_unanswered([q for q in missing if q is not None])

    scored = [a for a in answers.values() if a.scored]
    score = Score(sum(1 for a in scored if a.correct), len(scored))
    attempt.correct, attempt.scored = score.correct, score.scored
    attempt.finished_at = datetime.now(UTC)

    # Insert the completion if there is none yet; two attempts finishing at once both get
    # here, and the unique constraint lets only one row in.
    inserted = db.execute(
        insert(LessonCompletion)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            lesson_id=attempt.lesson_id,
            best_correct=score.correct,
            best_scored=score.scored,
            best_attempt_id=attempt.id,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "lesson_id"])
        .returning(LessonCompletion.id)
    ).scalar()
    completion = db.scalar(completion_query.execution_options(populate_existing=True))
    assert completion is not None
    if inserted is None:
        best = Score(completion.best_correct, completion.best_scored)
        # A tie keeps the most recent attempt.
        if _share(score) >= _share(best):
            completion.best_correct, completion.best_scored = score.correct, score.scored
            completion.best_attempt_id = attempt.id
        completion.updated_at = datetime.now(UTC)
    first_completion = inserted is not None
    topic_completed = first_completion and _topic_now_complete(db, user_id, lesson)
    db.commit()
    return AttemptResult(
        attempt_id=attempt.id,
        lesson_id=attempt.lesson_id,
        score=score,
        best=Score(completion.best_correct, completion.best_scored),
        first_completion=first_completion,
        topic_completed=topic_completed,
    )
