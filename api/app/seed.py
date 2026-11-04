"""Development seed data (SCRUM-72, SCRUM-77, Epic 6). Safe to run more than once.

Creates:
- one administrator (administrators are not created through registration, SCRUM-68)
- one ordinary Newcomer account, so the main app can be signed in to before SCRUM-61
- the six topics from the Figma home screen, each with a description (SCRUM-86)
- the lessons in content/lessons, published (see content/README.md). Loading them again
  only updates lessons whose files changed.
- some completed lessons for the Newcomer account, so the landing page circles have
  something to show while SCRUM-15 (answering a quiz) is still to be built

Topics and lessons get a position only when they are created, appended after anything
already there, so a fresh database gets the Figma order and re-seeding never undoes an
order an administrator has set (SCRUM-66). Likewise a description is only filled in while
a topic has none, so re-seeding never undoes an administrator's edit.
"""

from datetime import UTC, datetime

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import content_import, lesson_doc
from app.aptitude import latest_attempt
from app.auth import normalise_email
from app.config import get_settings
from app.lessons import latest_version
from app.models import (
    AptitudeAttempt,
    AptitudeQuestion,
    Lesson,
    LessonCompletion,
    LessonStatus,
    Profile,
    Topic,
    User,
    UserRole,
    UserType,
)
from app.security import hash_password
from app.topics import next_topic_position

# Name and description, in the Figma home screen's order, which is the order a fresh
# database starts in. Each description sums up the topic's lessons in content/lessons.
TOPICS = {
    "Singlish": (
        "The little words and sentence endings you will hear every day, and why "
        "Singaporeans often say more with fewer words."
    ),
    "Hawker & Food": (
        "How to order kopi, share a table and clear up after yourself at a hawker centre."
    ),
    "Workplace": (
        "How colleagues address each other, say no politely, chat over lunch and follow up on work."
    ),
    "Public Etiquette": (
        "The unwritten rules of queues, trains, buses, escalators and living close to your "
        "neighbours."
    ),
    "Festivals": (
        "What Chinese New Year, Hari Raya Puasa and Deepavali mean, and how to be a good "
        "guest when you visit someone's home."
    ),
    "Getting Around": (
        "Paying your fare, catching a bus, getting a taxi or ride, and when to give up your seat."
    ),
}


class SeedOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=300)
    correct: bool = False


class SeedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=120)
    topic: str
    level: int = Field(ge=1, le=5)
    prompt: str = Field(min_length=1)
    options: list[SeedOption] = Field(min_length=2)


class SeedQuestionFile(BaseModel):
    questions: list[SeedQuestion]


TEST_USERS = {
    "level1@sgjio.example.com": ("Level One Newcomer", 1),
    "level3@sgjio.example.com": ("Level Three Newcomer", 3),
    "level5@sgjio.example.com": ("Level Five Newcomer", 5),
    "skipped@sgjio.example.com": ("Skipped Quiz Newcomer", None),
}


# How many of each topic's lessons the demo Newcomer has finished, so the landing page
# shows every state a circle can be in: not started, in progress and complete
# (SCRUM-43 AC3, AC4, AC5). Only applied when the account has no progress at all.
SEEDED_COMPLETIONS = {
    "Singlish": 2,
    "Hawker & Food": 0,
    "Workplace": 1,
    "Public Etiquette": 3,
    "Festivals": 1,
    "Getting Around": 2,
}


def _get_or_create_user(
    db: Session,
    email: str,
    password: str,
    name: str,
    role: UserRole,
    user_type: UserType | None,
) -> tuple[User, bool]:
    email = normalise_email(email)
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role=role,
        user_type=user_type,
    )
    db.add(user)
    return user, True


def _scored_questions(db: Session, lesson: Lesson) -> int:
    version = latest_version(db, lesson.id)
    if version is None:
        return 0
    doc = lesson_doc.LessonDoc.model_validate(version.doc)
    return lesson_doc.stats(doc).scored_questions


def _seed_completions(db: Session, user: User) -> list[str]:
    """Give the demo account some progress, but never overwrite real progress."""
    if db.scalar(
        select(func.count())
        .select_from(LessonCompletion)
        .where(LessonCompletion.user_id == user.id)
    ):
        return []

    log: list[str] = []
    for topic_name, count in SEEDED_COMPLETIONS.items():
        if count == 0:
            continue
        lessons = db.scalars(
            select(Lesson)
            .join(Topic)
            .where(Topic.name == topic_name, Lesson.status == LessonStatus.PUBLISHED)
            .order_by(Lesson.title)
            .limit(count)
        ).all()
        for index, lesson in enumerate(lessons):
            # Alternate full marks and half marks, so the stored scores are not uniformly
            # perfect once tiers (SCRUM-27) start reading them.
            scored = _scored_questions(db, lesson)
            db.add(
                LessonCompletion(
                    user_id=user.id,
                    lesson_id=lesson.id,
                    best_correct=scored if index % 2 == 0 else scored // 2,
                    best_scored=scored,
                )
            )
        if lessons:
            log.append(f"{len(lessons)} completed lesson(s) in {topic_name}")
    return log


def _seed_aptitude_questions(db: Session) -> list[str]:
    path = get_settings().content_dir.parent / "aptitude_questions.yaml"
    data = SeedQuestionFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    topics = {topic.name: topic for topic in db.scalars(select(Topic))}
    log: list[str] = []
    for item in data.questions:
        correct = [option.id for option in item.options if option.correct]
        if len(correct) != 1:
            raise RuntimeError(f"Aptitude question {item.key} must have exactly one correct option")
        if item.topic not in topics:
            raise RuntimeError(f"Aptitude question {item.key} has unknown topic {item.topic}")
        options = [{"id": option.id, "text": option.text} for option in item.options]
        question = db.scalar(select(AptitudeQuestion).where(AptitudeQuestion.seed_key == item.key))
        values = (topics[item.topic].id, item.level, item.prompt, options, correct[0], True)
        if question is None:
            question = AptitudeQuestion(
                seed_key=item.key,
                topic_id=values[0],
                level=values[1],
                prompt=values[2],
                options=values[3],
                correct_option_id=values[4],
                is_active=values[5],
            )
            db.add(question)
            log.append(f"aptitude question {item.key}")
        elif (
            question.topic_id,
            question.level,
            question.prompt,
            question.options,
            question.correct_option_id,
            question.is_active,
        ) != values:
            (
                question.topic_id,
                question.level,
                question.prompt,
                question.options,
                question.correct_option_id,
                question.is_active,
            ) = values
            log.append(f"updated aptitude question {item.key}")
    db.commit()
    return log


def _seed_test_users(db: Session) -> list[str]:
    questions = list(
        db.scalars(
            select(AptitudeQuestion)
            .where(AptitudeQuestion.is_active.is_(True))
            .order_by(AptitudeQuestion.level, AptitudeQuestion.seed_key)
        )
    )
    by_level = {
        level: next(question for question in questions if question.level == level)
        for level in range(1, 6)
    }
    log: list[str] = []
    for email, (name, level) in TEST_USERS.items():
        user, created = _get_or_create_user(
            db, email, "UserPass123", name, UserRole.USER, UserType.NEWCOMER
        )
        if created:
            user.profile = Profile(
                neighbourhood="Tampines", interests=["Food"], languages=["English"]
            )
            user.intro_finished_at = datetime.now(UTC)
            user.level = level
            log.append(f"test user {email}")
        if level is not None and latest_attempt(db, user.id) is None:
            results = []
            for question_level, question in by_level.items():
                # Correct through the level below the awarded level; a Level 5 user
                # masters all five questions.
                correct = question_level < level or level == 5
                option_id = (
                    question.correct_option_id
                    if correct
                    else next(
                        option["id"]
                        for option in question.options
                        if option["id"] != question.correct_option_id
                    )
                )
                results.append(
                    {
                        "question_id": str(question.id),
                        "topic_id": str(question.topic_id),
                        "topic": question.topic.name,
                        "level": question.level,
                        "prompt": question.prompt,
                        "option_id": option_id,
                        "option_text": next(
                            option["text"]
                            for option in question.options
                            if option["id"] == option_id
                        ),
                        "correct": correct,
                    }
                )
            db.add(AptitudeAttempt(user_id=user.id, level=level, results=results))
            log.append(f"aptitude result for {email}")
    db.commit()
    return log


def seed(db: Session) -> list[str]:
    """Insert anything missing and return a short log of what was created."""
    settings = get_settings()
    log: list[str] = []

    admin, created = _get_or_create_user(
        db,
        settings.seed_admin_email,
        settings.seed_admin_password,
        "SGJio Admin",
        UserRole.ADMIN,
        None,
    )
    if created:
        log.append(f"admin account {admin.email}")

    user, created = _get_or_create_user(
        db,
        settings.seed_user_email,
        settings.seed_user_password,
        "Siddharth Sharma",
        UserRole.USER,
        UserType.NEWCOMER,
    )
    if created:
        user.profile = Profile(
            neighbourhood="Tampines",
            interests=["Food", "Football"],
            languages=["English", "Hindi"],
        )
        log.append(f"user account {user.email}")

    next_position = next_topic_position(db)
    for name, description in TOPICS.items():
        topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.lower()))
        if topic is None:
            topic = Topic(name=name, description=description, position=next_position)
            next_position += 1
            db.add(topic)
            log.append(f"topic {name}")
        elif topic.description == "":
            topic.description = description
            log.append(f"description for topic {topic.name}")
    db.commit()

    # Lessons come from the files in content/ (SCRUM-77), published as they load.
    for result in content_import.import_folder(db, get_settings().content_dir, publish=True):
        if result.action == "failed":
            raise RuntimeError(f"Could not load {result.path}: {'; '.join(result.problems)}")
        if result.action != "unchanged" or result.published:
            log.append(result.describe().strip())

    log.extend(_seed_aptitude_questions(db))
    log.extend(_seed_test_users(db))

    log.extend(_seed_completions(db, user))

    db.commit()
    return log
