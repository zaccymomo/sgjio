"""A stand-in for the Content service: it keeps topics, lessons and aptitude questions in
memory and publishes exactly the events Content does (contracts/README.md), in the same
order, with the same versions, through the real consumer.

The monolith's tests changed rows directly (`lesson.status = WITHDRAWN; db.commit()`).
Here the same steps are Content's own actions (`content.withdraw(lesson)`), so every test
also proves Learning's event handling: version guards, insert-if-absent decks, the topic
tombstone and the bank.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tests.support import lesson_doc
from tests.support.events import BANK_ID, EventBus, stamp

ONE_QUESTION = {
    "cards": [
        {
            "id": "c1",
            "text": "Pick {{blank}}.",
            "question": {
                "id": "q1",
                "options": [
                    {"id": "right", "text": "Right", "correct": True},
                    {"id": "wrong", "text": "Wrong"},
                ],
                "explanation": "Because.",
            },
        }
    ]
}
OPTIONS = [{"id": "a", "text": "Chope"}, {"id": "b", "text": "Queue"}]


@dataclass(eq=False)
class Topic:
    id: uuid.UUID
    name: str
    description: str
    position: int
    archived: bool = False
    version: int = 1

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(eq=False)
class Version:
    id: uuid.UUID
    lesson_id: uuid.UUID
    number: int
    title: str
    summary: str
    doc: dict
    published_at: datetime


@dataclass(eq=False)
class Lesson:
    id: uuid.UUID
    topic: Topic
    title: str  # the draft title (display_title)
    level: int
    position: int
    created_at: datetime
    key: str | None = None
    status: str = "draft"
    versions: list[Version] = field(default_factory=list)
    first_published_at: datetime | None = None
    published_at: datetime | None = None
    withdrawn_at: datetime | None = None
    version: int = 0
    # The working copy the next publish takes when no document is given.
    draft: dict = field(default_factory=lambda: ONE_QUESTION)

    @property
    def topic_id(self) -> uuid.UUID:
        return self.topic.id


@dataclass(eq=False)
class Question:
    id: uuid.UUID
    topic: Topic
    level: int
    prompt: str
    options: list[dict]
    correct_option_id: str
    is_active: bool = True
    seed_key: str | None = None
    version: int = 1

    @property
    def topic_id(self) -> uuid.UUID:
        return self.topic.id


def normalise(doc: dict) -> dict:
    """The document as Content stores it: every field present, missing ids filled in. (The
    monolith's tests reused option ids across questions, which Content's editor would not;
    they are kept as written, since ids only need to be unique within a question here.)"""
    parsed = lesson_doc.LessonDoc.model_validate(doc)
    for _, part in lesson_doc._parts_with_ids(parsed):
        if part.id is None:
            part.id = lesson_doc.new_id()
    return lesson_doc.dump(parsed)


def deck_data(version: Version) -> dict:
    """`data` of content.lesson_version.published for a stored version."""
    doc = lesson_doc.LessonDoc.model_validate(version.doc)
    return {
        "version_id": str(version.id),
        "lesson_id": str(version.lesson_id),
        "number": version.number,
        "title": version.title,
        "summary": version.summary,
        "published_at": stamp(version.published_at),
        "doc": version.doc,
        "questions": [
            {
                "card_id": card.id,
                "question_id": card.question.id,
                "scored": lesson_doc.is_scored(card.question),
                "correct_option_id": lesson_doc.correct_option(card.question).id,
            }
            for card in doc.cards
            if card.question is not None
        ],
        "reading_seconds": lesson_doc.stats(doc).reading_seconds,
        "scored_questions": lesson_doc.stats(doc).scored_questions,
        "assets": {},
        "cards_plain_text": [lesson_doc.plain_text(card.text) for card in doc.cards],
    }


class FakeContent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.topics: list[Topic] = []
        self.lessons: list[Lesson] = []
        self.questions: list[Question] = []
        self.bank_revision = 0
        # Lessons are created a millisecond apart, so `created_at` breaks ties as it did.
        self._clock = datetime.now(UTC) - timedelta(days=1)

    def _tick(self) -> datetime:
        self._clock += timedelta(milliseconds=1)
        return self._clock

    # --- Topics ----------------------------------------------------------------------------

    def _topic_changed(self, topic: Topic) -> dict:
        return self.bus.publish(
            "content.topic.changed",
            {
                "topic_id": str(topic.id),
                "name": topic.name,
                "description": topic.description,
                "position": topic.position,
                "is_archived": topic.archived,
            },
            topic.id,
            topic.version,
        )

    def topic(
        self, name: str = "Singlish", position: int = 0, description: str = "", archived=False
    ) -> Topic:
        topic = Topic(uuid.uuid4(), name, description, position, archived)
        self.topics.append(topic)
        self._topic_changed(topic)
        return topic

    def update_topic(self, topic: Topic, **changes) -> None:
        """Rename, describe, reorder, archive or restore, as Content does: the topic, then
        its lessons when archiving changes what learners see, then the bank if the topic is
        assessed."""
        was_archived = topic.archived
        for name, value in changes.items():
            setattr(topic, name, value)
        topic.version += 1
        self._topic_changed(topic)
        if topic.archived != was_archived:
            for lesson in self.lessons:
                if lesson.topic is topic and lesson.versions:
                    self._lesson_changed(lesson)
        if any(question.topic is topic for question in self.questions):
            self.publish_bank()

    def archive(self, topic: Topic) -> None:
        self.update_topic(topic, archived=True)

    def restore_topic(self, topic: Topic) -> None:
        self.update_topic(topic, archived=False)

    def delete_topic(self, topic: Topic, expect=None) -> dict:
        topic.version += 1
        self.topics.remove(topic)
        envelope = self.bus.envelope(
            "content.topic.deleted", {"topic_id": str(topic.id)}, topic.id, topic.version
        )
        self.bus.sent.append(envelope)
        if expect is None:
            self.bus.deliver(envelope)
        else:
            self.bus.deliver(envelope, expect)
        return envelope

    # --- Lessons ---------------------------------------------------------------------------

    def lesson_data(self, lesson: Lesson) -> dict:
        latest = lesson.versions[-1]
        return {
            "lesson_id": str(lesson.id),
            "key": lesson.key,
            "topic_id": str(lesson.topic.id),
            "level": lesson.level,
            "position": lesson.position,
            "created_at": stamp(lesson.created_at),
            "display_title": lesson.title,
            "publication_state": lesson.status,
            "learner_visible": lesson.status == "published" and not lesson.topic.archived,
            "first_published_at": stamp(lesson.first_published_at),
            "published_at": stamp(lesson.published_at) if lesson.published_at else None,
            "withdrawn_at": stamp(lesson.withdrawn_at) if lesson.withdrawn_at else None,
            "latest_version_id": str(latest.id),
            "latest_version_number": latest.number,
        }

    def _lesson_changed(self, lesson: Lesson) -> dict:
        lesson.version += 1
        return self.bus.publish(
            "content.lesson.changed", self.lesson_data(lesson), lesson.id, lesson.version
        )

    def lesson(
        self,
        topic: Topic,
        title: str = "Lesson",
        *,
        level: int = 1,
        position: int = 0,
        doc: dict | None = None,
        summary: str = "",
        status: str = "published",
        key: str | None = None,
        published_at: datetime | None = None,
    ) -> Lesson:
        """A lesson in `topic`. A draft is never sent to Learning; a withdrawn one was
        published first."""
        lesson = Lesson(uuid.uuid4(), topic, title, level, position, self._tick(), key=key)
        lesson.draft = doc or ONE_QUESTION
        self.lessons.append(lesson)
        if status != "draft":
            self.publish(lesson, doc, summary=summary, published_at=published_at)
        if status == "withdrawn":
            self.withdraw(lesson)
        return lesson

    def publish(
        self,
        lesson: Lesson,
        doc: dict | None = None,
        title: str | None = None,
        summary: str | None = None,
        *,
        deliver_deck: bool = True,
        published_at: datetime | None = None,
    ) -> Version:
        """Publish a new version: the deck first, then the lesson, as Content writes them.
        `deliver_deck=False` holds the deck back (it is in `self.held`), as if it were still
        on its way."""
        now = published_at or datetime.now(UTC)
        if title is not None:
            lesson.title = title
        doc = normalise(doc or lesson.draft)
        if summary is None:
            summary = lesson.versions[-1].summary if lesson.versions else ""
        version = Version(
            uuid.uuid4(), lesson.id, len(lesson.versions) + 1, lesson.title, summary, doc, now
        )
        lesson.versions.append(version)
        envelope = self.bus.envelope(
            "content.lesson_version.published", deck_data(version), version.id, 1
        )
        self.bus.sent.append(envelope)
        if deliver_deck:
            self.bus.deliver(envelope)
        else:
            self.held = envelope
        lesson.status = "published"
        lesson.first_published_at = lesson.first_published_at or now
        lesson.published_at = now
        self._lesson_changed(lesson)
        return version

    def withdraw(self, lesson: Lesson) -> None:
        lesson.status = "withdrawn"
        lesson.withdrawn_at = datetime.now(UTC)
        self._lesson_changed(lesson)

    def restore(self, lesson: Lesson) -> None:
        lesson.status = "published"
        lesson.published_at = datetime.now(UTC)
        self._lesson_changed(lesson)

    def update_lesson(self, lesson: Lesson, **changes) -> None:
        """A draft title change, a move to another topic or a reorder."""
        for name, value in changes.items():
            setattr(lesson, name, value)
        if lesson.versions:
            self._lesson_changed(lesson)

    # --- Aptitude questions and the bank ---------------------------------------------------

    def _question_changed(self, question: Question) -> dict:
        return self.bus.publish(
            "content.aptitude_question.changed",
            {
                "question_id": str(question.id),
                "topic_id": str(question.topic.id),
                "level": question.level,
                "prompt": question.prompt,
                "options": question.options,
                "correct_option_id": question.correct_option_id,
                "is_active": question.is_active,
                "seed_key": question.seed_key,
            },
            question.id,
            question.version,
        )

    def question(
        self,
        topic: Topic,
        level: int = 1,
        *,
        prompt: str | None = None,
        options: list[dict] | None = None,
        correct: str = "a",
        active: bool = True,
        seed_key: str | None = None,
    ) -> Question:
        question = Question(
            uuid.uuid4(),
            topic,
            level,
            prompt or f"{topic.name} question at level {level}",
            options or OPTIONS,
            correct,
            active,
            seed_key,
        )
        self.questions.append(question)
        self._question_changed(question)
        self.publish_bank()
        return question

    def update_question(self, question: Question, **changes) -> None:
        for name, value in changes.items():
            setattr(question, name, value)
        question.version += 1
        self._question_changed(question)
        self.publish_bank()

    def bank_data(self) -> dict:
        """aptitude.bank(): active topics with a question, in quiz order, and whether each
        has an active question at every level."""
        assessed = sorted(
            (
                topic
                for topic in self.topics
                if not topic.archived and any(q.topic is topic for q in self.questions)
            ),
            key=lambda topic: (topic.position, topic.name),
        )
        rows = [
            {
                "topic_id": str(topic.id),
                "ready": all(
                    any(
                        q.topic is topic and q.level == level and q.is_active
                        for q in self.questions
                    )
                    for level in range(1, 6)
                ),
            }
            for topic in assessed
        ]
        return {"ready": bool(rows) and all(row["ready"] for row in rows), "topics": rows}

    def publish_bank(self) -> dict:
        self.bank_revision += 1
        return self.bus.publish(
            "content.aptitude_bank.changed", self.bank_data(), BANK_ID, self.bank_revision
        )

    def full_bank(self, topics: list[Topic]) -> dict[tuple[Topic, int], Question]:
        """One active question at every level for each topic: a ready quiz."""
        return {
            (topic, level): self.question(topic, level, seed_key=f"{topic.name}-{level}")
            for topic in topics
            for level in range(1, 6)
        }
