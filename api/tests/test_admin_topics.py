"""SCRUM-57: administrators create, rename, archive, restore and delete topics.
SCRUM-86: and give them a description."""

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


def _topic(db, name: str, archived: bool = False, position: int = 0) -> Topic:
    topic = Topic(name=name, archived_at=datetime.now(UTC) if archived else None, position=position)
    db.add(topic)
    db.commit()
    return topic


def _lesson(db, topic: Topic, status: LessonStatus) -> Lesson:
    lesson = Lesson(title="A lesson", topic=topic, status=status)
    db.add(lesson)
    db.commit()
    return lesson


def _create(client, name: str, **fields):
    return client.post(URL, json={"name": name, **fields})


# --- Create -------------------------------------------------------------------------------


def test_create_a_topic(admin):
    response = _create(admin, "Singlish")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Singlish"
    assert body["description"] == ""
    assert body["archived_at"] is None
    assert (body["lesson_count"], body["published_count"]) == (0, 0)


def test_create_with_a_description(admin):
    response = _create(admin, "Singlish", description="  Words you will hear every day.\n")
    assert response.status_code == 201
    assert response.json()["description"] == "Words you will hear every day."


def test_a_description_of_200_characters_is_accepted(admin):
    assert _create(admin, "Singlish", description="x" * 200).status_code == 201


def test_a_description_over_200_characters_is_refused(admin):
    response = _create(admin, "Singlish", description="x" * 201)
    assert response.status_code == 422
    assert [error["loc"][-1] for error in response.json()["detail"]] == ["description"]


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


def test_editing_without_a_description_keeps_it(admin, db):
    topic = _topic(db, "Singlish")
    topic.description = "Words you will hear every day."
    db.commit()
    response = admin.patch(f"{URL}/{topic.id}", json={"name": "Local slang"})
    assert response.json()["description"] == "Words you will hear every day."


def test_edit_a_description(admin, db):
    topic = _topic(db, "Singlish")
    response = admin.patch(
        f"{URL}/{topic.id}", json={"name": "Singlish", "description": " Everyday words. "}
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Everyday words."
    db.refresh(topic)
    assert topic.description == "Everyday words."


def test_an_empty_description_clears_it(admin, db):
    topic = _topic(db, "Singlish")
    topic.description = "Words you will hear every day."
    db.commit()
    response = admin.patch(f"{URL}/{topic.id}", json={"name": "Singlish", "description": "  "})
    assert response.json()["description"] == ""


def test_an_archived_topics_description_can_be_edited(admin, db):
    topic = _topic(db, "Singlish", archived=True)
    response = admin.patch(
        f"{URL}/{topic.id}", json={"name": "Singlish", "description": "Everyday words."}
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Everyday words."


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


def test_list_is_in_position_order_then_creation_order(admin, db):
    _topic(db, "Workplace", position=1)
    _topic(db, "Singlish", position=0)
    _topic(db, "Festivals", position=1)  # same position: created later, so after Workplace
    rows = admin.get(URL).json()
    assert [(row["name"], row["position"]) for row in rows] == [
        ("Singlish", 0),
        ("Workplace", 1),
        ("Festivals", 1),
    ]


# --- Order (SCRUM-66) ---------------------------------------------------------------------

ORDER_URL = f"{URL}/order"


def _names(client) -> list[str]:
    return [row["name"] for row in client.get(URL).json()]


def _active_ids(client) -> list[str]:
    """The active topics in the order the admin page shows them."""
    return [row["id"] for row in client.get(URL).json() if row["archived_at"] is None]


def _reorder(client, ids: list, previous_ids: list | None = None):
    """Reorder as the page does: the new order, plus the order the page was showing."""
    return client.put(
        ORDER_URL,
        json={
            "ids": [str(i) for i in ids],
            "previous_ids": _active_ids(client) if previous_ids is None else previous_ids,
        },
    )


def test_a_new_topic_goes_to_the_end(admin, db):
    _topic(db, "Singlish", position=4)
    _topic(db, "Archived", archived=True, position=7)
    body = _create(admin, "Festivals").json()
    # After every position in use, archived topics included.
    assert body["position"] == 8
    assert _names(admin)[-1] == "Festivals"


def test_the_first_topic_starts_at_zero(admin):
    assert _create(admin, "Singlish").json()["position"] == 0


def test_a_restored_topic_goes_to_the_end(admin, db):
    archived = _topic(db, "Festivals", archived=True, position=0)
    _topic(db, "Singlish", position=1)
    _topic(db, "Workplace", position=2)
    _topic(db, "Other archived", archived=True, position=5)

    body = admin.post(f"{URL}/{archived.id}/restore").json()
    assert body["position"] == 6
    active = [row["name"] for row in admin.get(URL).json() if row["archived_at"] is None]
    assert active == ["Singlish", "Workplace", "Festivals"]


def test_restoring_an_active_topic_keeps_its_position(admin, db):
    topic = _topic(db, "Singlish", position=0)
    _topic(db, "Workplace", position=1)
    assert admin.post(f"{URL}/{topic.id}/restore").json()["position"] == 0


def test_reorder_topics(admin, db):
    singlish = _topic(db, "Singlish", position=0)
    workplace = _topic(db, "Workplace", position=1)
    festivals = _topic(db, "Festivals", position=2)
    updated_before = {t.id: t.updated_at for t in (singlish, workplace, festivals)}

    ids = [festivals.id, singlish.id, workplace.id]
    response = _reorder(admin, ids)

    assert response.status_code == 200
    assert [(row["name"], row["position"]) for row in response.json()] == [
        ("Festivals", 0),
        ("Singlish", 1),
        ("Workplace", 2),
    ]
    # The order is saved, not just echoed back.
    assert _names(admin) == ["Festivals", "Singlish", "Workplace"]
    # Moving a topic is not editing it.
    db.expire_all()
    assert {i: db.get(Topic, i).updated_at for i in ids} == updated_before


def test_reorder_ignores_archived_topics_and_keeps_their_position(admin, db):
    singlish = _topic(db, "Singlish", position=0)
    workplace = _topic(db, "Workplace", position=1)
    archived = _topic(db, "Archived", archived=True, position=2)

    response = _reorder(admin, [workplace.id, singlish.id])

    assert response.status_code == 200
    rows = {row["name"]: row["position"] for row in response.json()}
    assert rows == {"Workplace": 0, "Singlish": 1, "Archived": 2}
    db.refresh(archived)
    assert archived.position == 2


@pytest.mark.parametrize(
    "case", ["missing", "extra unknown", "archived included", "duplicate", "empty"]
)
def test_reorder_refuses_anything_but_the_current_active_topics(admin, db, case):
    singlish = _topic(db, "Singlish", position=0)
    workplace = _topic(db, "Workplace", position=1)
    archived = _topic(db, "Archived", archived=True, position=2)
    ids = {
        "missing": [singlish.id],
        "extra unknown": [singlish.id, workplace.id, uuid.uuid4()],
        "archived included": [singlish.id, workplace.id, archived.id],
        "duplicate": [singlish.id, workplace.id, workplace.id],
        "empty": [],
    }[case]

    response = _reorder(admin, ids)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_out_of_date"
    # Nothing moved.
    assert _names(admin) == ["Singlish", "Workplace", "Archived"]


def test_reorder_with_no_active_topics_accepts_an_empty_list(admin, db):
    _topic(db, "Archived", archived=True)
    response = _reorder(admin, [])
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Archived"]


def test_reorder_refuses_a_malformed_body(admin):
    assert admin.put(ORDER_URL, json={"ids": ["x"], "previous_ids": []}).status_code == 422
    assert admin.put(ORDER_URL, json={"ids": []}).status_code == 422  # previous_ids missing
    assert admin.put(ORDER_URL, json={}).status_code == 422


def test_reorder_from_a_page_showing_an_older_order_is_refused(admin, db):
    # Two tabs show A, B, C. Tab 1 saves C, A, B. Tab 2, still showing A, B, C, then saves
    # B, A, C: the same set of topics, but saving it would silently undo tab 1's change.
    a = _topic(db, "A", position=0)
    b = _topic(db, "B", position=1)
    c = _topic(db, "C", position=2)
    shown = [str(a.id), str(b.id), str(c.id)]
    assert _reorder(admin, [c.id, a.id, b.id], previous_ids=shown).status_code == 200

    response = _reorder(admin, [b.id, a.id, c.id], previous_ids=shown)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "order_out_of_date"
    assert _names(admin) == ["C", "A", "B"]


# --- Access -------------------------------------------------------------------------------

ROUTES = [
    ("put", ORDER_URL, {"ids": [], "previous_ids": []}),
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
