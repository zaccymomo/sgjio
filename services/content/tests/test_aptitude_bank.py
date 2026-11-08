"""SCRUM-96: authoring the per-topic aptitude question bank, and whether the aptitude test is
ready (the bank part of the monolith's test_aptitude.py; the quiz itself is Learning's)."""

from sqlalchemy import select

from app.aptitude import NOT_SURE_OPTION
from app.models import AptitudeQuestion, Topic
from app.seed import TOPICS, seed

URL = "/api/admin/aptitude-questions"


def _topic(db) -> Topic:
    topic = Topic(name="Test topic")
    db.add(topic)
    db.commit()
    return topic


def test_seeded_bank_is_ready_for_every_topic_and_level(admin, db):
    seed(db)

    response = admin.get(URL)
    assert response.status_code == 200
    bank = response.json()
    assert bank["ready"] is True
    assert {topic["topic_name"] for topic in bank["topics"]} == set(TOPICS)
    assert all(
        topic["ready"] and all(topic["counts_by_level"][str(level)] >= 1 for level in range(1, 6))
        for topic in bank["topics"]
    )
    assert len(bank["questions"]) >= len(TOPICS) * 5


def test_admin_can_create_and_edit_question_but_not_its_level(admin, db):
    topic = _topic(db)
    body = {
        "topic_id": str(topic.id),
        "level": 2,
        "prompt": "What should happen?",
        "options": [
            {"id": "a", "text": "This", "correct": True},
            {"id": "b", "text": "That", "correct": False},
        ],
        "is_active": True,
    }
    created = admin.post(URL, json=body)
    assert created.status_code == 201
    question_id = created.json()["id"]
    assert admin.patch(f"{URL}/{question_id}", json={"level": 4}).status_code == 422
    changed = admin.patch(f"{URL}/{question_id}", json={"prompt": "Updated?", "is_active": False})
    assert changed.status_code == 200
    assert changed.json()["level"] == 2
    assert changed.json()["is_active"] is False


def test_question_requires_exactly_one_correct_option(admin, db):
    topic = _topic(db)
    response = admin.post(
        URL,
        json={
            "topic_id": str(topic.id),
            "level": 1,
            "prompt": "Incomplete",
            "options": [
                {"id": "a", "text": "A", "correct": False},
                {"id": "b", "text": "B", "correct": False},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "one_correct_required"


def test_missing_level_makes_one_topic_and_the_quiz_not_ready(admin, db):
    seed(db)
    question = db.scalar(
        select(AptitudeQuestion)
        .join(Topic)
        .where(Topic.name == "Singlish", AptitudeQuestion.level == 3)
    )
    question.is_active = False
    db.commit()

    bank = admin.get(URL).json()
    singlish = next(topic for topic in bank["topics"] if topic["topic_name"] == "Singlish")
    assert bank["ready"] is False
    assert singlish["ready"] is False
    assert singlish["counts_by_level"]["3"] == 0


def test_not_sure_option_id_is_reserved_for_authors(admin, db):
    topic = _topic(db)
    response = admin.post(
        URL,
        json={
            "topic_id": str(topic.id),
            "level": 1,
            "prompt": "Pick one",
            "options": [
                {"id": NOT_SURE_OPTION["id"], "text": "Clash", "correct": True},
                {"id": "b", "text": "Other"},
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "option_id_reserved"


def test_an_unknown_topic_or_question_is_not_found(admin, db):
    missing = "00000000-0000-0000-0000-000000000000"
    response = admin.post(
        URL,
        json={
            "topic_id": missing,
            "level": 1,
            "prompt": "Pick one",
            "options": [{"id": "a", "text": "A", "correct": True}, {"id": "b", "text": "B"}],
        },
    )
    assert (response.status_code, response.json()["detail"]["code"]) == (404, "topic_not_found")
    response = admin.patch(f"{URL}/{missing}", json={"prompt": "X"})
    assert (response.status_code, response.json()["detail"]["code"]) == (404, "question_not_found")


def test_the_bank_is_for_administrators_only(client, learner):
    assert client.get(URL).status_code == 401
    assert learner.get(URL).status_code == 401
