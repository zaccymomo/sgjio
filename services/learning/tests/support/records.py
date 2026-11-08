"""Writing Learning's own rows directly, as the monolith's tests did: completions, a
completed aptitude quiz and its exemptions. (Read models are never written this way.)"""

from app.models import AptitudeAttempt, LessonCompletion, TopicExemption


def complete(db, user, lesson, correct: int = 1, scored: int = 1) -> LessonCompletion:
    completion = LessonCompletion(
        user_id=user.id, lesson_id=lesson.id, best_correct=correct, best_scored=scored
    )
    db.add(completion)
    db.commit()
    return completion


def quiz(db, user, exemptions: dict | None = None, results: list | None = None):
    """A completed quiz and its exemptions ({topic: level}), saved together (SCRUM-113)."""
    attempt = AptitudeAttempt(
        user_id=user.id, results=results if results is not None else [{"correct": True}]
    )
    db.add(attempt)
    db.flush()
    for topic, level in (exemptions or {}).items():
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
    db.commit()
    return attempt
