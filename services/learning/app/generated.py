"""AI-generated lessons for learners (docs/ai-lessons-plan.md, docs/ai-lessons-api.md).

A learner asks for a lesson on the Practice tab; Learning saves a `generated_lessons` row and,
in the same transaction, writes `learning.lesson_generation.requested` to its outbox. The
Generation service answers with `generation.lesson.progress`, then `generation.lesson
.generated` or `generation.lesson.failed`, which app/consumers.py hands to the functions at the
end of this module. Routes are in app/routers/generated.py.

- **Private and separate.** Everything lives in its own tables; nothing here touches
  lesson attempts, completions, progress, tiers, search or review (D6). Practising a mistake
  in a generated lesson does not clear it (D8).
- **Who asked never leaves Learning.** The event carries a request id, a brief and lesson
  text only: no user id, name or email (D13).
- **Daily limit** (D14): `generation_daily_limit` requests per Singapore date, not counting
  failed or cancelled ones.
- **Timeout** (D15): a request still waiting `generation_timeout_seconds` after it was made
  is marked failed (timeout) whenever it is read, by a request or by the consumer. No
  scheduler.
- **Cancel** (D16) is local: the row is marked cancelled and a later result is ignored.
- **Playing** mirrors app/learning.py: an attempt per run, the first answer to each question
  counts, checked here on the server; finishing needs every question answered and keeps the
  best score.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import catalog, deck
from app.config import get_settings
from app.erasure import refuse_if_erased
from app.exemptions import exemption_levels
from app.learning import (
    CheckResult,
    LearnerLesson,
    Score,
    TopicRef,
    check_result,
    learner_cards,
    share,
)
from app.models import (
    GENERATION_WAITING,
    MAX_LEVEL,
    MIN_LEVEL,
    GeneratedLesson,
    GeneratedLessonAnswer,
    GeneratedLessonAttempt,
    GeneratedLessonReport,
    LearnableLesson,
    LearnableTopic,
    LessonCompletion,
)
from app.platform.outbox import emit
from app.problems import (
    attempt_finished,
    attempt_not_found,
    card_not_found,
    daily_limit_reached,
    generated_not_found,
    no_mistakes,
    option_not_found,
    question_not_found,
    questions_unanswered,
    topic_not_found,
)
from app.progress import topic_figures, weakest_first
from app.review import Mistake, mistakes_for

# Singapore has had no daylight saving since 1982, so a fixed offset is its date.
SINGAPORE = timezone(timedelta(hours=8), "Asia/Singapore")
REQUESTER = "learning"
# Cards and questions per length (plan 4.4).
LENGTHS = {"short": (4, 1), "usual": (6, 2)}
STEPS = {"easier": -1, "right": 0, "harder": 1}
# What learners are told per failure code (never the model's text).
FAILURE_MESSAGES = {
    "off_topic": (
        "We couldn't create a lesson from that request. Lessons cover everyday life in "
        "Singapore, such as small talk at work or ordering food. Please rephrase it and try "
        "again."
    ),
    "invalid_output": "This lesson did not pass our quality checks, so it was not shown.",
    "unsafe": "This lesson did not pass our quality checks, so it was not shown.",
    "provider": "We couldn't create this lesson right now. Please try again shortly.",
    "timeout": "We couldn't create this lesson right now. Please try again shortly.",
}
# Limits from contracts/events/learning.lesson_generation.requested.schema.json.
MAX_GROUNDING_LESSONS = 20
MAX_CARDS_TEXT = 30
MAX_MISTAKES = 5
MAX_AVOID_TITLES = 50
MAX_FEEDBACK = 5


def _cut(value: str | None, length: int) -> str:
    return (value or "")[:length]


# --- Daily limit and timeout ----------------------------------------------------------------


def _fail(row: GeneratedLesson, code: str) -> None:
    row.status = "failed"
    row.failure_code = code
    row.failed_at = datetime.now(UTC)


def _timed_out(row: GeneratedLesson) -> bool:
    timeout = timedelta(seconds=get_settings().generation_timeout_seconds)
    return row.status in GENERATION_WAITING and row.created_at < datetime.now(UTC) - timeout


def _expire(db: Session, user_id: uuid.UUID) -> None:
    """Mark this user's requests that have waited too long as failed (timeout)."""
    timeout = timedelta(seconds=get_settings().generation_timeout_seconds)
    stale = db.scalars(
        select(GeneratedLesson)
        .where(
            GeneratedLesson.user_id == user_id,
            GeneratedLesson.status.in_(GENERATION_WAITING),
            GeneratedLesson.created_at < datetime.now(UTC) - timeout,
        )
        .with_for_update()
    )
    for row in stale:
        _fail(row, "timeout")
    db.flush()  # the session doesn't autoflush, and the daily count reads these


def left_today(db: Session, user_id: uuid.UUID) -> int:
    """Requests left today (Singapore date). Failed and cancelled ones are refunded."""
    midnight = datetime.now(SINGAPORE).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(
        select(func.count())
        .select_from(GeneratedLesson)
        .where(
            GeneratedLesson.user_id == user_id,
            GeneratedLesson.created_at >= midnight,
            GeneratedLesson.status.not_in(("failed", "cancelled")),
        )
    )
    return max(0, get_settings().generation_daily_limit - used)


# --- Options --------------------------------------------------------------------------------


@dataclass(frozen=True)
class TopicOption:
    id: uuid.UUID
    name: str
    mistakes: int
    level: int


@dataclass(frozen=True)
class Options:
    daily_limit: int
    left_today: int
    has_generated: bool
    mistakes_total: int
    pick_for_me: dict
    topics: list[TopicOption]


@dataclass(frozen=True)
class _Choices:
    topics: list[TopicOption]
    mistakes: dict[uuid.UUID, list[Mistake]]  # by topic, newest first
    pick_for_me: dict[str, uuid.UUID | None]


def _levels(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """The aptitude test's exemption level per topic if at least 1, else the highest level
    of a lesson completed there (callers default to 1)."""
    completed = dict(
        db.execute(
            select(LearnableLesson.topic_id, func.max(LearnableLesson.level))
            .join(LessonCompletion, LessonCompletion.lesson_id == LearnableLesson.id)
            .where(LessonCompletion.user_id == user_id)
            .group_by(LearnableLesson.topic_id)
        ).all()
    )
    quiz = {topic: level for topic, level in exemption_levels(db, user_id).items() if level >= 1}
    return completed | quiz


def _mistakes_by_topic(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, list[Mistake]]:
    """mistakes_for(), the Review mistakes list, grouped by topic, newest first."""
    mistakes = mistakes_for(db, user_id)
    if not mistakes:
        return {}
    topic_of = dict(
        db.execute(
            select(LearnableLesson.id, LearnableLesson.topic_id).where(
                LearnableLesson.id.in_({m.lesson_id for m in mistakes})
            )
        ).all()
    )
    by_topic: dict[uuid.UUID, list[Mistake]] = {}
    for mistake in mistakes:
        by_topic.setdefault(topic_of[mistake.lesson_id], []).append(mistake)
    return by_topic


def _choices(db: Session, user_id: uuid.UUID) -> _Choices:
    rows = topic_figures(db, user_id)
    by_topic = _mistakes_by_topic(db, user_id)
    levels = _levels(db, user_id)
    topics = [
        TopicOption(row.id, row.name, len(by_topic.get(row.id, [])), levels.get(row.id, 1))
        for row in rows
    ]
    with_mistakes = [t for t in topics if t.mistakes]
    most_mistakes = max(
        with_mistakes,
        # Ties: the topic with the most recent mistake.
        key=lambda t: (t.mistakes, by_topic[t.id][0].answered_at),
        default=None,
    )
    weakest = weakest_first(rows)
    return _Choices(
        topics=topics,
        mistakes=by_topic,
        pick_for_me={
            "new": weakest[0].id if weakest else None,
            "mistakes": most_mistakes.id if most_mistakes else None,
        },
    )


def options(db: Session, user_id: uuid.UUID) -> Options:
    _expire(db, user_id)
    choices = _choices(db, user_id)
    has_generated = db.scalar(
        select(select(GeneratedLesson.id).where(GeneratedLesson.user_id == user_id).exists())
    )
    result = Options(
        daily_limit=get_settings().generation_daily_limit,
        left_today=left_today(db, user_id),
        has_generated=bool(has_generated),
        mistakes_total=sum(len(m) for m in choices.mistakes.values()),
        pick_for_me=choices.pick_for_me,
        topics=choices.topics,
    )
    db.commit()
    return result


# --- Requesting -----------------------------------------------------------------------------


def _grounding_lessons(db: Session, topic_id: uuid.UUID, level: int) -> list[dict]:
    """The topic's lessons learners can open, latest versions, nearest the level first."""
    lessons = db.scalars(
        select(LearnableLesson)
        .where(LearnableLesson.topic_id == topic_id, catalog.lesson_visible())
        .order_by(
            func.abs(LearnableLesson.level - level),
            LearnableLesson.level,
            LearnableLesson.position,
            LearnableLesson.created_at,
        )
        .limit(MAX_GROUNDING_LESSONS)
    )
    grounding = []
    for lesson in lessons:
        version = catalog.latest_deck(db, lesson)
        if version is None:
            continue
        grounding.append(
            {
                "title": _cut(version.title, 200),
                "summary": _cut(version.summary, 160),
                "level": lesson.level,
                "cards_text": [
                    _cut(card, 1500) for card in version.cards_plain_text[:MAX_CARDS_TEXT]
                ],
            }
        )
    return grounding


def _avoid_titles(db: Session, user_id: uuid.UUID, topic_id: uuid.UUID) -> list[str]:
    titles = db.scalars(
        select(GeneratedLesson.title)
        .where(
            GeneratedLesson.user_id == user_id,
            GeneratedLesson.topic_id == topic_id,
            GeneratedLesson.title.is_not(None),
        )
        .order_by(GeneratedLesson.created_at.desc())
        .limit(MAX_AVOID_TITLES)
    )
    return [_cut(title, 200) for title in titles]


def _feedback(db: Session, user_id: uuid.UUID) -> list[dict]:
    rated = db.scalars(
        select(GeneratedLesson)
        .where(
            GeneratedLesson.user_id == user_id,
            GeneratedLesson.rated_at.is_not(None),
            GeneratedLesson.title.is_not(None),
        )
        .order_by(GeneratedLesson.rated_at.desc())
        .limit(MAX_FEEDBACK)
    )
    return [
        {
            "title": _cut(row.title, 200),
            "useful": bool(row.rating_useful),
            "reasons": list(row.rating_reasons or [])[:4],
        }
        for row in rated
    ]


def request(
    db: Session,
    user_id: uuid.UUID,
    *,
    topic_id: uuid.UUID | None,
    focus: str,
    ask: str | None,
    difficulty: str,
    length: str,
) -> GeneratedLesson:
    """Save a request and write learning.lesson_generation.requested in one transaction."""
    refuse_if_erased(db, user_id)
    # One request at a time per learner, so two at once can't both pass the daily limit.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"gen:{user_id}"})
    _expire(db, user_id)
    if left_today(db, user_id) == 0:
        db.commit()  # keep any timeouts just marked
        raise daily_limit_reached(get_settings().generation_daily_limit)

    choices = _choices(db, user_id)
    if topic_id is None:
        topic_id = choices.pick_for_me[focus]
        if topic_id is None:
            raise no_mistakes() if focus == "mistakes" else topic_not_found()
    option = next((t for t in choices.topics if t.id == topic_id), None)
    if option is None:
        raise topic_not_found()
    mistakes = choices.mistakes.get(topic_id, [])[:MAX_MISTAKES] if focus == "mistakes" else []
    if focus == "mistakes" and not mistakes:
        raise no_mistakes()

    topic = db.get(LearnableTopic, topic_id)
    assert topic is not None  # it has a lesson learners can open
    level = min(MAX_LEVEL, max(MIN_LEVEL, option.level + STEPS[difficulty]))
    cards, questions = LENGTHS[length]
    brief = {
        "audience": "learner",
        "focus": focus,
        "topic": {
            "id": str(topic.id),
            "name": _cut(topic.name, 120),
            "description": _cut(topic.description, 500),
        },
        "level": level,
        "cards": cards,
        "questions": questions,
        "ask": _cut(ask, 200) if ask else None,
        "notes": None,
        "check_answers": True,
    }
    grounding = {
        "lessons": _grounding_lessons(db, topic.id, level),
        "mistakes": [
            {
                "lesson_title": _cut(m.lesson_title, 200),
                "card_text": _cut(m.text, 1500),
                "chosen": _cut(m.chosen, 160),
                "correct": _cut(m.correct, 160),
                "explanation": _cut(m.explanation, 1500),
                "why_not": _cut(m.why_not, 400),
            }
            for m in mistakes
        ],
        "avoid_titles": _avoid_titles(db, user_id, topic.id),
        "feedback": _feedback(db, user_id),
    }
    row = GeneratedLesson(
        id=uuid.uuid4(),
        user_id=user_id,
        topic_id=topic.id,
        status="requested",
        version=0,
        focus=focus,
        difficulty=difficulty,
        length=length,
        level=level,
        ask=brief["ask"],
        brief=brief,
        covers=[
            {"lesson_id": str(m.lesson_id), "lesson_title": m.lesson_title, "correct": m.correct}
            for m in mistakes
        ],
    )
    db.add(row)
    db.flush()
    emit(
        db,
        type="learning.lesson_generation.requested",
        aggregate_type="lesson_generation",
        aggregate_id=row.id,
        aggregate_version=1,
        data={"request_id": row.id, "brief": brief, "grounding": grounding},
    )
    db.commit()
    return row


# --- Reading a request ----------------------------------------------------------------------


def _own(db: Session, user_id: uuid.UUID, generated_id: uuid.UUID, lock=False) -> GeneratedLesson:
    """The user's own request; anyone else's is answered as missing."""
    query = select(GeneratedLesson).where(
        GeneratedLesson.id == generated_id, GeneratedLesson.user_id == user_id
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise generated_not_found()
    return row


def topic_of(row: GeneratedLesson) -> dict:
    return {"id": row.topic_id, "name": row.brief["topic"]["name"]}


def best_of(row: GeneratedLesson) -> Score | None:
    if row.best_scored is None:
        return None
    return Score(row.best_correct or 0, row.best_scored)


def status_out(db: Session, row: GeneratedLesson) -> dict:
    """GeneratedStatus (docs/ai-lessons-api.md)."""
    lesson = None
    if row.status == "ready":
        lesson = {
            "title": row.title,
            "summary": row.summary or "",
            "learning_points": row.learning_points or [],
            "cards": len((row.doc or {}).get("cards", [])),
            "questions": len(row.questions or []),
            "reading_seconds": row.reading_seconds or 0,
        }
    failure = None
    if row.status == "failed":
        code = row.failure_code or "provider"
        failure = {"code": code, "message": FAILURE_MESSAGES[code]}
    return {
        "id": row.id,
        "status": row.status,
        "topic": topic_of(row),
        "focus": row.focus,
        "difficulty": row.difficulty,
        "length": row.length,
        "level": row.level,
        "ask": row.ask,
        "covers": row.covers,
        "lesson": lesson,
        "failure": failure,
        "created_at": row.created_at,
        "left_today": left_today(db, row.user_id),
    }


def status(db: Session, user_id: uuid.UUID, generated_id: uuid.UUID) -> dict:
    _expire(db, user_id)
    row = _own(db, user_id, generated_id)
    result = status_out(db, row)
    db.commit()
    return result


def cancel(db: Session, user_id: uuid.UUID, generated_id: uuid.UUID) -> dict:
    """Cancel a waiting request (refunded); a finished one is returned unchanged."""
    _expire(db, user_id)
    row = _own(db, user_id, generated_id, lock=True)
    if row.status in GENERATION_WAITING:
        row.status = "cancelled"
    db.flush()
    result = status_out(db, row)
    db.commit()
    return result


def listed(db: Session, user_id: uuid.UUID) -> list[dict]:
    """The user's requests, newest first, without failed or cancelled ones."""
    _expire(db, user_id)
    rows = db.scalars(
        select(GeneratedLesson)
        .where(
            GeneratedLesson.user_id == user_id,
            GeneratedLesson.status.not_in(("failed", "cancelled")),
        )
        .order_by(GeneratedLesson.created_at.desc())
    ).all()
    result = [
        {
            "id": row.id,
            "status": row.status,
            "title": row.title,
            "topic": topic_of(row),
            "created_at": row.created_at,
            "best": best_of(row),
        }
        for row in rows
    ]
    db.commit()
    return result


# --- Playing --------------------------------------------------------------------------------


def _ready(db: Session, user_id: uuid.UUID, generated_id: uuid.UUID) -> GeneratedLesson:
    row = _own(db, user_id, generated_id)
    if row.status != "ready":
        raise generated_not_found()
    return row


def _deck(row: GeneratedLesson) -> deck.Deck:
    return deck.read(row.doc or {"cards": []}, row.questions or [])


def learner_lesson(db: Session, user_id: uuid.UUID, generated_id: uuid.UUID) -> LearnerLesson:
    """The lesson as LearnerLessonOut, without right answers, so LessonDeck plays it as is."""
    row = _ready(db, user_id, generated_id)
    topic = topic_of(row)
    return LearnerLesson(
        id=row.id,
        version=1,
        title=row.title or "",
        summary=row.summary or "",
        topic=TopicRef(topic["id"], topic["name"]),
        reading_seconds=row.reading_seconds or 0,
        cards=learner_cards(_deck(row)),
        assets={},
    )


def start_attempt(
    db: Session, user_id: uuid.UUID, generated_id: uuid.UUID
) -> GeneratedLessonAttempt:
    row = _ready(db, user_id, generated_id)
    refuse_if_erased(db, user_id)
    attempt = GeneratedLessonAttempt(generated_lesson_id=row.id)
    db.add(attempt)
    db.commit()
    return attempt


def _locked_attempt(
    db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> tuple[GeneratedLessonAttempt, GeneratedLesson]:
    found = db.execute(
        select(GeneratedLessonAttempt, GeneratedLesson)
        .join(GeneratedLesson, GeneratedLesson.id == GeneratedLessonAttempt.generated_lesson_id)
        .where(GeneratedLessonAttempt.id == attempt_id, GeneratedLesson.user_id == user_id)
        .with_for_update(of=GeneratedLessonAttempt)
    ).first()
    if found is None:
        raise attempt_not_found()
    return found[0], found[1]


def answer(
    db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID, question_id: str, option_id: str
) -> CheckResult:
    """Check one answer and record it, if it is the first for that question."""
    attempt, row = _locked_attempt(db, user_id, attempt_id)
    if attempt.finished_at is not None:
        raise attempt_finished()
    the_deck = _deck(row)
    question = next((q for q in the_deck.questions if q.id == question_id), None)
    if question is None:
        raise question_not_found()
    if not any(option.id == option_id for option in question.options):
        raise option_not_found()

    earlier = db.get(GeneratedLessonAnswer, (attempt.id, question_id))
    if earlier is not None:
        db.commit()  # release the lock
        return check_result(the_deck, question, earlier.option_id)

    result = check_result(the_deck, question, option_id)
    db.add(
        GeneratedLessonAnswer(
            attempt_id=attempt.id,
            question_id=question_id,
            option_id=option_id,
            correct=result.correct,
            scored=the_deck.is_scored(question),
        )
    )
    db.commit()
    return result


@dataclass(frozen=True)
class GeneratedAttemptResult:
    attempt_id: uuid.UUID
    score: Score
    best: Score


def finish(db: Session, user_id: uuid.UUID, attempt_id: uuid.UUID) -> GeneratedAttemptResult:
    """Finish an attempt and keep the best score. Finishing again changes nothing."""
    attempt, row = _locked_attempt(db, user_id, attempt_id)
    db.refresh(row, with_for_update=True)
    if attempt.finished_at is not None:
        score = Score(attempt.correct or 0, attempt.scored or 0)
        best = best_of(row) or score
        db.commit()
        return GeneratedAttemptResult(attempt.id, score, best)

    answers = {a.question_id: a for a in attempt.answers}
    missing = [q.id for q in _deck(row).questions if q.id not in answers]
    if missing:
        raise questions_unanswered(missing)

    scored = [a for a in answers.values() if a.scored]
    score = Score(sum(1 for a in scored if a.correct), len(scored))
    attempt.correct, attempt.scored = score.correct, score.scored
    attempt.finished_at = datetime.now(UTC)
    best = best_of(row)
    # A tie keeps the most recent attempt, as for lessons.
    if best is None or share(score) >= share(best):
        row.best_correct, row.best_scored = score.correct, score.scored
    db.commit()
    return GeneratedAttemptResult(attempt.id, score, best_of(row) or score)


def rate(
    db: Session, user_id: uuid.UUID, generated_id: uuid.UUID, useful: bool, reasons: list[str]
) -> None:
    """Save the rating, replacing any earlier one."""
    row = _ready(db, user_id, generated_id)
    row.rating_useful = useful
    row.rating_reasons = list(dict.fromkeys(reasons))
    row.rated_at = datetime.now(UTC)
    db.commit()


def report(
    db: Session, user_id: uuid.UUID, generated_id: uuid.UUID, card_id: str, reason: str, note: str
) -> GeneratedLessonReport:
    row = _ready(db, user_id, generated_id)
    if not any(card.id == card_id for card in _deck(row).doc.cards):
        raise card_not_found()
    flag = GeneratedLessonReport(
        generated_lesson_id=row.id, card_id=card_id, reason=reason, note=note
    )
    db.add(flag)
    db.commit()
    return flag


# --- Generation's answers (called by app/consumers.py, inside its transaction) ---------------


def _waiting(session: Session, envelope: dict) -> GeneratedLesson | None:
    """The request this event is for, locked, if Learning asked for it, it is still waiting
    and the event is newer than what it holds. Anything else is ignored, so duplicates and
    events out of order change nothing."""
    data = envelope["data"]
    if data.get("requester") != REQUESTER:
        return None
    row = session.scalar(
        select(GeneratedLesson)
        .where(GeneratedLesson.id == uuid.UUID(str(data["request_id"])))
        .with_for_update()
    )
    if row is None:
        return None
    if _timed_out(row):
        _fail(row, "timeout")
        return None
    if row.status not in GENERATION_WAITING or envelope["aggregate_version"] <= row.version:
        return None
    row.version = envelope["aggregate_version"]
    return row


def on_progress(session: Session, envelope: dict) -> None:
    row = _waiting(session, envelope)
    if row is not None:
        row.status = envelope["data"]["stage"]


def on_generated(session: Session, envelope: dict) -> None:
    row = _waiting(session, envelope)
    if row is None:
        return
    data = envelope["data"]
    row.status = "ready"
    row.title = data["title"]
    row.summary = data.get("summary") or ""
    row.learning_points = data.get("learning_points") or []
    row.doc = data["doc"]
    row.questions = data.get("questions") or []
    row.reading_seconds = data.get("reading_seconds") or 0
    row.ready_at = datetime.now(UTC)


def on_failed(session: Session, envelope: dict) -> None:
    row = _waiting(session, envelope)
    if row is not None:
        _fail(row, envelope["data"]["code"])
