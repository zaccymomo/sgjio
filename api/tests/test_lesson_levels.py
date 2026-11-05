"""SCRUM-103: a level from 1 to 5 on each lesson, chosen when it is created and fixed once
it has been published, shown in the admin lesson list and counted per topic."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.content_import import import_folder
from app.models import Lesson, Topic, UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
URL = "/api/admin/lessons"

READY_DOC = {
    "cards": [
        {"text": "**Kopi** is coffee with condensed milk."},
        {
            "text": "Black coffee with sugar is kopi {{blank}}.",
            "question": {
                "options": [{"text": "O", "correct": True}, {"text": "C", "why_not": "Milk."}],
                "explanation": "O means no milk.",
            },
        },
    ]
}


@pytest.fixture
def admin(client, make_user):
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 200
    return client


@pytest.fixture
def topic(db) -> Topic:
    topic = Topic(name="Hawker & Food")
    db.add(topic)
    db.commit()
    return topic


def _create(admin, topic: Topic, level: int, title: str = "Ordering kopi") -> dict:
    body = {"title": title, "topic_id": str(topic.id), "doc": READY_DOC, "level": level}
    response = admin.post(URL, json=body)
    assert response.status_code == 201
    return response.json()


def _save(admin, lesson: dict, **changes):
    return admin.patch(
        f"{URL}/{lesson['id']}", json={"updated_at": lesson["updated_at"], **changes}
    )


def _publish(admin, lesson: dict) -> dict:
    response = admin.post(
        f"{URL}/{lesson['id']}/publish", json={"updated_at": lesson["updated_at"]}
    )
    assert response.status_code == 200
    return response.json()


def _code(response) -> str:
    return response.json()["detail"]["code"]


# --- AC1: chosen when the lesson is created -----------------------------------------------


def test_a_new_lesson_must_name_its_level(admin, db):
    response = admin.post(URL, json={"title": "Ordering kopi"})

    assert response.status_code == 422
    assert db.query(Lesson).count() == 0


@pytest.mark.parametrize("level", [0, 6, None, "high"])
def test_a_level_outside_1_to_5_is_refused(admin, db, level):
    response = admin.post(URL, json={"level": level})

    assert response.status_code == 422
    assert db.query(Lesson).count() == 0


@pytest.mark.parametrize("level", [1, 3, 5])
def test_the_chosen_level_is_kept(admin, db, topic, level):
    lesson = _create(admin, topic, level)

    assert lesson["level"] == level
    assert admin.get(f"{URL}/{lesson['id']}").json()["level"] == level
    assert db.get(Lesson, lesson["id"]).level == level


def test_an_otherwise_empty_draft_only_needs_its_level(admin):
    response = admin.post(URL, json={"level": 2})

    assert response.status_code == 201
    assert response.json()["level"] == 2


# --- AC2, as decided by the team: changeable until first published ------------------------


def test_a_draft_never_published_can_change_level(admin, topic):
    lesson = _create(admin, topic, 1)

    response = _save(admin, lesson, level=4)

    assert response.status_code == 200
    assert response.json()["level"] == 4


def test_a_published_lesson_keeps_its_level(admin, db, topic):
    lesson = _publish(admin, _create(admin, topic, 2))

    response = _save(admin, lesson, level=3)

    assert response.status_code == 409
    assert _code(response) == "level_locked"
    assert response.json()["detail"]["field"] == "level"
    db.expire_all()
    assert db.get(Lesson, lesson["id"]).level == 2


def test_a_refused_level_change_saves_nothing_else(admin, db, topic):
    lesson = _publish(admin, _create(admin, topic, 2))

    response = _save(admin, lesson, title="Renamed", level=3)

    assert response.status_code == 409
    db.expire_all()
    assert db.get(Lesson, lesson["id"]).title == "Ordering kopi"


def test_saving_a_published_lesson_with_its_own_level_is_fine(admin, topic):
    """The editor sends every field on each save, the level included."""
    lesson = _publish(admin, _create(admin, topic, 2))

    response = _save(admin, lesson, title="Ordering kopi at a kopitiam", level=2)

    assert response.status_code == 200
    assert response.json()["title"] == "Ordering kopi at a kopitiam"


def test_a_withdrawn_lesson_still_keeps_its_level(admin, topic):
    """It was published, so learners may have completed it or been exempted from it."""
    lesson = _publish(admin, _create(admin, topic, 2))
    withdrawn = admin.post(
        f"{URL}/{lesson['id']}/withdraw", json={"updated_at": lesson["updated_at"]}
    ).json()

    response = _save(admin, withdrawn, level=1)

    assert response.status_code == 409
    assert _code(response) == "level_locked"


def test_saving_without_a_level_leaves_it_alone(admin, topic):
    lesson = _create(admin, topic, 3)

    response = _save(admin, lesson, title="Renamed")

    assert response.status_code == 200
    assert response.json()["level"] == 3


def test_the_level_is_not_versioned(admin, db, topic):
    """Changing it before the first publish is not a change to publish."""
    lesson = _create(admin, topic, 1)
    saved = _save(admin, lesson, level=4).json()

    assert saved["has_unpublished_changes"] is False
    published = _publish(admin, saved)
    assert published["level"] == 4
    assert published["version"]["number"] == 1


# --- AC3: shown in the lesson list --------------------------------------------------------


def test_the_lesson_list_shows_each_level(admin, topic):
    _create(admin, topic, 1, "First")
    _create(admin, topic, 4, "Fourth")

    rows = admin.get(URL).json()

    assert [(row["title"], row["level"]) for row in rows] == [("First", 1), ("Fourth", 4)]


# --- AC4: lessons from before levels are Level 1 ------------------------------------------


def test_lessons_built_without_a_level_are_level_1(db, topic):
    lesson = Lesson(title="Old", topic_id=topic.id)
    db.add(lesson)
    db.commit()

    assert lesson.level == 1


# --- AC5: published lessons at each level, per topic --------------------------------------


def test_topics_count_published_lessons_at_each_level(admin, db, topic):
    for level, title in [(1, "a"), (1, "b"), (3, "c"), (5, "d")]:
        _publish(admin, _create(admin, topic, level, title))
    _create(admin, topic, 2, "draft")  # drafts are not counted
    withdrawn = _publish(admin, _create(admin, topic, 4, "withdrawn"))
    admin.post(f"{URL}/{withdrawn['id']}/withdraw", json={"updated_at": withdrawn["updated_at"]})
    empty = Topic(name="Festivals", position=1)
    db.add(empty)
    db.commit()

    rows = {row["name"]: row for row in admin.get("/api/admin/topics").json()}

    assert rows["Hawker & Food"]["published_by_level"] == [2, 0, 1, 0, 1]
    assert rows["Hawker & Food"]["published_count"] == 4
    assert rows["Festivals"]["published_by_level"] == [0, 0, 0, 0, 0]


def test_a_new_topic_starts_with_no_lessons_at_any_level(admin):
    response = admin.post("/api/admin/topics", json={"name": "Festivals"})

    assert response.json()["published_by_level"] == [0, 0, 0, 0, 0]


# --- Lesson files ---------------------------------------------------------------------------

LESSON = """\
title: Ordering kopi
topic: Hawker & Food
{level}cards:
  - text: Black coffee with sugar is kopi {{{{blank}}}}.
    question:
      options:
        - {{ text: O, correct: true }}
        - {{ text: C, why_not: C has evaporated milk. }}
      explanation: O means no milk.
"""


def _write(root: Path, level: int | None) -> None:
    folder = root / "hawker-food" / "ordering-kopi"
    folder.mkdir(parents=True, exist_ok=True)
    line = f"level: {level}\n" if level is not None else ""
    (folder / "lesson.yaml").write_text(LESSON.format(level=line))


def _imported(db) -> Lesson:
    db.expire_all()
    return db.scalar(select(Lesson).where(Lesson.key == "hawker-food/ordering-kopi"))


def test_a_lesson_file_sets_the_level(db, tmp_path):
    _write(tmp_path, 3)

    import_folder(db, tmp_path)

    assert _imported(db).level == 3


def test_a_lesson_file_without_a_level_is_level_1(db, tmp_path):
    _write(tmp_path, None)

    import_folder(db, tmp_path)

    assert _imported(db).level == 1


def test_a_file_changes_a_draft_s_level(db, tmp_path):
    _write(tmp_path, 1)
    import_folder(db, tmp_path)
    _write(tmp_path, 4)

    [result] = import_folder(db, tmp_path)

    assert result.action == "updated"
    assert _imported(db).level == 4


def test_a_file_without_a_level_keeps_one_chosen_in_the_portal(db, tmp_path):
    _write(tmp_path, None)
    import_folder(db, tmp_path)
    lesson = _imported(db)
    lesson.level = 3
    db.commit()

    [result] = import_folder(db, tmp_path)

    assert result.action == "unchanged"
    assert _imported(db).level == 3


def test_a_file_cannot_change_a_published_lesson_s_level(db, tmp_path):
    _write(tmp_path, 2)
    import_folder(db, tmp_path, publish=True)
    _write(tmp_path, 5)

    [result] = import_folder(db, tmp_path, publish=True)

    assert _imported(db).level == 2
    assert any("Level 2" in problem for problem in result.problems)


def test_a_file_with_a_level_outside_1_to_5_is_refused(db, tmp_path):
    _write(tmp_path, 6)

    [result] = import_folder(db, tmp_path)

    assert result.action == "failed"
    assert _imported(db) is None


# --- Order: by level first, reordered only within a level ----------------------------------


def _order(admin, topic: Topic) -> list[str]:
    return [row["title"] for row in admin.get(URL).json() if row["topic_id"] == str(topic.id)]


def _ids(admin, topic: Topic) -> dict[str, str]:
    return {row["title"]: row["id"] for row in admin.get(URL).json()}


def _reorder(admin, topic: Topic, titles: list[str]):
    ids = _ids(admin, topic)
    return admin.put(
        f"{URL}/order",
        json={
            "topic_id": str(topic.id),
            "ids": [ids[title] for title in titles],
            "previous_ids": [ids[title] for title in _order(admin, topic)],
        },
    )


def test_lessons_are_listed_by_level_then_by_order(admin, topic):
    _create(admin, topic, 3, "Third")
    _create(admin, topic, 1, "First")
    _create(admin, topic, 2, "Second")
    _create(admin, topic, 1, "Also first")

    assert _order(admin, topic) == ["First", "Also first", "Second", "Third"]


def test_lessons_reorder_within_a_level(admin, topic):
    _create(admin, topic, 1, "a")
    _create(admin, topic, 1, "b")
    _create(admin, topic, 2, "c")

    response = _reorder(admin, topic, ["b", "a", "c"])

    assert response.status_code == 200
    assert _order(admin, topic) == ["b", "a", "c"]


def test_a_lesson_cannot_move_above_a_lower_level(admin, topic):
    _create(admin, topic, 1, "a")
    _create(admin, topic, 2, "b")

    response = _reorder(admin, topic, ["b", "a"])

    assert response.status_code == 409
    assert _code(response) == "lesson_order_mixes_levels"
    assert _order(admin, topic) == ["a", "b"]


def test_a_new_level_puts_a_draft_at_the_end_of_that_level(admin, topic):
    _create(admin, topic, 2, "Level 2 first")
    _create(admin, topic, 2, "Level 2 second")
    moving = _create(admin, topic, 1, "Moving")

    _save(admin, moving, level=2)

    assert _order(admin, topic) == ["Level 2 first", "Level 2 second", "Moving"]
