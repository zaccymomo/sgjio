"""SCRUM-96: aptitude question-bank authoring."""

from sqlalchemy import select

from app.models import AptitudeQuestion, Topic, UserRole
from app.seed import seed


def test_seeded_bank_is_ready_and_has_two_active_questions_per_level(db):
    seed(db)
    counts = {level: 0 for level in range(1, 6)}
    for question in db.scalars(
        select(AptitudeQuestion).where(AptitudeQuestion.is_active.is_(True))
    ):
        counts[question.level] += 1
    assert all(count >= 2 for count in counts.values())


def test_admin_can_create_and_edit_question_but_not_its_level(client, db, make_user):
    admin = make_user("admin@example.com", "AdminPass123", role=UserRole.ADMIN)
    topic = Topic(name="Test topic")
    db.add(topic)
    db.commit()
    assert (
        client.post(
            "/api/admin/auth/sign-in", json={"email": admin.email, "password": "AdminPass123"}
        ).status_code
        == 200
    )
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
    created = client.post("/api/admin/aptitude-questions", json=body)
    assert created.status_code == 201
    question_id = created.json()["id"]
    refused = client.patch(f"/api/admin/aptitude-questions/{question_id}", json={"level": 4})
    assert refused.status_code == 422
    changed = client.patch(
        f"/api/admin/aptitude-questions/{question_id}",
        json={"prompt": "Updated?", "is_active": False},
    )
    assert changed.status_code == 200
    assert changed.json()["level"] == 2
    assert changed.json()["is_active"] is False


def test_question_requires_exactly_one_correct_option(client, db, make_user):
    admin = make_user("admin@example.com", "AdminPass123", role=UserRole.ADMIN)
    topic = Topic(name="Test topic")
    db.add(topic)
    db.commit()
    client.post("/api/admin/auth/sign-in", json={"email": admin.email, "password": "AdminPass123"})
    response = client.post(
        "/api/admin/aptitude-questions",
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
