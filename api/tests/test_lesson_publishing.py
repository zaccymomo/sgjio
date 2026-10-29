"""SCRUM-52, SCRUM-56, SCRUM-70: publishing a lesson as a version, editing it while it is
live, withdrawing and restoring it."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import Lesson, LessonCompletion, LessonVersion, Topic, UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
USER = {"email": "user@example.com", "password": "Password123"}
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


def _create(client, topic: Topic | None, title="Ordering kopi", doc=READY_DOC) -> dict:
    body = {"title": title, "doc": doc, "topic_id": str(topic.id) if topic else None}
    response = client.post(URL, json=body)
    assert response.status_code == 201
    return response.json()


def _act(client, lesson: dict, action: str, updated_at: str | None = None):
    return client.post(
        f"{URL}/{lesson['id']}/{action}",
        json={"updated_at": updated_at or lesson["updated_at"]},
    )


def _ok(client, lesson: dict, action: str) -> dict:
    response = _act(client, lesson, action)
    assert response.status_code == 200, response.json()
    return response.json()


def _save(client, lesson: dict, **changes) -> dict:
    response = client.patch(
        f"{URL}/{lesson['id']}", json={"updated_at": lesson["updated_at"], **changes}
    )
    assert response.status_code == 200, response.json()
    return response.json()


def _versions(db, lesson: dict) -> list[LessonVersion]:
    db.expire_all()
    return list(
        db.scalars(
            select(LessonVersion)
            .where(LessonVersion.lesson_id == lesson["id"])
            .order_by(LessonVersion.number)
        )
    )


def _progress(client) -> dict:
    assert client.post("/api/auth/sign-in", json=USER).status_code == 200
    return client.get("/api/progress").json()


# --- Publishing ---------------------------------------------------------------------------


def test_publish_makes_version_one(admin, db, topic):
    lesson = _create(admin, topic)

    body = _ok(admin, lesson, "publish")

    assert body["status"] == "published"
    assert body["version"]["number"] == 1
    assert body["published_at"] is not None
    assert body["has_unpublished_changes"] is False
    assert body["deletable"] is False
    [version] = _versions(db, lesson)
    assert version.title == "Ordering kopi"
    assert version.doc == body["doc"]
    assert version.published_by is not None


def test_publish_is_refused_with_the_issues_that_block_it(admin, db):
    lesson = _create(admin, None, title="", doc={"cards": [{"text": "A {{blank}}"}]})

    response = _act(admin, lesson, "publish")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "lesson_has_blockers"
    codes = [issue["code"] for issue in detail["issues"]]
    assert codes == ["missing_title", "missing_topic", "no_questions", "blank_without_question"]
    assert all(issue["severity"] == "blocker" for issue in detail["issues"])
    assert _versions(db, lesson) == []
    assert admin.get(f"{URL}/{lesson['id']}").json()["status"] == "draft"


def test_warnings_do_not_block_publishing(admin, topic):
    long_text = "word " * 60
    doc = {"cards": [{"text": long_text}, *READY_DOC["cards"]]}
    lesson = _create(admin, topic, doc=doc)
    assert [issue["code"] for issue in lesson["issues"]] == ["card_text_long"]

    assert _ok(admin, lesson, "publish")["status"] == "published"


def test_a_lesson_whose_only_question_is_a_tap_cannot_be_published(admin, topic):
    doc = {
        "cards": [
            {
                "text": "Say it with me: {{blank}}!",
                "question": {"options": [{"text": "Shiok"}], "explanation": "Delicious."},
            }
        ]
    }
    lesson = _create(admin, topic, doc=doc)
    assert [issue["code"] for issue in lesson["issues"]] == ["no_scored_question"]
    assert lesson["stats"]["scored_questions"] == 0

    response = _act(admin, lesson, "publish")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_has_blockers"


def test_publishing_again_after_edits_makes_a_new_version(admin, db, topic):
    lesson = _ok(admin, _create(admin, topic), "publish")
    edited = _save(admin, lesson, title="Ordering kopi like a local")
    assert edited["has_unpublished_changes"] is True

    body = _ok(admin, edited, "publish")

    assert body["version"]["number"] == 2
    assert body["has_unpublished_changes"] is False
    assert [v.title for v in _versions(db, lesson)] == [
        "Ordering kopi",
        "Ordering kopi like a local",
    ]


def test_publishing_with_nothing_new_changes_nothing(admin, db, topic):
    lesson = _ok(admin, _create(admin, topic), "publish")

    body = _ok(admin, lesson, "publish")

    assert body["version"]["number"] == 1
    assert body["updated_at"] == lesson["updated_at"]
    assert len(_versions(db, lesson)) == 1


def test_publish_from_an_out_of_date_editor_is_refused(admin, topic):
    lesson = _create(admin, topic)
    _save(admin, lesson, title="Changed elsewhere")

    response = _act(admin, lesson, "publish")

    assert response.json()["detail"]["code"] == "lesson_out_of_date"


def test_publishing_counts_toward_users_progress(admin, db, topic, make_user):
    make_user(**USER)
    lesson = _create(admin, topic)
    assert _progress(admin)["available"] == 0

    _ok(admin, lesson, "publish")

    assert _progress(admin)["available"] == 1


# --- Discarding changes -------------------------------------------------------------------


def test_discard_puts_the_draft_back_to_the_latest_version(admin, topic):
    lesson = _ok(admin, _create(admin, topic), "publish")
    edited = _save(admin, lesson, title="Changed", summary="New", doc={"cards": []})

    body = _ok(admin, edited, "discard")

    assert body["title"] == "Ordering kopi"
    assert body["summary"] == ""
    assert body["doc"] == lesson["doc"]
    assert body["has_unpublished_changes"] is False


def test_discard_needs_a_published_version(admin, topic):
    lesson = _create(admin, topic)

    response = _act(admin, lesson, "discard")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_status_conflict"


# --- Withdrawing and restoring (SCRUM-52 AC3-AC5) -------------------------------------------


def test_withdraw_hides_the_lesson_and_keeps_completions(admin, db, topic, make_user):
    user = make_user(**USER)
    lesson = _ok(admin, _create(admin, topic), "publish")
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson["id"], best_correct=1, best_scored=1))
    db.commit()
    assert _progress(admin)["completed"] == 1

    body = _ok(admin, lesson, "withdraw")

    assert body["status"] == "withdrawn"
    assert body["withdrawn_at"] is not None
    assert _progress(admin)["available"] == 0
    db.expire_all()
    assert db.query(LessonCompletion).count() == 1


def test_restore_brings_back_the_latest_version_and_keeps_draft_changes(admin, db, topic):
    lesson = _ok(admin, _create(admin, topic), "publish")
    withdrawn = _ok(admin, lesson, "withdraw")
    edited = _save(admin, withdrawn, title="Edited while withdrawn")

    body = _ok(admin, edited, "restore")

    assert body["status"] == "published"
    assert body["version"]["number"] == 1
    assert body["title"] == "Edited while withdrawn"
    assert body["has_unpublished_changes"] is True


def test_publishing_a_withdrawn_lesson_with_no_changes_restores_it(admin, db, topic):
    lesson = _ok(admin, _ok(admin, _create(admin, topic), "publish"), "withdraw")

    body = _ok(admin, lesson, "publish")

    assert body["status"] == "published"
    assert len(_versions(db, lesson)) == 1


@pytest.mark.parametrize(
    ("action", "status_needed"), [("withdraw", "published"), ("restore", "withdrawn")]
)
def test_withdraw_and_restore_need_the_right_status(admin, topic, action, status_needed):
    draft = _create(admin, topic)

    response = _act(admin, draft, action)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "lesson_status_conflict"


def test_withdrawn_lessons_stay_in_the_admin_list(admin, topic):
    lesson = _ok(admin, _ok(admin, _create(admin, topic), "publish"), "withdraw")

    [row] = admin.get(URL).json()

    assert row["id"] == lesson["id"]
    assert row["status"] == "withdrawn"
    assert row["version"] == 1


def test_versions_are_kept_when_a_topic_is_archived(admin, db, topic):
    lesson = _ok(admin, _create(admin, topic), "publish")
    topic.archived_at = datetime.now(UTC)
    db.commit()

    body = admin.get(f"{URL}/{lesson['id']}").json()

    assert body["version"]["number"] == 1
    assert [issue["code"] for issue in body["issues"]] == ["topic_archived"]
    assert db.get(Lesson, lesson["id"]) is not None
