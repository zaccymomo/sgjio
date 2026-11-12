"""SCRUM-19 and SCRUM-64: writing a lesson as a deck of cards, saved as a draft."""

import uuid
from datetime import UTC, datetime

import pytest

from app.lesson_doc import MAX_CARD_TEXT, MAX_OPTIONS
from app.models import Lesson, LessonStatus, LessonVersion, Topic
from app.schemas import MAX_LESSON_SUMMARY, MAX_LESSON_TITLE
from tests.conftest import outbox_events

URL = "/api/admin/lessons"


def _topic(db, name: str, position: int = 0, archived: bool = False) -> Topic:
    topic = Topic(name=name, position=position, archived_at=datetime.now(UTC) if archived else None)
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db,
    topic: Topic | None,
    title: str = "Lesson",
    position: int = 0,
    status: LessonStatus = LessonStatus.DRAFT,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, status=status, position=position)
    if status != LessonStatus.DRAFT:
        lesson.published_at = datetime.now(UTC)
        lesson.versions.append(
            LessonVersion(number=1, title=title, doc={"cards": []}, published_at=datetime.now(UTC))
        )
    db.add(lesson)
    db.commit()
    return lesson


def _card(text: str = "Some text", **extra) -> dict:
    return {"text": text, **extra}


def _question_card(text: str = "Kopi {{blank}}", options=None, **question) -> dict:
    options = options or [{"text": "O", "correct": True}, {"text": "C"}]
    return {
        "text": text,
        "question": {"options": options, "explanation": "Because.", **question},
    }


def _url(lesson) -> str:
    return f"{URL}/{getattr(lesson, 'id', lesson)}"


def _loaded(client, lesson) -> dict:
    """The lesson as the editor loads it."""
    response = client.get(_url(lesson))
    assert response.status_code == 200
    return response.json()


def _save(client, lesson, updated_at: str | None = None, **changes):
    """Save as the editor does, naming the "last updated" time it loaded."""
    if updated_at is None:
        updated_at = _loaded(client, lesson)["updated_at"]
    return client.patch(_url(lesson), json={"updated_at": updated_at, **changes})


def _delete(client, lesson, updated_at: str | None = None):
    if updated_at is None:
        updated_at = _loaded(client, lesson)["updated_at"]
    return client.delete(_url(lesson), params={"updated_at": updated_at})


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _group_titles(client, topic: Topic | None) -> list[str]:
    """One topic's lessons in the order the admin page shows them."""
    topic_id = str(topic.id) if topic else None
    return [row["title"] for row in client.get(URL).json() if row["topic_id"] == topic_id]


# --- Get ----------------------------------------------------------------------------------


def test_get_returns_the_draft_with_everything_the_editor_needs(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Lah, Leh and Lor")

    body = _loaded(admin, lesson)

    assert set(body) == {
        "id",
        "key",
        "title",
        "summary",
        "topic_id",
        "status",
        "published_at",
        "withdrawn_at",
        "position",
        "level",
        "created_at",
        "updated_at",
        "deletable",
        "has_unpublished_changes",
        "version",
        "origin",
        "ai_reviewed_at",
        "doc",
        "issues",
        "stats",
        "assets",
    }
    assert body["title"] == "Lah, Leh and Lor"
    assert body["origin"] == "authored"
    assert body["ai_reviewed_at"] is None
    assert body["doc"] == {"cards": []}
    assert body["topic_id"] == str(topic.id)
    assert body["status"] == "draft"
    assert body["deletable"] is True
    assert body["version"] is None
    assert body["assets"] == {}
    assert [issue["code"] for issue in body["issues"]] == ["no_cards"]


def test_get_works_for_every_status(admin, db):
    for status in LessonStatus:
        lesson = _lesson(db, None, status=status)
        assert _loaded(admin, lesson)["status"] == status.value


def test_get_an_unknown_lesson_is_not_found(admin):
    response = admin.get(_url(uuid.uuid4()))
    assert response.status_code == 404
    assert _code(response) == "lesson_not_found"


# --- Create -------------------------------------------------------------------------------


def test_create_an_empty_draft(admin, db):
    response = admin.post(URL, json={"level": 1})

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == ""
    assert body["summary"] == ""
    assert body["doc"] == {"cards": []}
    assert body["topic_id"] is None
    assert body["status"] == "draft"
    assert body["published_at"] is None
    assert body["deletable"] is True
    assert db.get(Lesson, uuid.UUID(body["id"])) is not None


def test_create_a_whole_lesson_in_one_request(admin, db):
    topic = _topic(db, "Hawker & Food")

    response = admin.post(
        URL,
        json={
            "level": 2,
            "title": "  Ordering kopi  ",
            "summary": " Coffee in code ",
            "topic_id": str(topic.id),
            "doc": {"cards": [_card("**Kopi** is coffee."), _question_card()]},
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Ordering kopi"  # trimmed
    assert body["summary"] == "Coffee in code"
    [story, quiz] = body["doc"]["cards"]
    assert story["text"] == "**Kopi** is coffee."  # kept exactly as written
    assert story["type"] == "story"
    assert quiz["question"]["type"] == "choice"
    assert quiz["question"]["shuffle"] is True
    assert [o["correct"] for o in quiz["question"]["options"]] == [True, False]
    # Every card, question and option gets an id.
    ids = [story["id"], quiz["id"], quiz["question"]["id"]]
    ids += [o["id"] for o in quiz["question"]["options"]]
    assert all(ids) and len(set(ids)) == len(ids)
    assert body["issues"] == []
    assert body["stats"]["cards"] == 2
    assert body["stats"]["questions"] == 1
    assert body["stats"]["scored_questions"] == 1


def test_ids_sent_by_the_editor_are_kept(admin):
    card = {"id": "card-1", **_question_card()}
    card["question"]["id"] = "q-1"
    card["question"]["options"][0]["id"] = "opt-1"

    body = admin.post(URL, json={"level": 1, "doc": {"cards": [card]}}).json()

    [saved] = body["doc"]["cards"]
    assert saved["id"] == "card-1"
    assert saved["question"]["id"] == "q-1"
    assert saved["question"]["options"][0]["id"] == "opt-1"
    assert saved["question"]["options"][1]["id"]  # filled in


def test_a_repeated_id_is_refused(admin, db):
    response = admin.post(
        URL, json={"level": 1, "doc": {"cards": [_card(id="same"), _card(id="same")]}}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "doc"]
    assert "same" in response.json()["detail"][0]["msg"]
    assert db.query(Lesson).count() == 0


def test_create_puts_the_draft_at_the_end_of_its_topic(admin, db):
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "First", position=0)
    _lesson(db, topic, "Second", position=5)

    admin.post(URL, json={"level": 1, "title": "New", "topic_id": str(topic.id)})

    assert _group_titles(admin, topic) == ["First", "Second", "New"]


def test_create_without_a_topic_goes_at_the_end_of_lessons_with_no_topic(admin, db):
    _lesson(db, None, "Loose", position=3)

    admin.post(URL, json={"level": 1, "title": "New"})

    assert _group_titles(admin, None) == ["Loose", "New"]


def test_create_in_an_unknown_topic_is_refused(admin, db):
    response = admin.post(URL, json={"level": 1, "topic_id": str(uuid.uuid4())})

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "topic_not_found",
        "message": "That topic does not exist.",
        "field": "topic_id",
    }
    assert db.query(Lesson).count() == 0


def test_create_in_an_archived_topic_is_refused(admin, db):
    topic = _topic(db, "Old", archived=True)

    response = admin.post(URL, json={"level": 1, "topic_id": str(topic.id)})

    assert response.status_code == 409
    assert _code(response) == "topic_archived"
    assert response.json()["detail"]["field"] == "topic_id"


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x" * (MAX_LESSON_TITLE + 1)},
        {"summary": "x" * (MAX_LESSON_SUMMARY + 1)},
        {"title": None},
        {"topic_id": "not-an-id"},
        {"doc": {"cards": [_card("x" * (MAX_CARD_TEXT + 1))]}},
        {"doc": {"cards": [_card(colour="red")]}},  # unknown fields are typos, not ignored
        {"doc": {"cards": [{"type": "comic", "text": "Not yet"}]}},
        {"doc": {"cards": [_question_card(options=[{"text": "x"}] * (MAX_OPTIONS + 1))]}},
        {"doc": {"cards": [_card(id="has spaces")]}},
        {"doc": {"cards": [_card(image={"asset_id": str(uuid.uuid4())})]}},  # no such image
    ],
)
def test_create_refuses_malformed_lessons(admin, db, body):
    response = admin.post(URL, json={"level": 1, **body})
    assert response.status_code == 422
    assert db.query(Lesson).count() == 0


def test_limits_are_accepted_up_to_the_limit(admin):
    response = admin.post(
        URL,
        json={
            "level": 5,
            "title": f"  {'x' * MAX_LESSON_TITLE}  ",
            "summary": "x" * MAX_LESSON_SUMMARY,
            "doc": {
                "cards": [
                    _card("x" * MAX_CARD_TEXT),
                    _question_card(options=[{"text": "x"}] * MAX_OPTIONS),
                ]
            },
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "x" * MAX_LESSON_TITLE


# --- Edit ---------------------------------------------------------------------------------


def test_edit_a_draft(admin, db):
    lesson = _lesson(db, None, "Old title")
    before = _loaded(admin, lesson)

    response = _save(
        admin, lesson, title="New title", summary="About", doc={"cards": [_card("New card")]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["summary"] == "About"
    assert [card["text"] for card in body["doc"]["cards"]] == ["New card"]
    assert body["updated_at"] > before["updated_at"]
    assert body["has_unpublished_changes"] is False  # never published: nothing to compare


def test_saving_empty_fields_is_allowed(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Title")

    response = _save(admin, lesson, title="", doc={"cards": [_card(""), {"question": {}}]})

    assert response.status_code == 200
    assert response.json()["title"] == ""
    codes = {issue["code"] for issue in response.json()["issues"]}
    assert {"missing_title", "card_text_missing", "question_no_options"} <= codes


def test_fields_left_out_are_kept(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Title")
    _save(admin, lesson, doc={"cards": [_card("Kept")]})

    body = _save(admin, lesson, summary="Only the summary").json()

    assert body["title"] == "Title"
    assert body["topic_id"] == str(topic.id)
    assert [card["text"] for card in body["doc"]["cards"]] == ["Kept"]


def test_a_save_that_changes_nothing_keeps_last_updated(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Title")
    before = _save(admin, lesson, doc={"cards": [_question_card()]}).json()

    response = _save(
        admin,
        lesson,
        before["updated_at"],
        title=before["title"],
        summary=before["summary"],
        topic_id=before["topic_id"],
        doc=before["doc"],
    )

    assert response.status_code == 200
    assert response.json()["updated_at"] == before["updated_at"]
    assert response.json()["position"] == before["position"]


def test_editing_a_published_lesson_changes_only_its_draft(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Live", status=LessonStatus.PUBLISHED)

    body = _save(admin, lesson, title="Edited", doc={"cards": [_card("New")]}).json()

    assert body["status"] == "published"
    assert body["has_unpublished_changes"] is True
    db.expire_all()
    [version] = db.get(Lesson, lesson.id).versions
    assert (version.title, version.doc) == ("Live", {"cards": []})


def test_changing_a_draft_back_clears_unpublished_changes(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Live", status=LessonStatus.PUBLISHED)
    assert _save(admin, lesson, title="Edited").json()["has_unpublished_changes"] is True

    assert _save(admin, lesson, title="Live").json()["has_unpublished_changes"] is False


def test_changing_topic_moves_the_lesson_to_the_end_of_the_new_topic(admin, db):
    old, new = _topic(db, "Old", position=0), _topic(db, "New", position=1)
    _lesson(db, old, "Stays 1", position=0)
    moving = _lesson(db, old, "Moving", position=1)
    _lesson(db, old, "Stays 2", position=2)
    _lesson(db, new, "Already there", position=7)

    response = _save(admin, moving, topic_id=str(new.id))

    assert response.status_code == 200
    assert response.json()["position"] == 8
    assert _group_titles(admin, new) == ["Already there", "Moving"]
    # The topic it left keeps its order and its positions.
    assert _group_titles(admin, old) == ["Stays 1", "Stays 2"]
    positions = {row["title"]: row["position"] for row in admin.get(URL).json()}
    assert positions["Stays 1"] == 0
    assert positions["Stays 2"] == 2


def test_moving_a_published_lesson_takes_effect_straight_away(admin, db):
    old, new = _topic(db, "Old", position=0), _topic(db, "New", position=1)
    lesson = _lesson(db, old, "Live", status=LessonStatus.PUBLISHED)

    body = _save(admin, lesson, topic_id=str(new.id)).json()

    assert body["topic_id"] == str(new.id)
    # Where a lesson sits is not part of its content, so there is nothing to publish.
    assert body["has_unpublished_changes"] is False


def test_a_published_lesson_keeps_a_topic(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic, "Live", status=LessonStatus.WITHDRAWN)

    response = _save(admin, lesson, topic_id=None)

    assert (response.status_code, _code(response)) == (409, "topic_required")
    assert _loaded(admin, lesson)["topic_id"] == str(topic.id)


def test_removing_the_topic_moves_the_lesson_to_the_end_of_lessons_with_no_topic(admin, db):
    topic = _topic(db, "Singlish")
    _lesson(db, None, "Loose", position=4)
    lesson = _lesson(db, topic, "Moving")

    body = _save(admin, lesson, topic_id=None).json()

    assert body["topic_id"] is None
    assert _group_titles(admin, None) == ["Loose", "Moving"]


def test_moving_into_an_unknown_or_archived_topic_is_refused(admin, db):
    topic = _topic(db, "Singlish")
    archived = _topic(db, "Old", archived=True)
    lesson = _lesson(db, topic, "Title")

    unknown = _save(admin, lesson, topic_id=str(uuid.uuid4()))
    into_archived = _save(admin, lesson, topic_id=str(archived.id), title="Changed")

    assert (unknown.status_code, _code(unknown)) == (404, "topic_not_found")
    assert unknown.json()["detail"]["field"] == "topic_id"
    assert (into_archived.status_code, _code(into_archived)) == (409, "topic_archived")
    # Nothing in a refused save is kept.
    assert _loaded(admin, lesson)["title"] == "Title"
    assert _loaded(admin, lesson)["topic_id"] == str(topic.id)


def test_a_lesson_already_in_an_archived_topic_keeps_saving(admin, db):
    archived = _topic(db, "Old", archived=True)
    lesson = _lesson(db, archived, "Title")

    response = _save(admin, lesson, title="Edited", topic_id=str(archived.id))

    assert response.status_code == 200
    assert response.json()["topic_id"] == str(archived.id)
    assert "topic_archived" in {issue["code"] for issue in response.json()["issues"]}


def test_a_malformed_save_keeps_nothing(admin, db):
    lesson = _lesson(db, None, "Title")

    response = _save(admin, lesson, title="Changed", doc={"cards": [_card(id="a"), _card(id="a")]})

    assert response.status_code == 422
    assert _loaded(admin, lesson)["title"] == "Title"


def test_a_save_from_an_out_of_date_editor_is_refused(admin, db):
    lesson = _lesson(db, None, "Title")
    first_tab = _loaded(admin, lesson)["updated_at"]
    assert _save(admin, lesson, first_tab, title="Saved in another tab").status_code == 200

    response = _save(admin, lesson, first_tab, title="Would overwrite it")

    assert response.status_code == 409
    assert _code(response) == "lesson_out_of_date"
    assert _loaded(admin, lesson)["title"] == "Saved in another tab"


def test_reordering_does_not_make_an_open_editor_out_of_date(admin, db):
    topic = _topic(db, "Singlish")
    a, b = _lesson(db, topic, "A", position=0), _lesson(db, topic, "B", position=1)
    loaded = _loaded(admin, a)["updated_at"]
    admin.put(
        f"{URL}/order",
        json={
            "topic_id": str(topic.id),
            "ids": [str(b.id), str(a.id)],
            "previous_ids": [str(a.id), str(b.id)],
        },
    )

    assert _save(admin, a, loaded, title="Edited").status_code == 200


def test_a_save_needs_the_last_updated_time(admin, db):
    lesson = _lesson(db, None)

    missing = admin.patch(_url(lesson), json={"title": "x"})
    without_time_zone = admin.patch(
        _url(lesson), json={"title": "x", "updated_at": "2026-01-01T00:00:00"}
    )

    assert missing.status_code == 422
    assert without_time_zone.status_code == 422


def test_edit_an_unknown_lesson_is_not_found(admin):
    response = _save(admin, uuid.uuid4(), "2026-01-01T00:00:00Z", title="x")
    assert response.status_code == 404
    assert _code(response) == "lesson_not_found"


# --- Delete -------------------------------------------------------------------------------


def test_delete_a_draft_with_its_cards(admin, db):
    lesson = _lesson(db, None)
    _save(admin, lesson, doc={"cards": [_question_card()]})
    lesson_id = lesson.id

    response = _delete(admin, lesson)

    assert response.status_code == 204
    db.expire_all()
    assert db.get(Lesson, lesson_id) is None
    assert admin.get(_url(lesson_id)).status_code == 404


@pytest.mark.parametrize("status", [LessonStatus.PUBLISHED, LessonStatus.WITHDRAWN])
def test_a_lesson_that_was_ever_published_cannot_be_deleted(admin, db, status):
    lesson = _lesson(db, None, status=status)
    assert _loaded(admin, lesson)["deletable"] is False

    response = _delete(admin, lesson)

    assert response.status_code == 409
    assert _code(response) == "lesson_not_deletable"
    assert admin.get(_url(lesson)).status_code == 200


def test_delete_from_an_out_of_date_editor_is_refused(admin, db):
    lesson = _lesson(db, None, "Title")
    loaded = _loaded(admin, lesson)["updated_at"]
    _save(admin, lesson, loaded, title="Edited elsewhere")

    response = _delete(admin, lesson, loaded)

    assert response.status_code == 409
    assert _code(response) == "lesson_out_of_date"
    assert admin.get(_url(lesson)).status_code == 200


def test_delete_an_unknown_lesson_is_not_found(admin):
    response = _delete(admin, uuid.uuid4(), "2026-01-01T00:00:00Z")
    assert response.status_code == 404
    assert _code(response) == "lesson_not_found"


def test_delete_needs_the_last_updated_time(admin, db):
    lesson = _lesson(db, None)
    assert admin.delete(_url(lesson)).status_code == 422


def test_deleting_a_topics_only_lesson_lets_the_topic_be_deleted(admin, db):
    topic = _topic(db, "Singlish")
    lesson = _lesson(db, topic)
    assert admin.delete(f"/api/admin/topics/{topic.id}").status_code == 409

    _delete(admin, lesson)

    assert admin.delete(f"/api/admin/topics/{topic.id}").status_code == 204


# --- Users never see drafts (SCRUM-64 AC5) -------------------------------------------------


def test_a_new_draft_changes_nobodys_progress(admin, db):
    # Learners' progress lives in Learning, which hears of lessons only through events: a
    # draft that was never published is never announced (and its edits never are either).
    topic = _topic(db, "Singlish")
    _lesson(db, topic, "Published", status=LessonStatus.PUBLISHED)
    before = len(outbox_events())

    draft = admin.post(URL, json={"level": 1, "title": "Draft", "topic_id": str(topic.id)}).json()
    _save(admin, draft["id"], doc={"cards": [_card("Still a draft")]})
    # A draft in a topic with no published lessons must not add a circle either.
    other = _topic(db, "Hawker", position=1)
    admin.post(URL, json={"level": 1, "title": "Draft", "topic_id": str(other.id)})

    assert outbox_events("content.lesson", since=before) == []


# --- Access -------------------------------------------------------------------------------

SOME_ID = "00000000-0000-0000-0000-000000000001"
STAMP = {"updated_at": "2026-01-01T00:00:00Z"}
ROUTES = [
    ("post", URL, {}),
    ("get", f"{URL}/{SOME_ID}", None),
    ("patch", f"{URL}/{SOME_ID}", STAMP),
    ("delete", f"{URL}/{SOME_ID}?updated_at=2026-01-01T00:00:00Z", None),
    ("post", f"{URL}/{SOME_ID}/publish", STAMP),
    ("post", f"{URL}/{SOME_ID}/discard", STAMP),
    ("post", f"{URL}/{SOME_ID}/withdraw", STAMP),
    ("post", f"{URL}/{SOME_ID}/restore", STAMP),
]


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_signed_out_requests_are_refused(client, method, path, body):
    response = client.request(method, path, json=body)
    assert response.status_code == 401
    assert _code(response) == "not_signed_in"


@pytest.mark.parametrize(("method", "path", "body"), ROUTES)
def test_a_normal_user_session_is_refused(learner, method, path, body):
    # As for every admin route: a user session gets the same 401 as no session at all.
    # The gateway let a main-app user through: admin routes still answer 401.
    response = learner.request(method, path, json=body)
    assert response.status_code == 401
    assert _code(response) == "not_signed_in"
