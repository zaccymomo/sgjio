"""SCRUM-100: see what the aptitude quiz exempted, and the level reached in each topic.

The quiz result gives, for each topic it covered, how many of the topic's published lessons
the quiz exempted ("Hawker culture: 4 of 12 exempted", AC1), so a topic with none can say
the learner starts from its first lesson (AC2). The progress figures behind the circles
also carry the level reached in each topic, which the Profile tab's chart draws.
"""

from datetime import UTC, datetime

from app.models import (
    AptitudeAttempt,
    Lesson,
    LessonCompletion,
    LessonStatus,
    LessonVersion,
    Topic,
    TopicExemption,
)
from app.progress import level_reached

USER = {"email": "user@example.com", "password": "Password123"}
DOC = {"cards": [{"id": "c1", "text": "Hello."}]}


def _topic(db, name: str, position: int = 0) -> Topic:
    topic = Topic(name=name, position=position)
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db, topic: Topic, title: str, level: int, status: LessonStatus = LessonStatus.PUBLISHED
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, level=level, status=status)
    db.add(lesson)
    db.flush()
    if status != LessonStatus.DRAFT:
        now = datetime.now(UTC)
        lesson.published_at = now
        db.add(
            LessonVersion(
                lesson_id=lesson.id, number=1, title=title, summary="", doc=DOC, published_at=now
            )
        )
    db.commit()
    return lesson


def _quiz(db, user, exemptions: dict[Topic, int]) -> None:
    db.add(AptitudeAttempt(user_id=user.id, results=[{"correct": True}]))
    db.flush()
    for topic, level in exemptions.items():
        db.add(TopicExemption(user_id=user.id, topic_id=topic.id, level=level))
    db.commit()


def _complete(db, user, lesson: Lesson) -> None:
    db.add(LessonCompletion(user_id=user.id, lesson_id=lesson.id, best_correct=1, best_scored=1))
    db.commit()


def _sign_in(client, make_user):
    user = make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    return user


def _placements(client) -> dict[str, dict]:
    response = client.get("/api/aptitude/result")
    assert response.status_code == 200
    return {row["topic"]: row for row in response.json()["placements"]}


def _levels(client) -> dict[str, tuple[int, int | None]]:
    topics = client.get("/api/progress").json()["topics"]
    return {t["name"]: (t["level"], t["quiz_level"]) for t in topics}


# --- AC1 and AC2: how many lessons each topic's placement exempts ------------------------


def test_each_topic_says_how_many_of_its_lessons_are_exempted(client, db, make_user):
    hawker, singlish = _topic(db, "Hawker", 0), _topic(db, "Singlish", 1)
    for level in (1, 2, 3, 5):
        _lesson(db, hawker, f"Hawker {level}", level)
        _lesson(db, singlish, f"Singlish {level}", level)
    user = _sign_in(client, make_user)
    _quiz(db, user, {hawker: 2, singlish: 0})

    placements = _placements(client)
    assert list(placements) == ["Hawker", "Singlish"]
    assert (placements["Hawker"]["exempted"], placements["Hawker"]["available"]) == (2, 4)
    assert placements["Hawker"]["level"] == 2
    # AC2: nothing exempted, so the page says the learner starts from the first lesson.
    assert (placements["Singlish"]["exempted"], placements["Singlish"]["available"]) == (0, 4)


def test_only_currently_published_lessons_count(client, db, make_user):
    hawker = _topic(db, "Hawker")
    _lesson(db, hawker, "Published", 1)
    _lesson(db, hawker, "Draft", 1, LessonStatus.DRAFT)
    _lesson(db, hawker, "Withdrawn", 1, LessonStatus.WITHDRAWN)
    user = _sign_in(client, make_user)
    _quiz(db, user, {hawker: 3})

    row = _placements(client)["Hawker"]
    assert (row["exempted"], row["available"]) == (1, 1)


def test_a_lesson_published_after_the_quiz_counts_too(client, db, make_user):
    """As in the circles (SCRUM-104 AC3), so the two figures always agree."""
    hawker = _topic(db, "Hawker")
    _lesson(db, hawker, "First", 1)
    user = _sign_in(client, make_user)
    _quiz(db, user, {hawker: 2})
    assert _placements(client)["Hawker"]["exempted"] == 1

    _lesson(db, hawker, "Added later", 2)
    _lesson(db, hawker, "Harder", 4)
    row = _placements(client)["Hawker"]
    assert (row["exempted"], row["available"]) == (2, 3)


def test_completing_an_exempted_lesson_keeps_it_in_the_count(client, db, make_user):
    hawker = _topic(db, "Hawker")
    first = _lesson(db, hawker, "First", 1)
    _lesson(db, hawker, "Second", 3)
    user = _sign_in(client, make_user)
    _quiz(db, user, {hawker: 1})
    _complete(db, user, first)

    assert _placements(client)["Hawker"]["exempted"] == 1


def test_a_topic_with_no_published_lessons_counts_none(client, db, make_user):
    empty = _topic(db, "Empty")
    user = _sign_in(client, make_user)
    _quiz(db, user, {empty: 3})

    row = _placements(client)["Empty"]
    assert (row["exempted"], row["available"]) == (0, 0)


def test_a_topic_archived_since_the_quiz_is_left_out(client, db, make_user):
    kept, archived = _topic(db, "Kept", 0), _topic(db, "Archived", 1)
    _lesson(db, kept, "Kept lesson", 1)
    _lesson(db, archived, "Archived lesson", 1)
    user = _sign_in(client, make_user)
    _quiz(db, user, {kept: 1, archived: 1})
    archived.archived_at = datetime.now(UTC)
    db.commit()

    assert list(_placements(client)) == ["Kept"]


def test_submitting_the_quiz_returns_the_counts(client, db, make_user):
    """The page shown straight after the quiz reads the submit response, not the GET."""
    from app.models import AptitudeQuestion, Profile, UserType

    topic = _topic(db, "Hawker")
    _lesson(db, topic, "Level 1 lesson", 1)
    _lesson(db, topic, "Level 2 lesson", 2)
    for level in range(1, 6):
        db.add(
            AptitudeQuestion(
                topic_id=topic.id,
                level=level,
                prompt=f"Question {level}",
                options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
                correct_option_id="a",
            )
        )
    db.commit()
    user = _sign_in(client, make_user)
    user.user_type = UserType.NEWCOMER
    user.profile = Profile(neighbourhood="Tampines", interests=["Food"], languages=["English"])
    db.commit()

    # Right at Levels 1 and 2, wrong at Level 3: placed at Level 2.
    question = client.post("/api/aptitude/start").json()["question"]
    answers = []
    for option in ("a", "a", "b"):
        answers.append({"question_id": question["id"], "option_id": option})
        step = client.post("/api/aptitude/next", json={"answers": answers}).json()
        question = step["question"]
    assert step["done"]

    response = client.post("/api/aptitude/submit", json={"answers": answers})
    assert response.status_code == 200, response.text
    row = response.json()["placements"][0]
    assert (row["level"], row["exempted"], row["available"]) == (2, 2, 2)


# --- The level reached in each topic, for the Profile tab's chart ------------------------


def test_level_reached_rules():
    # Nothing covered: Level 0, or whatever the quiz gave.
    assert level_reached(None, [(1, False), (2, False)]) == 0
    assert level_reached(3, [(1, False)]) == 3
    # The highest level whose lessons, and all those below it, are covered.
    assert level_reached(None, [(1, True), (2, True), (3, False), (5, False)]) == 2
    # A lesson covered out of order does not lift the level past a gap.
    assert level_reached(None, [(1, False), (2, True), (3, True)]) == 0
    # Every lesson at a level must be covered.
    assert level_reached(None, [(1, True), (2, True), (2, False), (3, False)]) == 1
    # A level with no lessons neither holds back nor lifts.
    assert level_reached(None, [(1, True), (3, True), (5, False)]) == 3
    # Everything covered reaches the top, even if the topic's lessons stop below Level 5.
    assert level_reached(None, [(1, True), (2, True)]) == 5
    # Never below the quiz's level.
    assert level_reached(4, [(1, True), (2, False)]) == 4
    # No lessons at all: just the quiz's level.
    assert level_reached(None, []) == 0


def test_progress_carries_the_level_reached_and_the_quiz_level(client, db, make_user):
    hawker, singlish, festivals = (
        _topic(db, "Hawker", 0),
        _topic(db, "Singlish", 1),
        _topic(db, "Festivals", 2),
    )
    lessons = {}
    for topic in (hawker, singlish, festivals):
        for level in (1, 2, 3, 5):
            lessons[topic.name, level] = _lesson(db, topic, f"{topic.name} {level}", level)
    user = _sign_in(client, make_user)
    # Festivals is left out of the quiz, as for a topic added after it was taken.
    _quiz(db, user, {hawker: 2, singlish: 0})

    assert _levels(client) == {"Hawker": (2, 2), "Singlish": (0, 0), "Festivals": (0, None)}

    # Completing lessons in order raises the level; the quiz level stays as it was.
    _complete(db, user, lessons["Hawker", 3])
    _complete(db, user, lessons["Singlish", 1])
    _complete(db, user, lessons["Festivals", 2])
    assert _levels(client) == {"Hawker": (3, 2), "Singlish": (1, 0), "Festivals": (0, None)}

    # Finishing every lesson in a topic fills it.
    _complete(db, user, lessons["Hawker", 5])
    assert _levels(client)["Hawker"] == (5, 2)


def test_a_user_who_skipped_the_quiz_has_levels_from_lessons_alone(client, db, make_user):
    hawker = _topic(db, "Hawker")
    first = _lesson(db, hawker, "First", 1)
    _lesson(db, hawker, "Second", 2)
    user = _sign_in(client, make_user)

    assert _levels(client) == {"Hawker": (0, None)}
    _complete(db, user, first)
    assert _levels(client) == {"Hawker": (1, None)}
