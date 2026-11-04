"""SCRUM-96/97: question-bank authoring and the onboarding aptitude quiz."""

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


def test_newcomer_gets_one_question_per_level_without_answers_and_submits(client, db):
    seed(db)
    assert (
        client.post(
            "/api/auth/sign-in",
            json={"email": "level3@sgjio.example.com", "password": "UserPass123"},
        ).status_code
        == 200
    )
    started = client.post("/api/aptitude/start")
    assert started.status_code == 200
    questions = started.json()["questions"]
    assert [question["level"] for question in questions] == [1, 2, 3, 4, 5]
    assert all("correct_option_id" not in question for question in questions)
    answers = [
        {"question_id": question["id"], "option_id": question["options"][0]["id"]}
        for question in questions
    ]
    result = client.post("/api/aptitude/submit", json={"answers": answers})
    assert result.status_code == 200
    assert 1 <= result.json()["level"] <= 5
    assert result.json()["total"] == 5


def test_skipping_creates_no_attempt_and_keeps_level_one(client, db):
    seed(db)
    client.post(
        "/api/auth/sign-in", json={"email": "skipped@sgjio.example.com", "password": "UserPass123"}
    )
    assert client.post("/api/aptitude/skip").status_code == 204
    progress = client.get("/api/progress").json()
    assert progress["level"] == 1
    assert progress["aptitude_taken"] is False
