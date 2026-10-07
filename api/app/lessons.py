"""The administrators' lessons: the list and its order (SCRUM-66), writing them as decks of
cards (SCRUM-19, SCRUM-64), and publishing, withdrawing and restoring them (SCRUM-52).

Routes stay thin: they call these functions and turn a ContentProblem into an HTTP error.

- the list has every lesson of every status, without its cards, ordered as the admin
  portal shows it: by topic order, then by order within the topic. Lessons with no topic
  come last, and lessons in archived topics are included.
- lessons are ordered within their topic, and lessons with no topic among themselves.
  Moving a lesson to another topic belongs to the lesson editor, not to reordering.
- a reorder must list every lesson in that topic (or with no topic) exactly once, of any
  status, and say which order it replaces; a page that was out of date is refused rather
  than guessed at.
- reordering never changes a lesson's "last updated" time, which the list sorts by
  (SCRUM-66 AC3): moving a lesson is not editing it.
- every lesson has a working draft, which is what the editor changes, whatever the
  lesson's status. Users only ever see published versions, so a draft may be incomplete;
  what still stops it being published is reported as issues (app/lesson_doc.py).
- publishing copies the draft into a new version. Withdrawing hides the lesson from users;
  restoring brings its latest version back. Neither touches anyone's completions.
- every change names the "last updated" time the editor loaded, and is refused if the
  lesson has changed since, so one save never silently overwrites another.
- only a lesson that has never been published can be deleted: deleting a lesson deletes
  everyone's completions of it, which published lessons must keep (SCRUM-52 AC4).
- a lesson can be moved into any active topic, but not into an archived one. A lesson that
  is already in an archived topic keeps saving there. A lesson that has been published
  always keeps a topic.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.orm import Session

from app import lesson_doc, media
from app.lesson_doc import Issue, LessonDoc, Stats
from app.models import Lesson, LessonStatus, LessonVersion, Topic
from app.problems import (
    ContentProblem,
    check_reorder,
    lesson_has_blockers,
    lesson_not_deletable,
    lesson_not_found,
    lesson_out_of_date,
    lesson_status_conflict,
    topic_archived,
    topic_not_found,
    topic_required,
)


@dataclass(frozen=True)
class LessonSummary:
    id: uuid.UUID
    title: str
    summary: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    updated_at: datetime
    position: int
    deletable: bool
    has_unpublished_changes: bool
    # The latest version's number, or None for a lesson never published.
    version: int | None
    cards: int
    questions: int
    # The first image in the deck, for a thumbnail.
    cover_asset_id: uuid.UUID | None


@dataclass(frozen=True)
class VersionInfo:
    number: int
    published_at: datetime


@dataclass(frozen=True)
class LessonDetail:
    """One lesson as the editor needs it: the draft with everything said about it."""

    id: uuid.UUID
    key: str | None
    title: str
    summary: str
    topic_id: uuid.UUID | None
    status: LessonStatus
    published_at: datetime | None
    withdrawn_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime
    deletable: bool
    has_unpublished_changes: bool
    version: VersionInfo | None
    doc: dict
    issues: list[Issue]
    stats: Stats
    assets: dict


# --- Reading -------------------------------------------------------------------------------


def _latest_version(db: Session, lesson_id: uuid.UUID) -> LessonVersion | None:
    return db.scalar(
        select(LessonVersion)
        .where(LessonVersion.lesson_id == lesson_id)
        .order_by(LessonVersion.number.desc())
        .limit(1)
    )


def _cover(doc: dict) -> uuid.UUID | None:
    for card in doc.get("cards", []):
        image = card.get("image")
        if image:
            return uuid.UUID(image["asset_id"])
    return None


def _detail(db: Session, lesson: Lesson) -> LessonDetail:
    doc = LessonDoc.model_validate(lesson.draft)
    facts = media.facts_for(db, doc)
    topic = lesson.topic
    latest = _latest_version(db, lesson.id)
    return LessonDetail(
        id=lesson.id,
        key=lesson.key,
        title=lesson.title,
        summary=lesson.summary,
        topic_id=lesson.topic_id,
        status=lesson.status,
        published_at=lesson.published_at,
        withdrawn_at=lesson.withdrawn_at,
        position=lesson.position,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        deletable=latest is None,
        has_unpublished_changes=lesson.has_unpublished_changes,
        version=VersionInfo(latest.number, latest.published_at) if latest else None,
        doc=lesson.draft,
        issues=lesson_doc.issues(
            doc,
            title=lesson.title,
            has_topic=topic is not None,
            topic_archived=topic is not None and topic.archived_at is not None,
            media=facts,
        ),
        stats=lesson_doc.stats(doc, facts),
        assets=media.assets_for(db, doc),
    )


def _in_group(topic_id: uuid.UUID | None) -> ColumnElement[bool]:
    """The lessons ordered together: one topic's, or those with no topic."""
    return Lesson.topic_id.is_(None) if topic_id is None else Lesson.topic_id == topic_id


def list_lessons(db: Session) -> list[LessonSummary]:
    latest = (
        select(LessonVersion.lesson_id, func.max(LessonVersion.number).label("number"))
        .group_by(LessonVersion.lesson_id)
        .subquery()
    )
    query = (
        select(Lesson, latest.c.number)
        .outerjoin(Topic, Lesson.topic_id == Topic.id)
        .outerjoin(latest, latest.c.lesson_id == Lesson.id)
        .order_by(
            Topic.position.nulls_last(),
            Topic.created_at,
            Topic.id,
            Lesson.position,
            Lesson.created_at,
            Lesson.id,
        )
    )
    summaries = []
    for lesson, version in db.execute(query).all():
        cards = lesson.draft.get("cards", [])
        summaries.append(
            LessonSummary(
                id=lesson.id,
                title=lesson.title,
                summary=lesson.summary,
                topic_id=lesson.topic_id,
                status=lesson.status,
                updated_at=lesson.updated_at,
                position=lesson.position,
                deletable=version is None,
                has_unpublished_changes=lesson.has_unpublished_changes,
                version=version,
                cards=len(cards),
                questions=sum(1 for card in cards if card.get("question")),
                cover_asset_id=_cover(lesson.draft),
            )
        )
    return summaries


def get_lesson(db: Session, lesson_id: uuid.UUID) -> LessonDetail:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise lesson_not_found()
    return _detail(db, lesson)


# --- Order (SCRUM-66) ----------------------------------------------------------------------


def next_lesson_position(db: Session, topic_id: uuid.UUID | None) -> int:
    """Where a new lesson goes in its topic (or among lessons with no topic): the end."""
    return db.scalar(
        select(func.coalesce(func.max(Lesson.position) + 1, 0)).where(_in_group(topic_id))
    )


def reorder_lessons(
    db: Session,
    topic_id: uuid.UUID | None,
    ids: list[uuid.UUID],
    previous_ids: list[uuid.UUID],
) -> list[LessonSummary]:
    """Put one topic's lessons (or those with no topic) in the order `ids`, replacing the
    order `previous_ids`.

    See check_reorder for what is refused. The group's lessons are locked first, so two
    reorders of the same topic run one after the other instead of interleaving.
    """
    if topic_id is not None and db.get(Topic, topic_id) is None:
        raise topic_not_found()
    current = list(
        db.scalars(
            select(Lesson.id)
            .where(_in_group(topic_id))
            .order_by(Lesson.position, Lesson.created_at, Lesson.id)
            .with_for_update()
        )
    )
    try:
        check_reorder(ids, previous_ids, current)
    except ContentProblem:
        db.rollback()
        raise
    if ids:
        db.execute(
            update(Lesson)
            .where(Lesson.id.in_(ids))
            # Setting updated_at to itself stops the ORM's onupdate from bumping it.
            .values(
                position=case({lesson_id: n for n, lesson_id in enumerate(ids)}, value=Lesson.id),
                updated_at=Lesson.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
    db.commit()
    return list_lessons(db)


# --- Writing the draft (SCRUM-19, SCRUM-64) ------------------------------------------------


def _check_topic(db: Session, topic_id: uuid.UUID) -> None:
    """A topic a lesson may be put in: one that exists and is not archived."""
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise topic_not_found(field="topic_id")
    if topic.archived_at is not None:
        raise topic_archived(field="topic_id")


def prepare_doc(db: Session, doc: LessonDoc, make_id=None) -> dict:
    """A document ready to store: ids filled in, images and audio checked to exist."""
    lesson_doc.assign_ids(doc, make_id)
    media.check_references(db, doc)
    return lesson_doc.dump(doc)


def _differs_from(lesson: Lesson, version: LessonVersion | None) -> bool:
    if version is None:
        return False
    return (lesson.title, lesson.summary, lesson.draft) != (
        version.title,
        version.summary,
        version.doc,
    )


def create_lesson(
    db: Session,
    title: str = "",
    summary: str = "",
    topic_id: uuid.UUID | None = None,
    doc: LessonDoc | None = None,
    key: str | None = None,
) -> LessonDetail:
    """A new draft, at the end of its topic (or of the lessons with no topic)."""
    if topic_id is not None:
        _check_topic(db, topic_id)
    lesson = Lesson(
        key=key,
        title=title,
        summary=summary,
        topic_id=topic_id,
        draft=prepare_doc(db, doc or LessonDoc()),
        status=LessonStatus.DRAFT,
        position=next_lesson_position(db, topic_id),
    )
    db.add(lesson)
    db.commit()
    return _detail(db, lesson)


def _for_change(db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime) -> Lesson:
    """The lesson, locked, provided nobody has changed it since the editor loaded it."""
    lesson = db.get(Lesson, lesson_id, with_for_update=True)
    if lesson is None:
        raise lesson_not_found()
    if lesson.updated_at != expected_updated_at:
        raise lesson_out_of_date()
    return lesson


def update_lesson(
    db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime, changes: dict
) -> LessonDetail:
    """Change the draft's `title`, `summary`, `doc` or the lesson's `topic_id`: whichever
    `changes` holds.

    A save that changes nothing leaves "last updated" alone, since the ORM only writes (and
    only bumps updated_at) when a value differs. A new topic puts the lesson at the end of
    that topic, straight away even for a published lesson; the lessons it leaves keep their
    positions, gap and all.
    """
    try:
        lesson = _for_change(db, lesson_id, expected_updated_at)
        if "topic_id" in changes and changes["topic_id"] != lesson.topic_id:
            topic_id = changes["topic_id"]
            if topic_id is None:
                if _latest_version(db, lesson.id) is not None:
                    raise topic_required()
            else:
                _check_topic(db, topic_id)
            # Worked out before the move, so the lesson does not count itself.
            position = next_lesson_position(db, topic_id)
            lesson.topic_id = topic_id
            lesson.position = position
        if "doc" in changes:
            draft = prepare_doc(db, changes["doc"])
            if draft != lesson.draft:
                lesson.draft = draft
        for field in ("title", "summary"):
            if field in changes and changes[field] != getattr(lesson, field):
                setattr(lesson, field, changes[field])
        changed = _differs_from(lesson, _latest_version(db, lesson.id))
        if changed != lesson.has_unpublished_changes:
            lesson.has_unpublished_changes = changed
    except (ContentProblem, ValueError):
        db.rollback()
        raise
    db.commit()
    db.refresh(lesson)
    return _detail(db, lesson)


def delete_lesson(db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime) -> None:
    """Delete a lesson that has never been published."""
    try:
        lesson = db.get(Lesson, lesson_id, with_for_update=True)
        if lesson is None:
            raise lesson_not_found()
        if _latest_version(db, lesson.id) is not None:
            raise lesson_not_deletable()
        if lesson.updated_at != expected_updated_at:
            raise lesson_out_of_date()
    except ContentProblem:
        db.rollback()
        raise
    db.delete(lesson)
    db.commit()


# --- Publishing (SCRUM-52, SCRUM-56, SCRUM-70) ---------------------------------------------


def blockers_of(db: Session, lesson: Lesson) -> list[Issue]:
    return [issue for issue in _detail(db, lesson).issues if issue.severity == "blocker"]


def publish_lesson(
    db: Session,
    lesson_id: uuid.UUID,
    expected_updated_at: datetime,
    published_by: uuid.UUID | None = None,
) -> LessonDetail:
    """Make the draft what users see.

    Refused while anything blocks it (lesson_has_blockers, with the issues). The draft
    becomes a new version unless it is the same as the latest one, so publishing a withdrawn
    lesson that has not changed simply brings it back. A first publish keeps the lesson
    where it is in its topic, which for a new lesson is the end.
    """
    try:
        lesson = _for_change(db, lesson_id, expected_updated_at)
        blockers = blockers_of(db, lesson)
        if blockers:
            raise lesson_has_blockers(blockers)
        latest = _latest_version(db, lesson.id)
        new_version = latest is None or _differs_from(lesson, latest)
        if not new_version and lesson.status == LessonStatus.PUBLISHED:
            db.rollback()
            return _detail(db, lesson)
        now = datetime.now(UTC)
        if new_version:
            db.add(
                LessonVersion(
                    lesson_id=lesson.id,
                    number=latest.number + 1 if latest else 1,
                    title=lesson.title,
                    summary=lesson.summary,
                    doc=lesson.draft,
                    published_at=now,
                    published_by=published_by,
                )
            )
        lesson.status = LessonStatus.PUBLISHED
        lesson.published_at = now
        lesson.has_unpublished_changes = False
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    db.refresh(lesson)
    return _detail(db, lesson)


def discard_changes(
    db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime
) -> LessonDetail:
    """Put the draft back to the latest version."""
    try:
        lesson = _for_change(db, lesson_id, expected_updated_at)
        latest = _latest_version(db, lesson.id)
        if latest is None:
            raise lesson_status_conflict(
                "This lesson has never been published, so there is nothing to go back to."
            )
        if _differs_from(lesson, latest):
            lesson.title = latest.title
            lesson.summary = latest.summary
            lesson.draft = latest.doc
        lesson.has_unpublished_changes = False
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    db.refresh(lesson)
    return _detail(db, lesson)


def withdraw_lesson(
    db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime
) -> LessonDetail:
    """Hide a published lesson from users. Their completions and history keep it
    (SCRUM-52 AC3, AC4)."""
    try:
        lesson = _for_change(db, lesson_id, expected_updated_at)
        if lesson.status != LessonStatus.PUBLISHED:
            raise lesson_status_conflict("Only a published lesson can be withdrawn.")
        lesson.status = LessonStatus.WITHDRAWN
        lesson.withdrawn_at = datetime.now(UTC)
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    db.refresh(lesson)
    return _detail(db, lesson)


def restore_lesson(
    db: Session, lesson_id: uuid.UUID, expected_updated_at: datetime
) -> LessonDetail:
    """Show a withdrawn lesson to users again, as its latest version. Changes made to the
    draft since stay in the draft."""
    try:
        lesson = _for_change(db, lesson_id, expected_updated_at)
        if lesson.status != LessonStatus.WITHDRAWN or _latest_version(db, lesson.id) is None:
            raise lesson_status_conflict("Only a withdrawn lesson can be restored.")
        lesson.status = LessonStatus.PUBLISHED
        lesson.published_at = datetime.now(UTC)
    except ContentProblem:
        db.rollback()
        raise
    db.commit()
    db.refresh(lesson)
    return _detail(db, lesson)
