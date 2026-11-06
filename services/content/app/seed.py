"""Content's development seed data (SCRUM-72, SCRUM-77, Epic 6). Safe to run more than once.

The content part of the monolith's seed (users, profiles, completions and quiz results now
belong to Identity's and Learning's seeds; scripts/seed-all.sh runs them in order):
- the six topics from the Figma home screen, each with a description (SCRUM-86)
- the lessons in content/lessons, published (see content/README.md). Loading them again
  only updates lessons whose files changed.
- the aptitude question bank from content/aptitude_questions.yaml

Topics and lessons get a position only when they are created, appended after anything
already there, so a fresh database gets the Figma order and re-seeding never undoes an
order an administrator has set (SCRUM-66). Likewise a description is only filled in while
a topic has none, so re-seeding never undoes an administrator's edit.

Other services find this data by its natural keys (contracts/README.md, "Seed and demo
ids"): topics by name, lessons by `key`, questions by `seed_key`, all carried in the events.
Ids stay random on purpose. Event versions restart at 1 in a fresh database, so a
deterministic id seeded again after a Content-only reset (or a deleted seed topic seeded
again) would reach Learning at a version it already has, and be ignored.

Every change is announced like the same change in the admin portal (app/events.py).
"""

import yaml
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import content_import, events
from app.aptitude import NOT_SURE_OPTION, mark_assessed
from app.config import get_settings
from app.models import AptitudeQuestion, Topic
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


def _seed_topics(db: Session) -> list[str]:
    log: list[str] = []
    next_position = next_topic_position(db)
    for name, description in TOPICS.items():
        topic = db.scalar(
            select(Topic).where(func.lower(Topic.name) == name.lower()).with_for_update()
        )
        if topic is None:
            topic = Topic(name=name, description=description, position=next_position)
            next_position += 1
            db.add(topic)
            events.topic_changed(db, topic, bump=False)
            log.append(f"topic {name}")
        elif topic.description == "":
            topic.description = description
            events.topic_changed(db, topic)
            log.append(f"description for topic {topic.name}")
    db.commit()
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
        if any(option.id == NOT_SURE_OPTION["id"] for option in item.options):
            raise RuntimeError(
                f"Aptitude question {item.key} uses the reserved option id {NOT_SURE_OPTION['id']}"
            )
        if item.topic not in topics:
            raise RuntimeError(f"Aptitude question {item.key} has unknown topic {item.topic}")
        options = [{"id": option.id, "text": option.text} for option in item.options]
        question = db.scalar(
            select(AptitudeQuestion).where(AptitudeQuestion.seed_key == item.key).with_for_update()
        )
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
            mark_assessed(db, question.topic_id)
            events.question_changed(db, question, bump=False)
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
            mark_assessed(db, question.topic_id)
            events.question_changed(db, question)
            log.append(f"updated aptitude question {item.key}")
    if log:
        events.bank_changed(db)
    db.commit()
    return log


def seed(db: Session) -> list[str]:
    """Insert anything missing and return a short log of what was created."""
    log = _seed_topics(db)

    # Lessons come from the files in content/ (SCRUM-77), published as they load.
    for result in content_import.import_folder(db, get_settings().content_dir, publish=True):
        if result.action == "failed":
            raise RuntimeError(f"Could not load {result.path}: {'; '.join(result.problems)}")
        if result.action != "unchanged" or result.published:
            log.append(result.describe().strip())
        # E.g. a published lesson keeping its level although its file now says another.
        log.extend(f"{result.key}: {problem}" for problem in result.problems)

    log.extend(_seed_aptitude_questions(db))
    db.commit()
    return log
