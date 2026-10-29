"""SCRUM-85: learners search every topic's published lessons by a word or phrase.

Results match the title and card text of each lesson's latest published version only
(AC2), carry the topic and whether this user has completed it (AC1), and follow the same
rules as the circles: no drafts, no withdrawn lessons, nothing from an archived topic.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.lesson_doc import plain_text
from app.models import Lesson, LessonCompletion, LessonStatus, LessonVersion, Topic

USER = {"email": "user@example.com", "password": "Password123"}
OTHER = {"email": "other@example.com", "password": "Password123"}


def _doc(*texts: str) -> dict:
    cards = [{"id": f"c{n}", "text": text} for n, text in enumerate(texts or ["Hello."])]
    cards.append(
        {
            "id": "quiz",
            "text": "Pick {{blank}}.",
            "question": {
                "id": "q",
                "options": [
                    {"id": "right", "text": "Kiasu", "correct": True},
                    {"id": "wrong", "text": "Shiok", "why_not": "Not paiseh at all."},
                ],
                "explanation": "Sabo means to sabotage.",
            },
        }
    )
    return {"cards": cards}


def _topic(db, name: str = "Singlish", position: int = 0, archived: bool = False) -> Topic:
    topic = Topic(name=name, position=position, archived_at=datetime.now(UTC) if archived else None)
    db.add(topic)
    db.commit()
    return topic


def _lesson(
    db,
    topic: Topic,
    title: str,
    *texts: str,
    position: int = 0,
    status: LessonStatus = LessonStatus.PUBLISHED,
) -> Lesson:
    lesson = Lesson(title=title, topic=topic, position=position, status=status, draft=_doc(*texts))
    db.add(lesson)
    db.flush()
    if status != LessonStatus.DRAFT:
        _publish(db, lesson, title, *texts)
    db.commit()
    return lesson


def _publish(db, lesson: Lesson, title: str, *texts: str) -> None:
    number = (db.scalar(select(func.count()).where(LessonVersion.lesson_id == lesson.id)) or 0) + 1
    now = datetime.now(UTC)
    lesson.published_at = now
    db.add(
        LessonVersion(
            lesson_id=lesson.id,
            number=number,
            title=title,
            summary=f"About {title}",
            doc=_doc(*texts),
            published_at=now,
        )
    )
    db.commit()


def _sign_in(client, make_user, who=USER):
    user = make_user(**who)
    client.post("/api/auth/sign-in", json=who)
    return user


def _search(client, q: str) -> list[dict]:
    response = client.get("/api/search", params={"q": q})
    assert response.status_code == 200, response.text
    return response.json()


def _titles(results: list[dict]) -> list[str]:
    return [result["title"] for result in results]


def test_needs_a_signed_in_user(client):
    assert client.get("/api/search", params={"q": "chope"}).status_code == 401


def test_needs_at_least_two_characters(client, make_user):
    _sign_in(client, make_user)
    assert client.get("/api/search", params={"q": "a"}).status_code == 422
    assert client.get("/api/search").status_code == 422


def test_matches_titles_and_card_text_ignoring_case_and_markdown(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    _lesson(db, topic, "Chope a seat", "Leave a tissue packet.", position=0)
    _lesson(db, topic, "Hawker basics", "You can **chope** _a table_ with a packet.", position=1)
    _lesson(db, topic, "Lah and leh", "Nothing about seats.", position=2)

    results = _search(client, "CHOPE a table")
    assert _titles(results) == ["Hawker basics"]
    assert "chope a table" in results[0]["snippet"]

    assert _titles(_search(client, "chope")) == ["Chope a seat", "Hawker basics"]


def test_results_carry_the_topic_and_whether_this_user_completed_them(client, db, make_user):
    user = _sign_in(client, make_user)
    other = make_user(**OTHER)
    topic = _topic(db)
    done = _lesson(db, topic, "Lah one", position=0)
    other_done = _lesson(db, topic, "Lah two", position=1)
    db.add(LessonCompletion(user_id=user.id, lesson_id=done.id))
    db.add(LessonCompletion(user_id=other.id, lesson_id=other_done.id))
    db.commit()

    results = _search(client, "lah")

    assert [(r["title"], r["completed"]) for r in results] == [
        ("Lah one", True),
        ("Lah two", False),
    ]
    assert results[0]["topic_id"] == str(topic.id)
    assert results[0]["topic_name"] == "Singlish"
    assert results[0]["lesson_id"] == str(done.id)
    # Only the title matched, so there is no card text to show.
    assert results[0]["snippet"] is None


def test_drafts_withdrawn_lessons_and_archived_topics_never_appear(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    archived = _topic(db, "Old", archived=True)
    _lesson(db, topic, "Chope draft", status=LessonStatus.DRAFT)
    _lesson(db, topic, "Chope withdrawn", status=LessonStatus.WITHDRAWN)
    _lesson(db, archived, "Chope archived")
    _lesson(db, topic, "Chope live")

    assert _titles(_search(client, "chope")) == ["Chope live"]


def test_only_the_latest_published_version_is_searched(client, db, make_user):
    _sign_in(client, make_user)
    topic = _topic(db)
    lesson = _lesson(db, topic, "Old title", "Say walao.")
    _publish(db, lesson, "New title", "Say alamak.")
    # An edit nobody has published yet.
    lesson.title = "Draft title"
    lesson.draft = _doc("Say sian.")
    db.commit()

    assert _titles(_search(client, "alamak")) == ["New title"]
    assert _titles(_search(client, "new title")) == ["New title"]
    assert _search(client, "walao") == []
    assert _search(client, "old title") == []
    assert _search(client, "sian") == []
    assert _search(client, "draft title") == []


def test_options_and_explanations_are_not_card_text(client, db, make_user):
    _sign_in(client, make_user)
    _lesson(db, _topic(db), "A lesson")

    for word in ("kiasu", "shiok", "paiseh", "sabotage"):
        assert _search(client, word) == [], word


def test_title_matches_come_first_then_the_order_of_the_circles(client, db, make_user):
    _sign_in(client, make_user)
    first = _topic(db, "Hawker", position=0)
    second = _topic(db, "Singlish", position=1)
    _lesson(db, first, "Ordering", "Say lah at the end.", position=0)
    _lesson(db, second, "Lah", position=1)
    _lesson(db, second, "Particles", "Lah softens things.", position=0)
    _lesson(db, first, "Lah at the stall", position=1)

    assert _titles(_search(client, "lah")) == [
        "Lah at the stall",
        "Lah",
        "Ordering",
        "Particles",
    ]


def test_a_long_card_is_cut_to_a_snippet_around_the_match(client, db, make_user):
    _sign_in(client, make_user)
    before = " ".join(["word"] * 30)
    after = " ".join(["more"] * 30)
    _lesson(db, _topic(db), "Long", f"{before} shiok {after}")

    snippet = _search(client, "shiok")[0]["snippet"]

    assert "shiok" in snippet
    assert snippet.startswith("…word ") and snippet.endswith(" more…")
    assert len(snippet) <= 130


def test_plain_text_reads_markdown_as_a_reader_would():
    text = "1. **Chope** a [seat](https://x.sg)\n- Say {{blank}} _lah_"
    assert plain_text(text) == "Chope a seat Say ___ lah"
