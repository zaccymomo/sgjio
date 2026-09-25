"""Development seed data (SCRUM-72). Safe to run more than once.

Creates:
- one administrator (administrators are not created through registration, SCRUM-68)
- one ordinary Newcomer account, so the main app can be signed in to before SCRUM-61
- the six topics from the Figma home screen
- one published sample lesson with a quiz, so the lesson and quiz tables have real data
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import normalise_email
from app.config import get_settings
from app.models import (
    Lesson,
    LessonStatus,
    Profile,
    QuizOption,
    QuizQuestion,
    Topic,
    User,
    UserRole,
    UserType,
)
from app.security import hash_password

TOPICS = [
    "Singlish",
    "Hawker & Food",
    "Workplace",
    "Public Etiquette",
    "Festivals",
    "Getting Around",
]

SAMPLE_LESSON = {
    "topic": "Hawker & Food",
    "title": "Ordering at a Local Hawker Centre",
    "content": (
        "## Chope first, then order\n\n"
        'At busy hawker centres, people reserve ("chope") a seat by leaving a packet of '
        "tissues on the table. Find a free seat before you queue.\n\n"
        "## Kopi lingo\n\n"
        "- **Kopi**: coffee with condensed milk\n"
        "- **Kopi O**: black coffee with sugar\n"
        "- **Kopi C**: coffee with evaporated milk and sugar\n"
        "- **Kosong**: no sugar\n"
        "- **Siew dai**: less sugar\n"
    ),
    "prompt": "You want black coffee with no sugar. What do you ask for?",
    "explanation": (
        '"O" means no milk and "kosong" means no sugar, so black coffee with no sugar '
        "is Kopi O Kosong."
    ),
    "options": [
        ("Kopi C", False),
        ("Kopi O Kosong", True),
        ("Kopi Siew Dai", False),
        ("Kopi", False),
    ],
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

    topics: dict[str, Topic] = {}
    for name in TOPICS:
        topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.lower()))
        if topic is None:
            topic = Topic(name=name)
            db.add(topic)
            log.append(f"topic {name}")
        topics[name] = topic
    db.flush()

    if db.scalar(select(Lesson).where(Lesson.title == SAMPLE_LESSON["title"])) is None:
        lesson = Lesson(
            title=SAMPLE_LESSON["title"],
            content=SAMPLE_LESSON["content"],
            topic=topics[SAMPLE_LESSON["topic"]],
            status=LessonStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        lesson.question = QuizQuestion(
            prompt=SAMPLE_LESSON["prompt"],
            explanation=SAMPLE_LESSON["explanation"],
            options=[
                QuizOption(text=text, is_correct=correct, position=i)
                for i, (text, correct) in enumerate(SAMPLE_LESSON["options"])
            ],
        )
        db.add(lesson)
        log.append(f'sample lesson "{lesson.title}"')

    db.commit()
    return log
