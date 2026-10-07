"""SCRUM-19, SCRUM-77: loading lessons from files in content/."""

import io
import struct
import wave
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app.cli import main as cli
from app.config import get_settings
from app.content_import import find_lesson_files, import_folder, key_for
from app.models import Lesson, LessonStatus, LessonVersion, MediaAsset, Topic

LESSON = """\
title: Ordering kopi
summary: Coffee, in code.
topic: Hawker & Food
cards:
  - text: At a kopitiam, coffee is ordered in **code**.
    image: { file: kopi.png, alt: Two cups of kopi }
  - text: "**O** means no milk."
    audio: { file: kopi.wav, transcript: Kopi O! }
  - text: Black coffee with sugar is kopi {{blank}}.
    question:
      options:
        - { text: O, correct: true }
        - { text: C, why_not: C has evaporated milk. }
      explanation: O means no milk.
"""


def _png(colour=(230, 80, 90)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (400, 300), colour).save(out, "PNG")
    return out.getvalue()


def _wav() -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(8000)
        recording.writeframes(struct.pack("<h", 0) * 8000)
    return out.getvalue()


def _write(root: Path, folder: str, text: str = LESSON, media: bool = True) -> Path:
    path = root / folder
    path.mkdir(parents=True, exist_ok=True)
    (path / "lesson.yaml").write_text(text)
    if media:
        (path / "kopi.png").write_bytes(_png())
        (path / "kopi.wav").write_bytes(_wav())
    return path


def _lesson(db, key: str) -> Lesson:
    db.expire_all()
    return db.scalar(select(Lesson).where(Lesson.key == key))


def test_keys_come_from_folders_without_number_prefixes(tmp_path):
    path = _write(tmp_path, "02-hawker-food/01-ordering-kopi") / "lesson.yaml"
    assert key_for(path, tmp_path) == "hawker-food/ordering-kopi"


def test_files_are_found_in_folder_order(tmp_path):
    for folder in ["b/02-second", "a/01-first", "b/01-first"]:
        _write(tmp_path, folder, media=False)
    keys = [key_for(path, tmp_path) for path in find_lesson_files(tmp_path)]
    assert keys == ["a/first", "b/first", "b/second"]


def test_a_new_lesson_is_created_with_its_media(db, tmp_path):
    _write(tmp_path, "hawker/01-kopi")

    [result] = import_folder(db, tmp_path)

    assert (result.action, result.published, result.problems) == ("created", False, [])
    lesson = _lesson(db, "hawker/kopi")
    assert (lesson.title, lesson.summary, lesson.status) == (
        "Ordering kopi",
        "Coffee, in code.",
        LessonStatus.DRAFT,
    )
    assert lesson.topic.name == "Hawker & Food"  # created, since it did not exist
    image, audio, quiz = lesson.draft["cards"]
    assert image["image"]["alt"] == "Two cups of kopi"
    assert audio["audio"]["transcript"] == "Kopi O!"
    assert quiz["question"]["options"][1]["why_not"] == "C has evaporated milk."
    kinds = {row.kind.value for row in db.scalars(select(MediaAsset))}
    assert kinds == {"image", "audio"}
    assert db.get(MediaAsset, image["image"]["asset_id"]).kind.value == "image"


def test_publish_publishes_lessons_that_are_ready(db, tmp_path):
    _write(tmp_path, "hawker/01-kopi")

    [result] = import_folder(db, tmp_path, publish=True)

    assert (result.published, result.version) == (True, 1)
    lesson = _lesson(db, "hawker/kopi")
    assert lesson.status == LessonStatus.PUBLISHED
    assert [version.number for version in lesson.versions] == [1]


def test_loading_again_changes_nothing(db, tmp_path):
    _write(tmp_path, "hawker/01-kopi")
    import_folder(db, tmp_path, publish=True)
    before = _lesson(db, "hawker/kopi")
    snapshot = (before.updated_at, before.draft, len(before.versions))

    [result] = import_folder(db, tmp_path, publish=True)

    after = _lesson(db, "hawker/kopi")
    assert (result.action, result.published) == ("unchanged", False)
    assert (after.updated_at, after.draft, len(after.versions)) == snapshot
    assert db.query(Lesson).count() == 1
    assert db.query(MediaAsset).count() == 2


def test_a_changed_file_updates_the_draft_and_publishes_a_new_version(db, tmp_path):
    folder = _write(tmp_path, "hawker/01-kopi")
    import_folder(db, tmp_path, publish=True)
    (folder / "lesson.yaml").write_text(
        LESSON.replace("Ordering kopi", "Ordering kopi like a local")
    )

    [result] = import_folder(db, tmp_path, publish=True)

    assert (result.action, result.published, result.version) == ("updated", True, 2)
    lesson = _lesson(db, "hawker/kopi")
    assert [v.title for v in lesson.versions] == ["Ordering kopi", "Ordering kopi like a local"]


def test_a_changed_file_without_publish_leaves_users_on_the_published_version(db, tmp_path):
    folder = _write(tmp_path, "hawker/01-kopi")
    import_folder(db, tmp_path, publish=True)
    (folder / "lesson.yaml").write_text(LESSON.replace("Coffee, in code.", "New summary"))

    import_folder(db, tmp_path)

    lesson = _lesson(db, "hawker/kopi")
    assert lesson.has_unpublished_changes is True
    assert [v.summary for v in lesson.versions] == ["Coffee, in code."]


def test_an_existing_lesson_with_the_same_title_is_adopted(db, tmp_path):
    topic = Topic(name="Somewhere else")
    old = Lesson(title="ordering KOPI", topic=topic, status=LessonStatus.PUBLISHED)
    old.versions.append(
        LessonVersion(
            number=1, title="ordering KOPI", doc={"cards": []}, published_at=datetime.now(UTC)
        )
    )
    db.add(old)
    db.commit()
    _write(tmp_path, "hawker/01-kopi")

    [result] = import_folder(db, tmp_path, publish=True)

    assert (result.action, result.version) == ("updated", 2)
    assert db.query(Lesson).count() == 1
    lesson = _lesson(db, "hawker/kopi")
    assert lesson.id == old.id
    # Where it sits is the administrator's, not the file's.
    assert lesson.topic.name == "Somewhere else"


def test_files_never_move_a_lesson_an_administrator_moved(db, tmp_path):
    _write(tmp_path, "hawker/01-kopi")
    import_folder(db, tmp_path)
    lesson = _lesson(db, "hawker/kopi")
    elsewhere = Topic(name="Elsewhere", position=5)
    db.add(elsewhere)
    db.flush()
    lesson.topic_id, lesson.position = elsewhere.id, 3
    db.commit()

    import_folder(db, tmp_path)

    lesson = _lesson(db, "hawker/kopi")
    assert (lesson.topic.name, lesson.position) == ("Elsewhere", 3)


def test_new_lessons_go_to_the_end_of_their_topic_in_folder_order(db, tmp_path):
    for n, title in enumerate(["First", "Second", "Third"], start=1):
        _write(tmp_path, f"hawker/0{n}-{title.lower()}", LESSON.replace("Ordering kopi", title))

    import_folder(db, tmp_path)

    titles = db.scalars(select(Lesson.title).order_by(Lesson.position))
    assert list(titles) == ["First", "Second", "Third"]


def test_withdrawn_lessons_are_not_published_again(db, tmp_path):
    folder = _write(tmp_path, "hawker/01-kopi")
    import_folder(db, tmp_path, publish=True)
    lesson = _lesson(db, "hawker/kopi")
    lesson.status = LessonStatus.WITHDRAWN
    db.commit()
    (folder / "lesson.yaml").write_text(LESSON.replace("Coffee, in code.", "Changed"))

    [result] = import_folder(db, tmp_path, publish=True)

    assert (result.action, result.published) == ("updated", False)
    assert _lesson(db, "hawker/kopi").status == LessonStatus.WITHDRAWN


def test_publish_false_keeps_a_lesson_as_a_draft(db, tmp_path):
    _write(tmp_path, "gallery/01-cards", "publish: false\n" + LESSON)

    [result] = import_folder(db, tmp_path, publish=True)

    assert result.published is False
    assert _lesson(db, "gallery/cards").status == LessonStatus.DRAFT


def test_a_lesson_that_is_not_ready_is_loaded_but_not_published(db, tmp_path):
    _write(
        tmp_path, "hawker/01-kopi", "title: Unfinished\ncards:\n  - text: Only text\n", media=False
    )

    [result] = import_folder(db, tmp_path, publish=True)

    assert (result.action, result.published) == ("created", False)
    assert any("Choose a topic" in problem for problem in result.problems)
    assert _lesson(db, "hawker/kopi").status == LessonStatus.DRAFT


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("title: [unclosed", "Not valid YAML"),
        ("title: T\ncolour: red\n", "colour: Extra inputs are not permitted"),
        ("cards: []\n", "title: Field required"),
        ("title: T\ncards:\n  - text: A\n    explaination: typo\n", "explaination"),
        ("title: T\ncards:\n  - text: A\n    image: missing.png\n", "there is no file missing.png"),
        ("title: T\ncards:\n  - text: A\n    audio: kopi.png\n", "kopi.png is not audio"),
        ("title: T\ncards:\n  - {id: same, text: A}\n  - {id: same, text: B}\n", "more than once"),
    ],
)
def test_a_broken_file_is_reported_and_the_others_still_load(db, tmp_path, text, message):
    _write(tmp_path, "a/01-broken", text)
    _write(tmp_path, "b/01-fine")

    broken, fine = import_folder(db, tmp_path)

    assert broken.action == "failed"
    assert message in broken.problems[0]
    assert fine.action == "created"
    assert db.query(Lesson).count() == 1


def test_the_command_reports_each_lesson(db, tmp_path, capsys):
    _write(tmp_path, "hawker/01-kopi")

    assert cli(["import-lessons", str(tmp_path), "--publish"]) == 0

    assert "created   hawker/kopi (published as version 1)" in capsys.readouterr().out


def test_the_command_fails_when_a_file_cannot_be_loaded(db, tmp_path):
    _write(tmp_path, "hawker/01-kopi", "title: [unclosed")
    assert cli(["import-lessons", str(tmp_path)]) == 1


def test_every_lesson_in_the_repository_loads_and_is_ready(db):
    """Guards content/: a lesson file someone edits must still load, and publish if meant to."""
    root = get_settings().content_dir
    results = import_folder(db, root, publish=True)

    assert results, f"no lesson files under {root}"
    for result in results:
        assert result.action == "created", (result.key, result.problems)
        assert result.problems == [], (result.key, result.problems)
