"""SCRUM-96/97: per-topic question-bank authoring and adaptive onboarding quiz."""

from sqlalchemy import select

from app.aptitude import NOT_SURE_OPTION, _quiz_options
from app.models import (
    AptitudeAttempt,
    AptitudeQuestion,
    Profile,
    Topic,
    TopicExemption,
    UserRole,
    UserType,
)
from app.seed import TOPICS, seed

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
NEWCOMER = {"email": "newcomer@sgjio.example.com", "password": "UserPass123"}


def _admin(client, db, make_user):
    make_user(**ADMIN, role=UserRole.ADMIN)
    topic = Topic(name="Test topic")
    db.add(topic)
    db.commit()
    client.post("/api/admin/auth/sign-in", json=ADMIN)
    return topic


def _wrong(question: AptitudeQuestion) -> str:
    return next(
        option["id"] for option in question.options if option["id"] != question.correct_option_id
    )


def test_seeded_bank_is_ready_for_every_topic_and_level(client, db, make_user):
    seed(db)
    admin = make_user(**ADMIN, role=UserRole.ADMIN)
    client.post("/api/admin/auth/sign-in", json=ADMIN)

    response = client.get("/api/admin/aptitude-questions")
    assert response.status_code == 200
    bank = response.json()
    assert bank["ready"] is True
    assert {topic["topic_name"] for topic in bank["topics"]} == set(TOPICS)
    assert all(
        topic["ready"] and all(topic["counts_by_level"][str(level)] >= 1 for level in range(1, 6))
        for topic in bank["topics"]
    )
    assert len(bank["questions"]) >= len(TOPICS) * 5
    assert admin.id is not None


def test_admin_can_create_and_edit_question_but_not_its_level(client, db, make_user):
    topic = _admin(client, db, make_user)
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
    assert (
        client.patch(f"/api/admin/aptitude-questions/{question_id}", json={"level": 4}).status_code
        == 422
    )
    changed = client.patch(
        f"/api/admin/aptitude-questions/{question_id}",
        json={"prompt": "Updated?", "is_active": False},
    )
    assert changed.status_code == 200
    assert changed.json()["level"] == 2
    assert changed.json()["is_active"] is False


def test_question_requires_exactly_one_correct_option(client, db, make_user):
    topic = _admin(client, db, make_user)
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


def test_missing_level_makes_one_topic_and_the_quiz_not_ready(client, db, make_user):
    seed(db)
    make_user(**ADMIN, role=UserRole.ADMIN)
    client.post("/api/admin/auth/sign-in", json=ADMIN)
    question = db.scalar(
        select(AptitudeQuestion)
        .join(Topic)
        .where(Topic.name == "Singlish", AptitudeQuestion.level == 3)
    )
    question.is_active = False
    db.commit()

    bank = client.get("/api/admin/aptitude-questions").json()
    singlish = next(topic for topic in bank["topics"] if topic["topic_name"] == "Singlish")
    assert bank["ready"] is False
    assert singlish["ready"] is False
    assert singlish["counts_by_level"]["3"] == 0


def test_adaptive_quiz_moves_up_on_correct_and_topics_on_wrong(client, db):
    seed(db)
    assert client.post("/api/auth/sign-in", json=NEWCOMER).status_code == 200

    started = client.post("/api/aptitude/start")
    assert started.status_code == 200
    first = started.json()["question"]
    assert first["level"] == 1
    assert "correct_option_id" not in first

    first_model = db.get(AptitudeQuestion, first["id"])
    answers = [{"question_id": first["id"], "option_id": first_model.correct_option_id}]
    second = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    assert second["topic_id"] == first["topic_id"]
    assert second["level"] == 2

    second_model = db.get(AptitudeQuestion, second["id"])
    answers.append({"question_id": second["id"], "option_id": _wrong(second_model)})
    third = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    assert third["topic_id"] != first["topic_id"]
    assert third["level"] == 1

    current = third
    while current is not None:
        model = db.get(AptitudeQuestion, current["id"])
        answers.append({"question_id": current["id"], "option_id": _wrong(model)})
        step = client.post("/api/aptitude/next", json={"answers": answers}).json()
        current = step["question"]

    submitted = client.post("/api/aptitude/submit", json={"answers": answers})
    assert submitted.status_code == 200
    result = submitted.json()
    assert len(result["placements"]) == len(TOPICS)
    assert result["placements"][0]["level"] == 1
    assert all(placement["level"] == 0 for placement in result["placements"][1:])
    assert db.scalar(select(AptitudeAttempt)) is not None
    user_id = client.get("/api/auth/me").json()["id"]
    assert len(
        list(db.scalars(select(TopicExemption).where(TopicExemption.user_id == user_id)))
    ) == len(TOPICS)
    assert client.post("/api/aptitude/start").status_code == 409


def test_leaving_an_incomplete_quiz_saves_no_attempt_or_exemption(client, db):
    seed(db)
    client.post("/api/auth/sign-in", json=NEWCOMER)
    question = client.post("/api/aptitude/start").json()["question"]
    model = db.get(AptitudeQuestion, question["id"])
    client.post(
        "/api/aptitude/next",
        json={"answers": [{"question_id": question["id"], "option_id": model.correct_option_id}]},
    )

    user_id = client.get("/api/auth/me").json()["id"]
    assert db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id)) is None
    assert list(db.scalars(select(TopicExemption).where(TopicExemption.user_id == user_id))) == []
    restarted = client.post("/api/aptitude/start").json()["question"]
    assert restarted["level"] == 1


def test_inactive_question_is_not_selected_for_a_new_quiz(client, db):
    seed(db)
    first_topic = db.scalar(select(Topic).order_by(Topic.position, Topic.name))
    original = db.scalar(
        select(AptitudeQuestion).where(
            AptitudeQuestion.topic_id == first_topic.id, AptitudeQuestion.level == 1
        )
    )
    original.is_active = False
    replacement = AptitudeQuestion(
        topic_id=first_topic.id,
        level=1,
        prompt="Replacement",
        options=[{"id": "yes", "text": "Yes"}, {"id": "no", "text": "No"}],
        correct_option_id="yes",
        is_active=True,
    )
    db.add(replacement)
    db.commit()
    client.post("/api/auth/sign-in", json=NEWCOMER)

    selected = client.post("/api/aptitude/start").json()["question"]
    assert selected["id"] == str(replacement.id)


def test_singaporean_cannot_take_the_newcomer_quiz(client, db, make_user):
    seed(db)
    user = make_user(email="local@example.com", password="Password123")
    user.user_type = UserType.SINGAPOREAN
    user.profile = Profile(neighbourhood="Tampines", interests=["Food"], languages=["English"])
    db.commit()
    client.post(
        "/api/auth/sign-in",
        json={"email": "local@example.com", "password": "Password123"},
    )

    response = client.post("/api/aptitude/start")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "quiz_for_newcomers"


def test_quiz_options_are_shuffled_and_end_with_not_sure(client, db):
    seed(db)
    client.post("/api/auth/sign-in", json=NEWCOMER)
    question = client.post("/api/aptitude/start").json()["question"]
    model = db.get(AptitudeQuestion, question["id"])

    assert question["options"][-1] == NOT_SURE_OPTION
    assert sorted(option["id"] for option in question["options"][:-1]) == sorted(
        option["id"] for option in model.options
    )

    orders = {tuple(option["id"] for option in _quiz_options(model)[:-1]) for _ in range(50)}
    assert len(orders) > 1


def test_not_sure_counts_as_wrong(client, db):
    seed(db)
    client.post("/api/auth/sign-in", json=NEWCOMER)
    current = client.post("/api/aptitude/start").json()["question"]
    first_topic = current["topic_id"]
    answers = [{"question_id": current["id"], "option_id": NOT_SURE_OPTION["id"]}]

    step = client.post("/api/aptitude/next", json={"answers": answers}).json()
    assert step["question"]["topic_id"] != first_topic
    assert step["question"]["level"] == 1

    current = step["question"]
    while current is not None:
        answers.append({"question_id": current["id"], "option_id": NOT_SURE_OPTION["id"]})
        current = client.post("/api/aptitude/next", json={"answers": answers}).json()["question"]
    result = client.post("/api/aptitude/submit", json={"answers": answers}).json()
    assert result["correct"] == 0
    assert all(placement["level"] == 0 for placement in result["placements"])
    user_id = client.get("/api/auth/me").json()["id"]
    attempt = db.scalar(select(AptitudeAttempt).where(AptitudeAttempt.user_id == user_id))
    assert attempt.results[0]["option_text"] == NOT_SURE_OPTION["text"]
    assert attempt.results[0]["correct"] is False


def test_not_sure_option_id_is_reserved_for_authors(client, db, make_user):
    topic = _admin(client, db, make_user)
    response = client.post(
        "/api/admin/aptitude-questions",
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
