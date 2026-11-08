"""SCRUM-85: learners search every topic's published lessons by a word or phrase.
(Ported from api/tests/test_lesson_search.py.)

Results match the title and card text of each lesson's latest published version only
(AC2), carry the topic and whether this user has completed it (AC1), and follow the same
rules as the circles: no drafts, no withdrawn lessons, nothing from an archived topic.

Moved to Content: test_plain_text_reads_markdown_as_a_reader_would. Content works out each
card's plain text (`cards_plain_text`); Learning only searches it.
"""

import pytest

from app.models import LessonCompletion
from tests.conftest import sign_in


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


@pytest.fixture
def lesson_in(content):
    def _lesson(topic, title, *texts, position=0, status="published"):
        return content.lesson(
            topic,
            title,
            doc=_doc(*texts),
            position=position,
            status=status,
            summary=f"About {title}",
        )

    return _lesson


def _sign_in(client, make_user, email="user@example.com"):
    user = make_user(email)
    sign_in(client, user)
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


def test_matches_titles_and_card_text_ignoring_case_and_markdown(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson_in(topic, "Chope a seat", "Leave a tissue packet.", position=0)
    lesson_in(topic, "Hawker basics", "You can **chope** _a table_ with a packet.", position=1)
    lesson_in(topic, "Lah and leh", "Nothing about seats.", position=2)

    results = _search(client, "CHOPE a table")
    assert _titles(results) == ["Hawker basics"]
    assert "chope a table" in results[0]["snippet"]

    assert _titles(_search(client, "chope")) == ["Chope a seat", "Hawker basics"]


def test_results_carry_the_topic_and_whether_this_user_completed_them(
    client, db, content, lesson_in, make_user
):
    user = _sign_in(client, make_user)
    other = make_user("other@example.com")
    topic = content.topic()
    done = lesson_in(topic, "Lah one", position=0)
    other_done = lesson_in(topic, "Lah two", position=1)
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


def test_drafts_withdrawn_lessons_and_archived_topics_never_appear(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    topic = content.topic()
    archived = content.topic("Old", archived=True)
    lesson_in(topic, "Chope draft", status="draft")
    lesson_in(topic, "Chope withdrawn", status="withdrawn")
    lesson_in(archived, "Chope archived")
    lesson_in(topic, "Chope live")

    assert _titles(_search(client, "chope")) == ["Chope live"]


def test_only_the_latest_published_version_is_searched(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    topic = content.topic()
    lesson = lesson_in(topic, "Old title", "Say walao.")
    content.publish(lesson, _doc("Say alamak."), title="New title")
    # An edit nobody has published yet: only the draft title reaches Learning.
    content.update_lesson(lesson, title="Draft title", draft=_doc("Say sian."))

    assert _titles(_search(client, "alamak")) == ["New title"]
    assert _titles(_search(client, "new title")) == ["New title"]
    assert _search(client, "walao") == []
    assert _search(client, "old title") == []
    assert _search(client, "sian") == []
    assert _search(client, "draft title") == []


def test_options_and_explanations_are_not_card_text(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    lesson_in(content.topic(), "A lesson")

    for word in ("kiasu", "shiok", "paiseh", "sabotage"):
        assert _search(client, word) == [], word


def test_title_matches_come_first_then_the_order_of_the_circles(
    client, content, lesson_in, make_user
):
    _sign_in(client, make_user)
    first = content.topic("Hawker", position=0)
    second = content.topic("Singlish", position=1)
    lesson_in(first, "Ordering", "Say lah at the end.", position=0)
    lesson_in(second, "Lah", position=1)
    lesson_in(second, "Particles", "Lah softens things.", position=0)
    lesson_in(first, "Lah at the stall", position=1)

    assert _titles(_search(client, "lah")) == [
        "Lah at the stall",
        "Lah",
        "Ordering",
        "Particles",
    ]


def test_a_long_card_is_cut_to_a_snippet_around_the_match(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    before = " ".join(["word"] * 30)
    after = " ".join(["more"] * 30)
    lesson_in(content.topic(), "Long", f"{before} shiok {after}")

    snippet = _search(client, "shiok")[0]["snippet"]

    assert "shiok" in snippet
    assert snippet.startswith("…word ") and snippet.endswith(" more…")
    assert len(snippet) <= 130


def test_the_snippet_comes_from_the_first_matching_card(client, content, lesson_in, make_user):
    _sign_in(client, make_user)
    lesson_in(content.topic(), "Cards", "Nothing here.", "Second card says shiok.", "Shiok again.")

    assert _search(client, "shiok")[0]["snippet"] == "Second card says shiok."
