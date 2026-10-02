"""SCRUM-57: administrators create, rename, archive, restore and delete topics."""

import uuid
from datetime import UTC, datetime

import pytest

from app.models import Lesson, LessonStatus, Topic, UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
USER = {"email": "user@example.com", "password": "Password123"}
URL = "/api/admin/topics"


@pytest.fixture
def admin(client, make_user):
    """The test client, signed in to the admin portal."""
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 200
    return client


def _topic(db, name: str, archived: bool = False) -> Topic:
    topic = Topic(name=name, archived_at=datetime.now(UTC) if archived else None)
    db.add(topic)
    db.commit()
    return topic


def _lesson(db, topic: Topic, status: LessonStatus) -> Lesson:
    lesson = Lesson(title="A lesson", content="...", topic=topic, status=status)
    db.add(lesson)
    db.commit()
    return lesson


def _create(client, name: str):
    return client.post(URL, json={"name": name})


# --- Create -------------------------------------------------------------------------------


def test_create_a_topic(admin):
    response = _create(admin, "Singlish")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Singlish"
    assert body["archived_at"] is None
    assert (body["lesson_count"], body["published_count"]) == (0, 0)


def test_create_trims_whitespace(admin):
    assert _create(admin, "  Festivals \n").json()["name"] == "Festivals"


@pytest.mark.parametrize("name", ["", "   ", "x" * 81])
def test_create_refuses_a_name_that_is_empty_or_too_long(admin, name):
    assert _create(admin, name).status_code == 422


def test_create_refuses_a_duplicate_ignoring_case(admin):
    _create(admin, "Singlish")
    response = _create(admin, "SINGLISH")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "topic_name_taken"
    assert response.json()["detail"]["field"] == "name"


def test_an_archived_topic_still_reserves_its_name(admin, db):
    _topic(db, "Singlish", archived=True)
    assert _create(admin, "singlish").status_code == 409


# --- Rename -------------------------------------------------------------------------------


def test_rename_keeps_the_id(admin, db):
    topic = _topic(db, "Singlish")
    response = admin.patch(f"{URL}/{topic.id}", json={"name": " Singlish & Slang "})
    assert response.status_code == 200
    assert response.json()["id"] == str(topic.id)
    assert response.json()["name"] == "Singlish & Slang"


def test_rename_to_another_topics_name_is_refused(admin, db):
    _topic(db, "Singlish")
    other = _topic(db, "Workplace")
    response = admin.patch(f"{URL}/{other.id}", json={"name": "singlish"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "topic_name_taken"
    assert response.json()["detail"]["field"] == "name"


def test_rename_to_the_same_name_in_a_different_case_is_allowed(admin, db):
    topic = _topic(db, "singlish")
    response = admin.patch(f"{URL}/{topic.id}", json={"name": "Singlish"})
    assert response.status_code == 200
    assert response.json()["name"] == "Singlish"


def test_an_archived_topic_can_be_renamed(admin, db):
    topic = _topic(db, "Singlish", archived=True)
    response = admin.patch(f"{URL}/{topic.id}", json={"name": "Local slang"})
    assert response.status_code == 200
    assert response.json()["archived_at"] is not None


def test_rename_of_a_missing_topic_is_not_found(admin):
    response = admin.patch(f"{URL}/{uuid.uuid4()}", json={"name": "Anything"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"


# --- Archive and restore ------------------------------------------------------------------


def test_archive_twice(admin, db):
    topic = _topic(db, "Singlish")
    first = admin.post(f"{URL}/{topic.id}/archive")
    second = admin.post(f"{URL}/{topic.id}/archive")
    assert first.status_code == second.status_code == 200
    assert first.json()["archived_at"] is not None
    # The second call does not move the original archive date.
    assert second.json()["archived_at"] == first.json()["archived_at"]


def test_restore_twice(admin, db):
    topic = _topic(db, "Singlish", archived=True)
    first = admin.post(f"{URL}/{topic.id}/restore")
    second = admin.post(f"{URL}/{topic.id}/restore")
    assert first.status_code == second.status_code == 200
    assert first.json()["archived_at"] is None
    assert second.json()["archived_at"] is None


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_archive_and_restore_of_a_missing_topic_are_not_found(admin, action):
    response = admin.post(f"{URL}/{uuid.uuid4()}/{action}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"


# --- Delete -------------------------------------------------------------------------------


def test_delete_an_empty_topic(admin, db):
    topic = _topic(db, "Singlish")
    assert admin.delete(f"{URL}/{topic.id}").status_code == 204
    assert admin.get(URL).json() == []


@pytest.mark.parametrize("status", list(LessonStatus))
def test_delete_is_refused_when_the_topic_has_a_lesson(admin, db, status):
    topic = _topic(db, "Singlish")
    _lesson(db, topic, status)
    response = admin.delete(f"{URL}/{topic.id}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "topic_not_empty"
    assert "Archive" in response.json()["detail"]["message"]
    assert len(admin.get(URL).json()) == 1


def test_delete_of_a_missing_topic_is_not_found(admin):
    response = admin.delete(f"{URL}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "topic_not_found"


# --- List ---------------------------------------------------------------------------------


def test_list_counts_every_status_and_published_only(admin, db):
    busy = _topic(db, "Hawker & Food")
    for status in (
        LessonStatus.PUBLISHED,
        LessonStatus.PUBLISHED,
        LessonStatus.DRAFT,
        LessonStatus.WITHDRAWN,
    ):
        _lesson(db, busy, status)
    _topic(db, "Festivals")
    _topic(db, "Archived one", archived=True)

    rows = {row["name"]: row for row in admin.get(URL).json()}
    assert set(rows) == {"Hawker & Food", "Festivals", "Archived one"}
    assert (rows["Hawker & Food"]["lesson_count"], rows["Hawker & Food"]["published_count"]) == (
        4,
        2,
    )
    assert (rows["Festivals"]["lesson_count"], rows["Festivals"]["published_count"]) == (0, 0)
    assert rows["Archived one"]["archived_at"] is not None


# --- Access -------------------------------------------------------------------------------

ROUTES = [
    ("get", URL, None),
    ("post", URL, {"name": "X"}),
    ("patch", f"{URL}/{uuid.uuid4()}", {"name": "X"}),
    ("post", f"{URL}/{uuid.uuid4()}/archive", None),
    ("post", f"{URL}/{uuid.uuid4()}/restore", None),
    ("delete", f"{URL}/{uuid.uuid4()}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_signed_out_requests_are_refused(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_a_normal_user_session_is_refused(client, make_user, method, path, body):
    # The admin guard answers 401 to everyone but a signed-in admin, so it never reveals
    # which routes or accounts are admin ones.
    make_user(**USER)
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"
