"""Reviewing the questions a learner answered wrongly (SCRUM-44). Moved from the monolith's
app/review.py onto the read models.

A question is a mistake to review while the learner's latest answer to it was wrong:

- every answer counts, in finished or unfinished attempts, but only the latest one for each
  question. Getting it right on a retake takes it off the list; getting it wrong again
  keeps it there, dated afresh.
- it is shown as the lesson reads now: the latest published version, with its right answer
  and explanation. A question since removed from the lesson, or turned into a one-option
  tap, is no longer a mistake, and nor is one whose right answer is now the option chosen.
- only lessons learners can open count (app/catalog.py), so every mistake can lead back to
  its lesson (AC3).

Mistakes are always the caller's own. They are listed newest first.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import catalog, deck
from app.catalog import visible_to_users
from app.models import AttemptAnswer, LearnableLesson, LearnableTopic, LessonAttempt, LessonDeck


@dataclass(frozen=True)
class Mistake:
    lesson_id: uuid.UUID
    lesson_title: str
    topic_name: str
    question_id: str
    # The card's Markdown, with its {{blank}} if it has one.
    text: str
    chosen: str
    correct: str
    explanation: str
    # Why the chosen option isn't the norm, when the lesson says.
    why_not: str
    answered_at: datetime


def mistakes_for(db: Session, user_id: uuid.UUID) -> list[Mistake]:
    """The questions whose latest answer from this user was wrong, newest first."""
    latest_answers = db.execute(
        select(AttemptAnswer, LessonAttempt.lesson_id, LessonAttempt.version_id)
        .join(LessonAttempt, AttemptAnswer.attempt_id == LessonAttempt.id)
        .where(LessonAttempt.user_id == user_id)
        .distinct(LessonAttempt.lesson_id, AttemptAnswer.question_id)
        .order_by(
            LessonAttempt.lesson_id, AttemptAnswer.question_id, AttemptAnswer.answered_at.desc()
        )
    ).all()
    wrong = [row for row in latest_answers if not row[0].correct and row[0].scored]
    if not wrong:
        return []

    open_lessons = {
        lesson.id: (lesson, topic_name)
        for lesson, topic_name in db.execute(
            visible_to_users(
                select(LearnableLesson, LearnableTopic.name)
                .join(LearnableTopic, LearnableLesson.topic_id == LearnableTopic.id)
                .where(
                    LearnableLesson.id.in_({lesson_id for _, lesson_id, _ in wrong}),
                    catalog.lesson_visible(),
                )
            )
        ).all()
    }

    decks: dict[uuid.UUID, tuple[str, deck.Deck] | None] = {}
    mistakes = []
    for answer, lesson_id, answered_version_id in wrong:
        if lesson_id not in open_lessons:
            continue
        if lesson_id not in decks:
            version = catalog.latest_deck(db, open_lessons[lesson_id][0])
            decks[lesson_id] = (version.title, deck.of(version)) if version else None
        current = decks[lesson_id]
        if current is None:
            continue
        title, the_deck = current
        card = next(
            (c for c in the_deck.doc.cards if c.question and c.question.id == answer.question_id),
            None,
        )
        if card is None or card.question is None or not the_deck.is_scored(card.question):
            continue
        right = the_deck.correct_option(card.question)
        if right is None or right.id == answer.option_id:
            continue
        chosen = next((o for o in card.question.options if o.id == answer.option_id), None)
        if chosen is not None:
            chosen_text, why_not = chosen.text, chosen.why_not
        else:
            # The option has since been removed: say what it was, from the version answered.
            chosen_text, why_not = _option_text(db, answered_version_id, answer), ""
        mistakes.append(
            Mistake(
                lesson_id=lesson_id,
                lesson_title=title,
                topic_name=open_lessons[lesson_id][1],
                question_id=answer.question_id,
                text=card.text,
                chosen=chosen_text,
                correct=right.text,
                explanation=card.question.explanation,
                why_not=why_not,
                answered_at=answer.answered_at,
            )
        )
    mistakes.sort(key=lambda mistake: mistake.answered_at, reverse=True)
    return mistakes


def _option_text(db: Session, version_id: uuid.UUID, answer: AttemptAnswer) -> str:
    version = db.get(LessonDeck, version_id)
    if version is None:
        return ""
    for card in deck.of(version).doc.cards:
        if card.question and card.question.id == answer.question_id:
            for option in card.question.options:
                if option.id == answer.option_id:
                    return option.text
    return ""
