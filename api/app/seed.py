"""Development seed data (SCRUM-72, SCRUM-77). Safe to run more than once.

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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import content_import, lesson_doc
from app.auth import normalise_email
from app.config import get_settings
from app.lessons import latest_version
from app.models import (
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

    log.extend(_seed_completions(db, user))

    db.commit()
    return log
