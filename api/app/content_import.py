"""Loading lessons from files in content/ (SCRUM-19, SCRUM-77).

Lessons can be written without the admin portal: one folder per lesson, holding a
`lesson.yaml` and the images and audio its cards use. See content/README.md for the format.
`python -m app.cli import-lessons` and the seed both come through here.

- a lesson's key is its folder path without number prefixes ("hawker-food/ordering-kopi"
  for content/lessons/02-hawker-food/01-ordering-kopi), unless the file sets `key`. Loading
  a file again updates the lesson with that key rather than adding another.
- a lesson with no key yet but the same title (one seeded or written before files had keys)
  is adopted the first time, rather than duplicated.
- files hold a lesson's content: title, summary and cards. Where a lesson sits (its topic
  and position) is set only when it is first created, so loading files never undoes an
  administrator's reordering. A missing topic is created, at the end.
- ids the file leaves out are derived from the key, so loading an unchanged file changes
  nothing at all. Images and audio are stored once however often they are loaded.
- with `publish`, a lesson is published when its content is new or changed, unless the file
  says `publish: false`, something blocks it, or an administrator has withdrawn it.
  Publishing never touches anyone's progress.
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import lessons, media
from app.lesson_doc import LessonDoc
from app.models import Lesson, LessonStatus, Topic
from app.problems import ContentProblem
from app.topics import next_topic_position

LESSON_FILES = ("lesson.yaml", "lesson.yml", "lesson.json")
_NUMBER_PREFIX = re.compile(r"^\d+[-_ ]+")


class LessonFile(BaseModel):
    """The top of a lesson file. Cards are checked as lesson documents once their image and
    audio files have been stored."""

    model_config = ConfigDict(extra="forbid")

    key: str | None = Field(default=None, max_length=200)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=160)
    topic: str | None = Field(default=None, max_length=80)
    publish: bool = True
    cards: list[dict] = Field(default_factory=list)


@dataclass
class Result:
    path: Path
    key: str
    title: str = ""
    # created, updated, unchanged or failed
    action: str = "unchanged"
    published: bool = False
    version: int | None = None
    # Why it could not be loaded or published.
    problems: list[str] = field(default_factory=list)

    def describe(self) -> str:
        text = f"{self.action:<9} {self.key}"
        if self.published:
            text += f" (published as version {self.version})"
        return text


class ContentError(ValueError):
    """A lesson file that cannot be loaded, with a message saying what to fix."""


def find_lesson_files(root: Path) -> list[Path]:
    """Every lesson file under `root`, in folder order, which is the order new lessons are
    placed in their topics."""
    return sorted(p for p in root.rglob("*") if p.name in LESSON_FILES and p.is_file())


def key_for(path: Path, root: Path) -> str:
    parts = path.parent.relative_to(root).parts
    return "/".join(_NUMBER_PREFIX.sub("", part) for part in parts)


def _read(path: Path) -> LessonFile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ContentError(f"Not valid YAML: {error}") from None
    try:
        return LessonFile.model_validate(raw)
    except ValidationError as error:
        raise ContentError(_explain(error)) from None


def _explain(error: ValidationError) -> str:
    lines = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "file"
        lines.append(f"{where}: {item['msg']}")
    return "; ".join(lines)


def _store_media(db: Session, folder: Path, cards: list[dict]) -> list[dict]:
    """The cards with each `file` swapped for the id of the stored image or audio."""
    stored = []
    for n, card in enumerate(cards):
        card = dict(card)
        for kind, text_field in (("image", "alt"), ("audio", "transcript")):
            value = card.get(kind)
            if value is None:
                continue
            if isinstance(value, str):  # "image: kopi.png" is short for "image: {file: ...}"
                value = {"file": value}
            if not isinstance(value, dict) or "file" not in value:
                continue  # left to the document check, e.g. an asset_id given directly
            path = folder / value["file"]
            if not path.is_file():
                raise ContentError(f"cards.{n}.{kind}: there is no file {value['file']} here")
            try:
                asset = media.store(db, path.read_bytes(), path.name, None)
            except ContentProblem as problem:
                raise ContentError(
                    f"cards.{n}.{kind}: {value['file']}: {problem.message}"
                ) from None
            if asset.kind.value != kind:
                raise ContentError(f"cards.{n}.{kind}: {value['file']} is not {kind}")
            ref = {key: v for key, v in value.items() if key != "file"}
            card[kind] = {"asset_id": str(asset.id), text_field: "", **ref}
        stored.append(card)
    return stored


def _topic(db: Session, name: str | None) -> Topic | None:
    if not name:
        return None
    topic = db.scalar(select(Topic).where(func.lower(Topic.name) == name.strip().lower()))
    if topic is None:
        topic = Topic(name=name.strip(), position=next_topic_position(db))
        db.add(topic)
        db.flush()
    return topic


def _find(db: Session, key: str, title: str) -> Lesson | None:
    lesson = db.scalar(select(Lesson).where(Lesson.key == key))
    if lesson is None:
        lesson = db.scalar(
            select(Lesson)
            .where(Lesson.key.is_(None), func.lower(Lesson.title) == title.lower())
            .order_by(Lesson.created_at)
            .limit(1)
        )
    return lesson


def import_file(db: Session, path: Path, root: Path, publish: bool = False) -> Result:
    """Load one lesson file. Raises ContentError if the file cannot be loaded."""
    data = _read(path)
    key = data.key or key_for(path, root)
    result = Result(path=path, key=key, title=data.title)
    try:
        cards = _store_media(db, path.parent, data.cards)
        doc = LessonDoc.model_validate({"cards": cards})
    except ValidationError as error:
        db.rollback()
        raise ContentError(_explain(error)) from None
    prefix = hashlib.sha1(key.encode()).hexdigest()[:6]
    try:
        draft = lessons.prepare_doc(db, doc, lambda part: f"{prefix}-{part}")
    except ValueError as error:
        db.rollback()
        raise ContentError(str(error)) from None

    lesson = _find(db, key, data.title)
    if lesson is None:
        topic = _topic(db, data.topic)
        lesson = Lesson(
            key=key,
            title=data.title,
            summary=data.summary,
            topic_id=topic.id if topic else None,
            draft=draft,
            status=LessonStatus.DRAFT,
            position=lessons.next_lesson_position(db, topic.id if topic else None),
        )
        db.add(lesson)
        result.action = "created"
    elif (lesson.title, lesson.summary, lesson.draft) != (data.title, data.summary, draft):
        lesson.title, lesson.summary, lesson.draft = data.title, data.summary, draft
        result.action = "updated"
    lesson.key = key
    db.flush()
    latest = lessons.latest_version(db, lesson.id)
    lesson.has_unpublished_changes = latest is not None and (
        (lesson.title, lesson.summary, lesson.draft) != (latest.title, latest.summary, latest.doc)
    )
    db.commit()

    wants_publish = publish and data.publish and lesson.status != LessonStatus.WITHDRAWN
    if wants_publish and (
        latest is None or lesson.has_unpublished_changes or lesson.status == LessonStatus.DRAFT
    ):
        blockers = lessons.blockers_of(db, lesson)
        if blockers:
            result.problems = [f"not published: {issue.message}" for issue in blockers]
        else:
            detail = lessons.publish_lesson(db, lesson.id, lesson.updated_at)
            result.published = True
            result.version = detail.version.number if detail.version else None
    return result


def import_folder(db: Session, root: Path, publish: bool = False) -> list[Result]:
    """Load every lesson file under `root`. A file that cannot be loaded is reported in its
    result and skipped; the others still load."""
    results = []
    for path in find_lesson_files(root):
        try:
            results.append(import_file(db, path, root, publish))
        except ContentError as error:
            db.rollback()
            results.append(
                Result(path=path, key=key_for(path, root), action="failed", problems=[str(error)])
            )
    return results
