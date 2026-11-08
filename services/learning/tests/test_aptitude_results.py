"""SCRUM-100: see what the aptitude quiz exempted, and the level reached in each topic.
(Ported from api/tests/test_aptitude_results.py.)

The quiz result gives, for each topic it covered, how many of the topic's published lessons
the quiz exempted ("Hawker culture: 4 of 12 exempted", AC1), so a topic with none can say
the learner starts from its first lesson (AC2). The progress figures behind the circles
also carry the level reached in each topic, which the Profile tab's chart draws.
"""

import pytest

from app.progress import level_reached
from tests.conftest import sign_in
from tests.support.records import complete, quiz

DOC = {"cards": [{"id": "c1", "text": "Hello."}]}


@pytest.fixture
def lesson_in(content):
    def _lesson(topic, title, level, status="published"):
        return content.lesson(topic, title, level=level, status=status, doc=DOC)

    return _lesson


def _sign_in(client, make_user):
    user = make_user("user@example.com")
    sign_in(client, user)
    return user


def _placements(client) -> dict[str, dict]:
    response = client.get("/api/aptitude/result")
    assert response.status_code == 200
    return {row["topic"]: row for row in response.json()["placements"]}


def _levels(client) -> dict[str, int]:
    topics = client.get("/api/progress").json()["topics"]
    return {t["name"]: t["level"] for t in topics}


def test_no_result_before_the_quiz(client, make_user):
    _sign_in(client, make_user)
    response = client.get("/api/aptitude/result")
    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "attempt_not_found",
        "message": "No aptitude result yet.",
    }


# --- AC1 and AC2: how many lessons each topic's placement exempts ------------------------


def test_each_topic_says_how_many_of_its_lessons_are_exempted(
    client, db, content, lesson_in, make_user
):
    hawker, singlish = content.topic("Hawker", 0), content.topic("Singlish", 1)
    for level in (1, 2, 3, 5):
        lesson_in(hawker, f"Hawker {level}", level)
        lesson_in(singlish, f"Singlish {level}", level)
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 2, singlish: 0})

    placements = _placements(client)
    assert list(placements) == ["Hawker", "Singlish"]
    assert (placements["Hawker"]["exempted"], placements["Hawker"]["available"]) == (2, 4)
    assert placements["Hawker"]["level"] == 2
    # AC2: nothing exempted, so the page says the learner starts from the first lesson.
    assert (placements["Singlish"]["exempted"], placements["Singlish"]["available"]) == (0, 4)


def test_each_topic_lists_the_lessons_it_exempts(client, db, content, lesson_in, make_user):
    """For the results' list of exempted lessons: lowest level first, as their latest
    published version is titled, and only the topic's own (none for a topic at 0)."""
    hawker, singlish = content.topic("Hawker", 0), content.topic("Singlish", 1)
    lesson_in(hawker, "Hawker 3", 3)
    second = lesson_in(hawker, "Hawker 2", 2)
    lesson_in(hawker, "Hawker 1", 1)
    lesson_in(singlish, "Singlish 1", 1)
    content.publish(second, DOC, title="Hawker 2, revised")
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 2, singlish: 0})

    placements = _placements(client)
    lessons = placements["Hawker"]["lessons"]
    assert [(row["title"], row["level"]) for row in lessons] == [
        ("Hawker 1", 1),
        ("Hawker 2, revised", 2),
    ]
    assert lessons[1]["id"] == str(second.id)
    assert placements["Singlish"]["lessons"] == []


def test_the_list_leaves_out_lessons_learners_cannot_open(
    client, db, content, lesson_in, make_user
):
    """The list follows the counts beside it: a withdrawn lesson, a draft, and a lesson
    whose latest version has not reached Learning yet are left out."""
    hawker = content.topic("Hawker", 0)
    lesson_in(hawker, "Published", 1)
    lesson_in(hawker, "Withdrawn", 1, status="withdrawn")
    lesson_in(hawker, "Draft", 1, status="draft")
    held = lesson_in(hawker, "Held back", 1, status="draft")
    content.publish(held, DOC, deliver_deck=False)
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 5})

    placement = _placements(client)["Hawker"]
    assert [row["title"] for row in placement["lessons"]] == ["Published"]
    assert placement["exempted"] == len(placement["lessons"])


def test_only_currently_published_lessons_count(client, db, content, lesson_in, make_user):
    hawker = content.topic("Hawker")
    lesson_in(hawker, "Published", 1)
    lesson_in(hawker, "Draft", 1, "draft")
    lesson_in(hawker, "Withdrawn", 1, "withdrawn")
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 3})

    row = _placements(client)["Hawker"]
    assert (row["exempted"], row["available"]) == (1, 1)


def test_a_lesson_published_after_the_quiz_counts_too(client, db, content, lesson_in, make_user):
    """As in the circles (SCRUM-104 AC3), so the two figures always agree."""
    hawker = content.topic("Hawker")
    lesson_in(hawker, "First", 1)
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 2})
    assert _placements(client)["Hawker"]["exempted"] == 1

    lesson_in(hawker, "Added later", 2)
    lesson_in(hawker, "Harder", 4)
    row = _placements(client)["Hawker"]
    assert (row["exempted"], row["available"]) == (2, 3)


def test_completing_an_exempted_lesson_keeps_it_in_the_count(
    client, db, content, lesson_in, make_user
):
    hawker = content.topic("Hawker")
    first = lesson_in(hawker, "First", 1)
    lesson_in(hawker, "Second", 3)
    user = _sign_in(client, make_user)
    quiz(db, user, {hawker: 1})
    complete(db, user, first)

    assert _placements(client)["Hawker"]["exempted"] == 1


def test_a_topic_with_no_published_lessons_counts_none(client, db, content, make_user):
    empty = content.topic("Empty")
    user = _sign_in(client, make_user)
    quiz(db, user, {empty: 3})

    row = _placements(client)["Empty"]
    assert (row["exempted"], row["available"]) == (0, 0)


def test_a_topic_archived_since_the_quiz_is_left_out(client, db, content, lesson_in, make_user):
    kept, archived = content.topic("Kept", 0), content.topic("Archived", 1)
    lesson_in(kept, "Kept lesson", 1)
    lesson_in(archived, "Archived lesson", 1)
    user = _sign_in(client, make_user)
    quiz(db, user, {kept: 1, archived: 1})
    content.archive(archived)

    assert list(_placements(client)) == ["Kept"]


def test_submitting_the_quiz_returns_the_counts(client, content, lesson_in, make_user):
    """The page shown straight after the quiz reads the submit response, not the GET."""
    topic = content.topic("Hawker")
    lesson_in(topic, "Level 1 lesson", 1)
    lesson_in(topic, "Level 2 lesson", 2)
    for level in range(1, 6):
        content.question(
            topic,
            level,
            prompt=f"Question {level}",
            options=[{"id": "a", "text": "A"}, {"id": "b", "text": "B"}],
            correct="a",
        )
    _sign_in(client, make_user)

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
    assert client.get("/api/aptitude/result").json() == response.json()


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


def test_progress_carries_the_level_reached_in_each_topic(
    client, db, content, lesson_in, make_user
):
    hawker, singlish, festivals = (
        content.topic("Hawker", 0),
        content.topic("Singlish", 1),
        content.topic("Festivals", 2),
    )
    lessons = {}
    for topic in (hawker, singlish, festivals):
        for level in (1, 2, 3, 5):
            lessons[topic.name, level] = lesson_in(topic, f"{topic.name} {level}", level)
    user = _sign_in(client, make_user)
    # Festivals is left out of the quiz, as for a topic added after it was taken.
    quiz(db, user, {hawker: 2, singlish: 0})

    assert _levels(client) == {"Hawker": 2, "Singlish": 0, "Festivals": 0}

    # Completing lessons raises the level, but only once every lesson below is covered.
    complete(db, user, lessons["Hawker", 3])
    complete(db, user, lessons["Singlish", 1])
    complete(db, user, lessons["Festivals", 2])
    assert _levels(client) == {"Hawker": 3, "Singlish": 1, "Festivals": 0}

    # Finishing every lesson in a topic fills it.
    complete(db, user, lessons["Hawker", 5])
    assert _levels(client)["Hawker"] == 5


def test_a_user_who_skipped_the_quiz_has_levels_from_lessons_alone(
    client, db, content, lesson_in, make_user
):
    hawker = content.topic("Hawker")
    first = lesson_in(hawker, "First", 1)
    lesson_in(hawker, "Second", 2)
    user = _sign_in(client, make_user)

    assert _levels(client) == {"Hawker": 0}
    complete(db, user, first)
    assert _levels(client) == {"Hawker": 1}
