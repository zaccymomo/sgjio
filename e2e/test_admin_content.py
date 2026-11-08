"""Authoring through the admin portal's API, and what learners see of it after replication
(detailed plan 8.3 items 5, 6, 7, 10 and 12).

Admin changes reach Learning over the broker, usually in well under a second, so learner
checks poll (`eventually`). Every topic made here is archived when its test ends.
"""

import io
import os

import httpx
from PIL import Image

from conftest import (
    circle,
    client,
    create_lesson,
    create_topic,
    eventually,
    learner_sees,
    lesson_doc,
    progress,
    publish,
    take_lesson,
    unique,
)
from shapes import check, not_signed_in, problem


def _png(width: int = 64, height: int = 48) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (244, 63, 94)).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(admin: httpx.Client, data: bytes, name: str = "picture.png", mime: str = "image/png"):
    return admin.post("/api/admin/media", files={"file": (name, data, mime)})


def _topic_page(http: httpx.Client, topic_id: str) -> dict:
    return check(http.get(f"/api/topics/{topic_id}"), "GET /api/topics/{topic_id}", 200)


def _lesson(admin: httpx.Client, lesson_id: str) -> dict:
    return check(
        admin.get(f"/api/admin/lessons/{lesson_id}"), "GET /api/admin/lessons/{lesson_id}", 200
    )


# --- Topics and lessons ------------------------------------------------------------------


def test_topic_and_lesson_draft_lifecycle(admin, scratch_topics, new_learner):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    assert topic["lesson_count"] == 0 and topic["published_by_level"] == [0, 0, 0, 0, 0]
    problem(admin.post("/api/admin/topics", json={"name": topic["name"]}), 409, "topic_name_taken")

    renamed = check(
        admin.patch(
            f"/api/admin/topics/{topic['id']}",
            json={"name": topic["name"] + " renamed", "description": "New words."},
        ),
        "PATCH /api/admin/topics/{topic_id}",
        200,
    )
    assert renamed["description"] == "New words."
    topics = check(admin.get("/api/admin/topics"), "GET /api/admin/topics", 200)
    assert topic["id"] in [t["id"] for t in topics]

    draft = create_lesson(admin, topic["id"], level=2)
    assert draft["status"] == "draft" and draft["deletable"] is True and draft["version"] is None
    lessons = check(admin.get("/api/admin/lessons"), "GET /api/admin/lessons", 200)
    assert draft["id"] in [lesson["id"] for lesson in lessons]

    edited = check(
        admin.patch(
            f"/api/admin/lessons/{draft['id']}",
            json={
                "updated_at": draft["updated_at"],
                "title": "Edited " + draft["title"],
                "doc": lesson_doc(3),
            },
        ),
        "PATCH /api/admin/lessons/{lesson_id}",
        200,
    )
    assert edited["title"].startswith("Edited ")
    # A page that is out of date can't overwrite the newer draft.
    stale = admin.patch(
        f"/api/admin/lessons/{draft['id']}",
        json={"updated_at": draft["updated_at"], "title": "Lost update"},
    )
    problem(stale, 409, "lesson_out_of_date")

    # A learner never sees a draft.
    learner = new_learner()
    problem(learner.http.get(f"/api/lessons/{draft['id']}"), 404, "lesson_unavailable")

    # A draft that was never published can be deleted; then the empty topic can too.
    deleted = admin.delete(
        f"/api/admin/lessons/{draft['id']}", params={"updated_at": edited["updated_at"]}
    )
    check(deleted, "DELETE /api/admin/lessons/{lesson_id}", 204)
    problem(admin.get(f"/api/admin/lessons/{draft['id']}"), 404, "lesson_not_found")
    check(
        admin.delete(f"/api/admin/topics/{topic['id']}"), "DELETE /api/admin/topics/{topic_id}", 204
    )
    scratch_topics.remove(topic["id"])


def test_publish_reaches_learners_then_withdraw_and_restore(admin, scratch_topics, new_learner):
    """8.3.5 and 8.3.6."""
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lesson = create_lesson(admin, topic["id"])
    learner = new_learner()
    assert learner_sees(learner.http, lesson["id"]) is None
    assert circle(learner.http, topic["id"]) is None

    published = publish(admin, lesson)
    assert published["status"] == "published" and published["version"]["number"] == 1
    assert published["deletable"] is False

    seen = eventually(lambda: learner_sees(learner.http, lesson["id"]), "the published lesson")
    assert seen["version"] == 1 and seen["topic"] == {"id": topic["id"], "name": topic["name"]}
    for card in seen["cards"]:
        for option in (card["question"] or {}).get("options", []):
            assert set(option) == {"id", "text"}, "the learner's copy says which is right"
    assert eventually(lambda: circle(learner.http, topic["id"]), "the circle") == {
        "id": topic["id"],
        "name": topic["name"],
        "completed": 0,
        "exempted": 0,
        "available": 1,
        "level": 0,
    }

    result = take_lesson(learner.http, lesson["id"])
    assert result["score"] == {"correct": 2, "scored": 2}
    assert result["first_completion"] is True and result["topic_completed"] is True
    assert circle(learner.http, topic["id"])["completed"] == 1

    # Withdraw: the lesson disappears for learners and the circle with it.
    current = _lesson(admin, lesson["id"])
    withdrawn = check(
        admin.post(
            f"/api/admin/lessons/{lesson['id']}/withdraw",
            json={"updated_at": current["updated_at"]},
        ),
        "POST /api/admin/lessons/{lesson_id}/withdraw",
        200,
    )
    assert withdrawn["status"] == "withdrawn"
    eventually(lambda: learner_sees(learner.http, lesson["id"]) is None, "the lesson to go")
    eventually(lambda: circle(learner.http, topic["id"]) is None, "the circle to go")
    problem(
        learner.http.post(f"/api/lessons/{lesson['id']}/attempts", json={"version": 1}),
        404,
        "lesson_unavailable",
    )

    # Restore: back, and the completion was kept.
    restored = check(
        admin.post(
            f"/api/admin/lessons/{lesson['id']}/restore",
            json={"updated_at": withdrawn["updated_at"]},
        ),
        "POST /api/admin/lessons/{lesson_id}/restore",
        200,
    )
    assert restored["status"] == "published"
    back = eventually(lambda: circle(learner.http, topic["id"]), "the circle to come back")
    assert (back["completed"], back["available"]) == (1, 1)

    # A second version: learners get it on their next start; the old one is refused.
    edited = check(
        admin.patch(
            f"/api/admin/lessons/{lesson['id']}",
            json={"updated_at": restored["updated_at"], "doc": lesson_doc(3)},
        ),
        "PATCH /api/admin/lessons/{lesson_id}",
        200,
    )
    assert edited["has_unpublished_changes"] is True
    assert publish(admin, edited)["version"]["number"] == 2
    eventually(
        lambda: (learner_sees(learner.http, lesson["id"]) or {}).get("version") == 2,
        "version 2",
    )
    problem(
        learner.http.post(f"/api/lessons/{lesson['id']}/attempts", json={"version": 1}),
        409,
        "lesson_updated",
    )


def test_reorder_lessons_and_topics_reaches_learners(admin, scratch_topics, new_learner):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    first = publish(admin, create_lesson(admin, topic["id"]))
    second = publish(admin, create_lesson(admin, topic["id"]))
    learner = new_learner()

    def order() -> list[str]:
        page = _topic_page(learner.http, topic["id"])
        return [lesson["id"] for lesson in page["lessons"]]

    eventually(lambda: order() == [first["id"], second["id"]], "both lessons, in order")

    reordered = check(
        admin.put(
            "/api/admin/lessons/order",
            json={
                "topic_id": topic["id"],
                "ids": [second["id"], first["id"]],
                "previous_ids": [first["id"], second["id"]],
            },
        ),
        "PUT /api/admin/lessons/order",
        200,
    )
    assert [lesson["id"] for lesson in reordered if lesson["topic_id"] == topic["id"]] == [
        second["id"],
        first["id"],
    ]
    eventually(lambda: order() == [second["id"], first["id"]], "the new lesson order")
    stale = admin.put(
        "/api/admin/lessons/order",
        json={
            "topic_id": topic["id"],
            "ids": [first["id"], second["id"]],
            "previous_ids": [first["id"], second["id"]],
        },
    )
    problem(stale, 409, "order_out_of_date")

    # Topics: move ours to the front, see the learner's circles follow, then put it back.
    topics = check(admin.get("/api/admin/topics"), "GET /api/admin/topics", 200)
    before = [t["id"] for t in topics if t["archived_at"] is None]
    moved = [topic["id"]] + [i for i in before if i != topic["id"]]
    try:
        check(
            admin.put("/api/admin/topics/order", json={"ids": moved, "previous_ids": before}),
            "PUT /api/admin/topics/order",
            200,
        )
        eventually(
            lambda: progress(learner.http)["topics"][0]["id"] == topic["id"],
            "our topic's circle to come first",
        )
    finally:
        current = [
            t["id"] for t in admin.get("/api/admin/topics").json() if t["archived_at"] is None
        ]
        restore = [i for i in before if i in current] + [i for i in current if i not in before]
        admin.put("/api/admin/topics/order", json={"ids": restore, "previous_ids": current})
    eventually(
        lambda: progress(learner.http)["topics"][-1]["id"] == topic["id"], "the order restored"
    )


def test_archive_topic_hides_it_from_learners(admin, scratch_topics, new_learner):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lesson = publish(admin, create_lesson(admin, topic["id"]))
    learner = new_learner()
    eventually(lambda: circle(learner.http, topic["id"]), "the circle")

    archived = check(
        admin.post(f"/api/admin/topics/{topic['id']}/archive"),
        "POST /api/admin/topics/{topic_id}/archive",
        200,
    )
    assert archived["archived_at"] is not None
    eventually(lambda: circle(learner.http, topic["id"]) is None, "the circle to go")
    eventually(lambda: learner_sees(learner.http, lesson["id"]) is None, "the lesson to go")
    eventually(
        lambda: learner.http.get(f"/api/topics/{topic['id']}").status_code == 404,
        "the topic page to go",
    )
    problem(learner.http.get(f"/api/topics/{topic['id']}"), 404, "topic_unavailable")
    # A topic with lessons can't be deleted, archived or not.
    problem(admin.delete(f"/api/admin/topics/{topic['id']}"), 409, "topic_not_empty")

    restored = check(
        admin.post(f"/api/admin/topics/{topic['id']}/restore"),
        "POST /api/admin/topics/{topic_id}/restore",
        200,
    )
    assert restored["archived_at"] is None
    eventually(lambda: circle(learner.http, topic["id"]), "the circle to come back")


# --- Media ---------------------------------------------------------------------------------


def test_media_upload_is_served_publicly_with_ranges_and_etags(admin, scratch_topics, new_learner):
    """8.3.10."""
    asset = check(_upload(admin, _png(800, 600)), "POST /api/admin/media", 201)
    assert asset["kind"] == "image" and asset["mime"] == "image/webp"
    assert asset["url"] == f"/api/media/{asset['id']}"
    assert (asset["width"], asset["height"]) == (800, 600)

    with client() as anonymous:
        whole = anonymous.get(asset["url"])
        assert whole.status_code == 200
        assert whole.headers["content-type"] == "image/webp"
        assert whole.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert whole.headers["accept-ranges"] == "bytes"
        assert len(whole.content) == asset["size"]

        part = anonymous.get(asset["url"], headers={"Range": "bytes=0-99"})
        assert part.status_code == 206
        assert part.content == whole.content[:100]
        assert part.headers["content-range"] == f"bytes 0-99/{asset['size']}"

        tail = anonymous.get(asset["url"], headers={"Range": "bytes=-10"})
        assert tail.status_code == 206 and tail.content == whole.content[-10:]
        assert anonymous.get(asset["url"], headers={"Range": "bytes=99999999-"}).status_code == 416

        cached = anonymous.get(asset["url"], headers={"If-None-Match": whole.headers["etag"]})
        assert cached.status_code == 304

        missing = anonymous.get("/api/media/00000000-0000-0000-0000-000000000000")
        problem(missing, 404, "media_not_found")

    # Used on a card, it comes with the learner's lesson.
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lesson = create_lesson(
        admin, topic["id"], image={"asset_id": asset["id"], "alt": "A red square"}
    )
    assert asset["id"] in _lesson(admin, lesson["id"])["assets"]
    publish(admin, lesson)
    learner = new_learner()
    seen = eventually(lambda http=learner.http: learner_sees(http, lesson["id"]), "the lesson")
    assert seen["cards"][0]["image"]["asset_id"] == asset["id"]
    assert seen["assets"][asset["id"]]["url"] == asset["url"]


def test_media_size_limits_and_types(admin):
    # Over the gateway's 20 MB: refused by the gateway, in Content's words.
    huge = os.urandom(21 * 1024 * 1024)
    response = _upload(admin, huge)
    detail = problem(response, 413, "media_too_large")
    assert "15 MB" in detail["message"]
    # Between Content's 15 MB and the gateway's 20 MB: refused by Content itself.
    problem(_upload(admin, huge[: 16 * 1024 * 1024]), 413, "media_too_large")
    # Not an image or audio file.
    response = _upload(admin, b"just text", name="notes.txt", mime="text/plain")
    assert response.status_code == 415, response.text
    # Learners can't upload.
    with client() as anonymous:
        not_signed_in(_upload(anonymous, _png()))


def test_other_requests_over_10_mb_are_refused_by_the_gateway(admin):
    response = admin.post(
        "/api/admin/topics",
        content=b"{" + b" " * (11 * 1024 * 1024) + b"}",
        headers={"Content-Type": "application/json"},
    )
    problem(response, 413, "payload_too_large")


# --- Reports and insights ------------------------------------------------------------------


def test_report_a_card_then_admin_marks_it_fixed(admin, scratch_topics, new_learner):
    """8.3.7."""
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    lesson = publish(admin, create_lesson(admin, topic["id"]))
    learner = new_learner()
    eventually(lambda http=learner.http: learner_sees(http, lesson["id"]), "the lesson")

    sent = check(
        learner.http.post(
            f"/api/lessons/{lesson['id']}/reports",
            json={"version": 1, "card_id": "card0", "reason": "typo", "note": unique("note")},
        ),
        "POST /api/lessons/{lesson_id}/reports",
        201,
    )
    problem(
        learner.http.post(
            f"/api/lessons/{lesson['id']}/reports",
            json={"version": 1, "card_id": "no-such-card", "reason": "typo"},
        ),
        422,
        "card_not_found",
    )

    reports = check(admin.get("/api/admin/reports"), "GET /api/admin/reports", 200)
    [mine] = [report for report in reports if report["id"] == sent["id"]]
    assert mine["lesson_id"] == lesson["id"] and mine["card_number"] == 2
    assert mine["topic_name"] == topic["name"] and mine["status"] == "open"
    assert mine["card_in_draft"] is True
    listed = [item for item in admin.get("/api/admin/lessons").json() if item["id"] == lesson["id"]]
    assert listed[0]["open_reports"] == 1

    fixed = check(
        admin.put(f"/api/admin/reports/{sent['id']}/status", json={"status": "fixed"}),
        "PUT /api/admin/reports/{report_id}/status",
        200,
    )
    assert fixed["status"] == "fixed" and fixed["resolved_at"] is not None
    assert sent["id"] not in [r["id"] for r in admin.get("/api/admin/reports").json()]
    closed = check(
        admin.get("/api/admin/reports", params={"status": "closed"}), "GET /api/admin/reports", 200
    )
    assert sent["id"] in [r["id"] for r in closed]
    problem(
        admin.put(
            "/api/admin/reports/00000000-0000-0000-0000-000000000000/status",
            json={"status": "fixed"},
        ),
        404,
        "report_not_found",
    )


def test_lesson_insights(admin, scratch_topics, new_learner):
    topic = create_topic(admin)
    scratch_topics.append(topic["id"])
    draft = create_lesson(admin, topic["id"])

    # Never published: the empty shape (a declared change: no 404).
    empty = check(
        admin.get(f"/api/admin/lessons/{draft['id']}/insights"),
        "GET /api/admin/lessons/{lesson_id}/insights",
        200,
    )
    assert empty["enough"] is False and empty["summary"] is None and empty["versions"] == []

    publish(admin, draft)
    learners = [new_learner(user_type="newcomer") for _ in range(3)] + [
        new_learner(user_type="singaporean") for _ in range(2)
    ]
    for n, learner in enumerate(learners):
        eventually(lambda http=learner.http: learner_sees(http, draft["id"]), "the lesson")
        take_lesson(learner.http, draft["id"], right=n % 2 == 0)

    def insights():
        body = check(
            admin.get(f"/api/admin/lessons/{draft['id']}/insights"),
            "GET /api/admin/lessons/{lesson_id}/insights",
            200,
        )
        return body if body["enough"] else None

    body = eventually(insights, "5 learners in the insights")
    assert body["status"] == "published" and body["version"] == 1
    assert body["topic_name"] == topic["name"]
    assert body["summary"]["learners"] == 5
    assert body["summary"]["finish_rate"] == 1.0
    assert body["summary"]["average_best"] == 0.6
    question = body["questions"][0]
    assert question["right_first_time"] == 0.6
    assert question["newcomers"] is None or 0 <= question["newcomers"] <= 1
    assert body["funnel"][0]["runs"] == 5
    assert body["doc"]["cards"][1]["question"]["options"][0]["correct"] is True

    # Filtered to one kind of learner.
    newcomers = check(
        admin.get(f"/api/admin/lessons/{draft['id']}/insights", params={"learners": "newcomer"}),
        "GET /api/admin/lessons/{lesson_id}/insights",
        200,
    )
    assert newcomers["learners"] == "newcomer"
    assert newcomers["enough"] is False  # only 3 newcomers finished
