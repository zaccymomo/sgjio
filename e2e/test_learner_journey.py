"""A learner's whole journey, start to finish, and what deleting the account erases
(detailed plan 8.3 item 8).

The admin publishes a lesson of the suite's own for the learner to take, so every figure
checked here is exact.
"""

from conftest import (
    PASSWORD,
    circle,
    client,
    create_lesson,
    create_topic,
    eventually,
    learner_sees,
    onboard,
    progress,
    publish,
    register,
    take_lesson,
    unique,
    unique_email,
)
from shapes import check, not_signed_in, problem


def test_learner_journey(admin, scratch_topics):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lessons = [
        publish(admin, create_lesson(admin, topic["id"], words=unique("zebra"))) for _ in range(2)
    ]
    keyword = lessons[0]["doc"]["cards"][0]["text"].split()[-1]

    with client() as http:
        email = unique_email()
        user = register(http, email)["user"]
        assert user["intro_finished_at"] is None and user["user_type"] == "newcomer"
        assert check(http.get("/api/auth/me"), "GET /api/auth/me", 200)["id"] == user["id"]
        onboard(http)

        # Home: every topic with published lessons has a circle; ours is "Not started".
        home = progress(http)
        assert home["completed"] == 0 and home["exempted"] == 0
        assert home["available"] == sum(t["available"] for t in home["topics"])
        ours = eventually(
            lambda: (c := circle(http, topic["id"])) and c["available"] == 2 and c,
            "our topic's circle with both lessons",
        )
        assert ours["completed"] == 0
        assert home["suggestion"] is not None

        # Topic page.
        page = check(http.get(f"/api/topics/{topic['id']}"), "GET /api/topics/{topic_id}", 200)
        assert page["description"] == "e2e"
        assert [lesson["id"] for lesson in page["lessons"]] == [lesson["id"] for lesson in lessons]
        assert all(
            lesson["last_attempted_at"] is None and lesson["best_correct"] is None
            for lesson in page["lessons"]
        )

        # Search finds the lesson by a word on its first card.
        found = check(http.get("/api/search", params={"q": keyword}), "GET /api/search", 200)
        assert [hit["lesson_id"] for hit in found] == [lessons[0]["id"]]
        assert keyword in found[0]["snippet"] and found[0]["completed"] is False
        assert (
            check(http.get("/api/search", params={"q": "zz" + unique()}), "GET /api/search", 200)
            == []
        )

        # Take the first lesson, getting everything wrong first time.
        lesson = learner_sees(http, lessons[0]["id"])
        attempt = check(
            http.post(
                f"/api/lessons/{lessons[0]['id']}/attempts", json={"version": lesson["version"]}
            ),
            "POST /api/lessons/{lesson_id}/attempts",
            201,
        )
        problem(http.post(f"/api/attempts/{attempt['id']}/finish"), 409, "questions_unanswered")
        for n, card in enumerate(card for card in lesson["cards"] if card["question"]):
            question = card["question"]
            first = check(
                http.post(
                    f"/api/attempts/{attempt['id']}/answers",
                    json={"question_id": question["id"], "option_id": f"q{n}-wrong"},
                ),
                "POST /api/attempts/{attempt_id}/answers",
                200,
            )
            assert first == {
                "correct": False,
                "correct_option_id": f"q{n}-right",
                "explanation": "Because it is right.",
                "why_not": "Not this one.",
            }
            # Only the first answer counts.
            again = http.post(
                f"/api/attempts/{attempt['id']}/answers",
                json={"question_id": question["id"], "option_id": f"q{n}-right"},
            )
            assert check(again, "POST /api/attempts/{attempt_id}/answers", 200)["correct"] is False
        finished = check(
            http.post(f"/api/attempts/{attempt['id']}/finish"),
            "POST /api/attempts/{attempt_id}/finish",
            200,
        )
        assert finished["score"] == {"correct": 0, "scored": 2}
        assert finished["first_completion"] is True and finished["topic_completed"] is False
        problem(
            http.post(
                f"/api/attempts/{attempt['id']}/answers",
                json={"question_id": "q0", "option_id": "q0-right"},
            ),
            409,
            "attempt_finished",
        )

        # The circle moved: completed whether right or wrong.
        assert (circle(http, topic["id"])["completed"], circle(http, topic["id"])["available"]) == (
            1,
            2,
        )
        assert progress(http)["completed"] == 1
        page = check(http.get(f"/api/topics/{topic['id']}"), "GET /api/topics/{topic_id}", 200)
        taken = page["lessons"][0]
        assert taken["completed"] is True and (taken["best_correct"], taken["best_scored"]) == (
            0,
            2,
        )
        assert taken["last_attempted_at"] is not None

        # Review shows both mistakes.
        review = check(http.get("/api/review"), "GET /api/review", 200)
        assert {m["question_id"] for m in review["mistakes"]} == {"q0", "q1"}
        assert all(m["chosen"] == "Wrong" and m["correct"] == "Right" for m in review["mistakes"])

        # Retake, all right: best score kept, still one completion; mistakes fixed drop off.
        retake = take_lesson(http, lessons[0]["id"], right=True)
        assert retake["best"] == {"correct": 2, "scored": 2} and retake["first_completion"] is False
        assert check(http.get("/api/review"), "GET /api/review", 200)["mistakes"] == []

        # The second lesson completes the topic.
        assert take_lesson(http, lessons[1]["id"])["topic_completed"] is True
        assert circle(http, topic["id"])["completed"] == 2

        # Report a problem on a card.
        check(
            http.post(
                f"/api/lessons/{lessons[0]['id']}/reports",
                json={"version": 1, "card_id": "intro", "reason": "wrong", "note": "Looks off."},
            ),
            "POST /api/lessons/{lesson_id}/reports",
            201,
        )

        # Change password, sign out, sign back in with the new one.
        check(
            http.post(
                "/api/auth/change-password",
                json={
                    "current_password": PASSWORD,
                    "password": "Changed123",
                    "password_confirmation": "Changed123",
                },
            ),
            "POST /api/auth/change-password",
            204,
        )
        check(http.post("/api/auth/sign-out"), "POST /api/auth/sign-out", 204)
        not_signed_in(http.get("/api/progress"))
        check(
            http.post("/api/auth/sign-in", json={"email": email, "password": "Changed123"}),
            "POST /api/auth/sign-in",
            200,
        )
        assert progress(http)["completed"] == 2

        # Delete the account.
        problem(
            http.post("/api/auth/delete-account", json={"password": "WrongPass1"}),
            401,
            "incorrect_password",
        )
        deleted = http.post("/api/auth/delete-account", json={"password": "Changed123"})
        check(deleted, "POST /api/auth/delete-account", 204)
        assert "sgjio_session=" in deleted.headers["set-cookie"]
        not_signed_in(http.get("/api/progress"))

    # Signing in again is impossible; the email is free at once, and the new account
    # starts from nothing.
    with client() as again:
        problem(
            again.post("/api/auth/sign-in", json={"email": email, "password": "Changed123"}),
            401,
            "invalid_credentials",
        )
        fresh = register(again, email)["user"]
        assert fresh["id"] != user["id"]
        onboard(again)
        assert progress(again)["completed"] == 0
        assert check(again.get("/api/review"), "GET /api/review", 200) == {"mistakes": []}
        page = check(again.get(f"/api/topics/{topic['id']}"), "GET /api/topics/{topic_id}", 200)
        assert page["completed"] == 0
        assert all(lesson["last_attempted_at"] is None for lesson in page["lessons"])


def test_deleting_an_account_erases_its_learning_data(admin, scratch_topics, new_learner):
    """8.3.8: insights count the deleted learner out within seconds, and the report stays
    (with nobody behind it)."""
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lesson = publish(admin, create_lesson(admin, topic["id"]))
    learners = [new_learner() for _ in range(6)]
    for learner in learners:
        eventually(lambda http=learner.http: learner_sees(http, lesson["id"]), "the lesson")
        take_lesson(learner.http, lesson["id"])
    leaving = learners[0]
    report = check(
        leaving.http.post(
            f"/api/lessons/{lesson['id']}/reports",
            json={"version": 1, "card_id": "card1", "reason": "typo", "note": unique("note")},
        ),
        "POST /api/lessons/{lesson_id}/reports",
        201,
    )

    def insights() -> dict:
        return check(
            admin.get(f"/api/admin/lessons/{lesson['id']}/insights"),
            "GET /api/admin/lessons/{lesson_id}/insights",
            200,
        )

    before = eventually(lambda: (body := insights())["enough"] and body, "6 learners")
    assert before["summary"]["learners"] == 6
    assert before["funnel"][0]["runs"] == 6

    check(
        leaving.http.post("/api/auth/delete-account", json={"password": PASSWORD}),
        "POST /api/auth/delete-account",
        204,
    )
    after = eventually(
        lambda: (body := insights())["summary"]["learners"] == 5 and body,
        "the deleted learner's runs to be erased",
    )
    assert after["funnel"][0]["runs"] == 5

    reports = check(admin.get("/api/admin/reports"), "GET /api/admin/reports", 200)
    [kept] = [r for r in reports if r["id"] == report["id"]]
    assert "reporter" not in str(kept) and kept["status"] == "open"

    # The same email can register again at once, as a brand-new learner.
    with client() as http:
        register(http, leaving.email)
        onboard(http)
        assert progress(http)["completed"] == 0
