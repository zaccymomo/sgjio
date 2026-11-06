"""SCRUM-66: the administrators' lesson list, and the order of lessons within a topic."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.lessons import next_lesson_position
from app.models import Lesson, LessonStatus, LessonVersion, Topic

URL = "/api/admin/lessons"
ORDER_URL = f"{URL}/order"


def _topic(db, name: str, position: int = 0, archived: bool = False) -> Topic:
    topic = Topic(name=name, position=position, archived_at=datetime.now(UTC) if archived else None)
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db,
    topic: Topic | None,
    title: str,
    position: int = 0,
    status: LessonStatus = LessonStatus.PUBLISHED,
    created_at: datetime | None = None,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, status=status, position=position)
    if created_at is not None:
        lesson.created_at = created_at
    if status != LessonStatus.DRAFT:
        # Published and withdrawn lessons have been published, so they have a version.
        lesson.versions.append(
            LessonVersion(number=1, title=title, doc={"cards": []}, published_at=datetime.now(UTC))
        )
    db.add(lesson)
    db.commit()
    return lesson


def _titles(client) -> list[str]:
    return [row["title"] for row in client.get(URL).json()]


def _group_ids(client, topic: Topic | None) -> list[str]:
    """One group's lessons in the order the admin page shows them."""
    topic_id = str(topic.id) if topic else None
    return [row["id"] for row in client.get(URL).json() if row["topic_id"] == topic_id]


def _reorder(client, topic: Topic | None, lessons: list, previous_ids: list | None = None):
    """Reorder as the page does: the new order, plus the order the page was showing."""
    return client.put(
        ORDER_URL,
        json={
            "topic_id": str(topic.id) if topic else None,
            "ids": [str(getattr(lesson, "id", lesson)) for lesson in lessons],
            "previous_ids": _group_ids(client, topic) if previous_ids is None else previous_ids,
        },
    )


# --- List ---------------------------------------------------------------------------------


def test_list_shows_what_the_admin_page_needs_and_no_body(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Lah, Leh and Lor", status=LessonStatus.DRAFT)

    [row] = admin.get(URL).json()

    assert set(row) == {
        "id",
        "title",
        "summary",
        "topic_id",
        "status",
        "updated_at",
        "position",
        "level",
        "deletable",
        "has_unpublished_changes",
        "version",
        "cards",
        "questions",
        "cover_asset_id",
        "open_reports",
    }
    assert row["id"] == str(lesson.id)
    assert row["topic_id"] == str(topic.id)
    assert row["status"] == "draft"
    assert row["deletable"] is True
    assert row["version"] is None
    assert (row["cards"], row["questions"]) == (0, 0)


def test_list_counts_cards_and_questions_and_shows_the_latest_version(admin, db):
    lesson = _lesson(db, None, "Counted")
    lesson.draft = {
        "cards": [
            {
                "type": "story",
                "id": "a",
                "text": "One",
                "image": None,
                "audio": None,
                "question": None,
            },
            {
                "type": "story",
                "id": "b",
                "text": "Two",
                "image": None,
                "audio": None,
                "question": {
                    "type": "choice",
                    "id": "q",
                    "options": [],
                    "explanation": "",
                    "shuffle": True,
                },
            },
        ]
    }
    lesson.versions.append(
        LessonVersion(number=2, title="Counted", doc={"cards": []}, published_at=datetime.now(UTC))
    )
    db.commit()

    [row] = admin.get(URL).json()

    assert (row["cards"], row["questions"], row["version"]) == (2, 1, 2)


def test_list_marks_only_never_published_drafts_as_deletable(admin, db):
    draft = _lesson(db, None, "Draft", status=LessonStatus.DRAFT)
    published = _lesson(db, None, "Published", status=LessonStatus.PUBLISHED)
    withdrawn = _lesson(db, None, "Withdrawn", status=LessonStatus.WITHDRAWN)

    deletable = {row["title"]: row["deletable"] for row in admin.get(URL).json()}

    assert deletable == {draft.title: True, published.title: False, withdrawn.title: False}


def test_list_is_in_topic_order_then_lesson_order(admin, db):
    later_topic = _topic(db, "Workplace", position=1)
    first_topic = _topic(db, "Singlish", position=0)
    archived = _topic(db, "Festivals", position=2, archived=True)
    _lesson(db, later_topic, "W1", position=0)
    _lesson(db, first_topic, "S2", position=1)
    _lesson(db, first_topic, "S1", position=0)
    _lesson(db, None, "Loose", position=0)
    _lesson(db, archived, "F1", position=0, status=LessonStatus.WITHDRAWN)

    # Lessons with no topic come last; lessons in archived topics are still listed.
    assert _titles(admin) == ["S1", "S2", "W1", "F1", "Loose"]


def test_lessons_sharing_a_position_fall_back_to_creation_order(admin, db):
    topic = _topic(db, "Singlish")
    now = datetime.now(UTC)
    _lesson(db, topic, "Second", position=0, created_at=now)
    _lesson(db, topic, "First", position=0, created_at=now - timedelta(minutes=1))
    assert _titles(admin) == ["First", "Second"]


def test_list_is_empty_with_no_lessons(admin):
    assert admin.get(URL).json() == []


# --- Next position ------------------------------------------------------------------------


def test_next_lesson_position(db):
    topic = _topic(db, "Singlish")
    empty = _topic(db, "Workplace")
    _lesson(db, topic, "A", position=0)
    _lesson(db, topic, "B", position=4)
    _lesson(db, None, "Loose", position=2)

    assert next_lesson_position(db, topic.id) == 5
    assert next_lesson_position(db, empty.id) == 0
    assert next_lesson_position(db, None) == 3


def test_next_lesson_position_with_no_lessons_without_a_topic(db):
    assert next_lesson_position(db, None) == 0


# --- Reorder ------------------------------------------------------------------------------


def test_reorder_a_topics_lessons_of_every_status(admin, db):
    topic = _topic(db, "Singlish")
    other = _topic(db, "Workplace", position=1)
    a = _lesson(db, topic, "A", position=0, status=LessonStatus.PUBLISHED)
    b = _lesson(db, topic, "B", position=1, status=LessonStatus.DRAFT)
    c = _lesson(db, topic, "C", position=2, status=LessonStatus.WITHDRAWN)
    untouched = _lesson(db, other, "W", position=0)
    db.expire_all()
    updated_before = {lesson.id: db.get(Lesson, lesson.id).updated_at for lesson in (a, b, c)}

    response = _reorder(admin, topic, [c, a, b])

    assert response.status_code == 200
    assert [(row["title"], row["position"]) for row in response.json()] == [
        ("C", 0),
        ("A", 1),
        ("B", 2),
        ("W", 0),
    ]
    assert _titles(admin) == ["C", "A", "B", "W"]
    db.expire_all()
    assert db.get(Lesson, untouched.id).position == 0
    # SCRUM-66 AC3 sorts by "last updated"; moving a lesson must not count as an update.
    assert {i: db.get(Lesson, i).updated_at for i in updated_before} == updated_before


def test_reorder_lessons_with_no_topic(admin, db):
    topic = _topic(db, "Singlish")
    in_topic = _lesson(db, topic, "In topic", position=0)
    first = _lesson(db, None, "First", position=0)
    second = _lesson(db, None, "Second", position=1)

    response = _reorder(admin, None, [second, first])

    assert response.status_code == 200
    assert _titles(admin) == ["In topic", "Second", "First"]
    db.expire_all()
    assert db.get(Lesson, in_topic.id).position == 0


@pytest.mark.parametrize(
    "case", ["missing", "from another topic", "unknown", "duplicate", "no-topic lesson"]
)
def test_reorder_refuses_anything_but_the_current_lessons(admin, db, case):
    topic = _topic(db, "Singlish")
    other = _topic(db, "Workplace", position=1)
    a = _lesson(db, topic, "A", position=0)
    b = _lesson(db, topic, "B", position=1)
    elsewhere = _lesson(db, other, "W", position=0)
    loose = _lesson(db, None, "Loose", position=0)
    ids = {
        "missing": [a],
        "from another topic": [a, b, elsewhere],
        "unknown": [a, b, uuid.uuid4()],
        "duplicate": [a, b, b],
        "no-topic lesson": [a, b, loose],
    }[case]

    response = _reorder(admin, topic, ids)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_out_of_date"
    assert _titles(admin) == ["A", "B", "W", "Loose"]


def test_reorder_refuses_a_stale_list_after_a_lesson_was_added(admin, db):
    topic = _topic(db, "Singlish")
    a = _lesson(db, topic, "A", position=0)
    b = _lesson(db, topic, "B", position=1)
    _lesson(db, topic, "Added in another tab", position=2)

    response = _reorder(admin, topic, [b, a])

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_out_of_date"


def test_reorder_in_an_unknown_topic_is_not_found(admin):
    response = admin.put(
        ORDER_URL, json={"topic_id": str(uuid.uuid4()), "ids": [], "previous_ids": []}
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"


def test_reorder_of_an_empty_topic_accepts_an_empty_list(admin, db):
    topic = _topic(db, "Singlish")
    assert _reorder(admin, topic, []).status_code == 200


def test_reorder_needs_the_topic_id_even_when_it_is_null(admin, db):
    # Forgetting topic_id must not quietly mean "the lessons with no topic".
    loose = _lesson(db, None, "Loose")
    body = {"ids": [str(loose.id)], "previous_ids": [str(loose.id)]}
    assert admin.put(ORDER_URL, json=body).status_code == 422


def test_reorder_from_a_page_showing_an_older_order_is_refused(admin, db):
    # Same set of lessons, but another tab has reordered them since this page loaded.
    topic = _topic(db, "Singlish")
    a = _lesson(db, topic, "A", position=0)
    b = _lesson(db, topic, "B", position=1)
    shown = [str(a.id), str(b.id)]
    assert _reorder(admin, topic, [b, a], previous_ids=shown).status_code == 200

    response = _reorder(admin, topic, [b, a], previous_ids=shown)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_out_of_date"


# --- Access -------------------------------------------------------------------------------

ROUTES = [
    ("get", URL, None),
    ("put", ORDER_URL, {"topic_id": None, "ids": [], "previous_ids": []}),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_signed_out_requests_are_refused(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_a_normal_user_session_is_refused(learner, method, path, body):
    # As for every admin route: a user session gets the same 401 as no session at all.
    # The gateway let a main-app user through: admin routes still answer 401.
    response = learner.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"
