"""Errors the content-management logic raises (SCRUM-57, SCRUM-66, SCRUM-64, SCRUM-52).

Routes catch a ContentProblem and answer with {"detail": {"code", "message", "field"?,
...extra}}, the shape the front end reads through ApiError.
"""

import uuid
from dataclasses import asdict


class ContentProblem(Exception):
    """A rule the request broke. `status_code` is the HTTP status the route answers with."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
        extra: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        # More detail for the front end, e.g. the issues that block publishing.
        self.extra = extra or {}


def topic_not_found(field: str | None = None) -> ContentProblem:
    """`field` is set when the topic came from a form field rather than the URL."""
    return ContentProblem("topic_not_found", "That topic does not exist.", 404, field=field)


def topic_archived(field: str | None = None) -> ContentProblem:
    return ContentProblem(
        "topic_archived",
        "That topic is archived. Choose another topic, or restore it first.",
        409,
        field=field,
    )


def lesson_not_found() -> ContentProblem:
    return ContentProblem("lesson_not_found", "That lesson no longer exists.", 404)


def version_not_found() -> ContentProblem:
    return ContentProblem("version_not_found", "That version of the lesson doesn't exist.", 404)


def lesson_not_deletable() -> ContentProblem:
    return ContentProblem(
        "lesson_not_deletable",
        "This lesson has been published, so it cannot be deleted. Withdraw it instead.",
        409,
    )


def lesson_out_of_date() -> ContentProblem:
    return ContentProblem(
        "lesson_out_of_date",
        "This lesson was changed in another tab or by another administrator since you opened it.",
        409,
    )


def lesson_has_blockers(issues: list) -> ContentProblem:
    """`issues` are the lesson_doc.Issue blockers, sent along so the editor can list them."""
    return ContentProblem(
        "lesson_has_blockers",
        "This lesson isn't ready to publish yet.",
        409,
        extra={"issues": [asdict(issue) for issue in issues]},
    )


def lesson_status_conflict(message: str) -> ContentProblem:
    """Publish, withdraw or restore asked of a lesson in a status that doesn't allow it."""
    return ContentProblem("lesson_status_conflict", message, 409)


def topic_required() -> ContentProblem:
    return ContentProblem(
        "topic_required",
        "A lesson that has been published always keeps a topic. Choose another topic instead.",
        409,
        field="topic_id",
    )


def level_locked() -> ContentProblem:
    return ContentProblem(
        "level_locked",
        "A lesson's level can't be changed once it has been published, so learners' "
        "exemptions stay the same. To offer it at another level, write a new lesson.",
        409,
        field="level",
    )


def order_out_of_date() -> ContentProblem:
    return ContentProblem(
        "order_out_of_date",
        "The list has changed since you loaded it. Reload and try again.",
        409,
    )


def check_reorder(
    ids: list[uuid.UUID], previous_ids: list[uuid.UUID], current: list[uuid.UUID]
) -> None:
    """Refuse a reorder made from an out-of-date page (SCRUM-66).

    `current` is the list's order now, read with its rows locked. The page sends the order
    it showed (`previous_ids`) and the new one (`ids`). If the order it showed is not the
    order now, another administrator or another tab has changed the list since, whether by
    adding, removing or just reordering, and applying the request would silently undo
    their change. The new order must hold exactly the same items, each once.
    """
    if previous_ids != current or len(ids) != len(set(ids)) or set(ids) != set(current):
        raise order_out_of_date()


# --- Learners (SCRUM-15, SCRUM-16) ---------------------------------------------------------


def lesson_unavailable() -> ContentProblem:
    """The lesson is not published (a draft, withdrawn, or in an archived topic). Answered
    as if it did not exist, so learners cannot tell drafts from missing lessons."""
    return ContentProblem(
        "lesson_unavailable", "This lesson isn't available any more. It may have been removed.", 404
    )


def topic_unavailable() -> ContentProblem:
    """The topic is archived or does not exist. Learners get one answer for both, as with
    lessons (SCRUM-53)."""
    return ContentProblem(
        "topic_unavailable", "This topic isn't available any more. It may have been removed.", 404
    )


def lesson_updated() -> ContentProblem:
    return ContentProblem(
        "lesson_updated",
        "This lesson has just been updated. Reload it to see the new version.",
        409,
    )


def attempt_not_found() -> ContentProblem:
    return ContentProblem("attempt_not_found", "We couldn't find that attempt.", 404)


def attempt_finished() -> ContentProblem:
    return ContentProblem(
        "attempt_finished",
        "This attempt is already finished. Start the lesson again to retake it.",
        409,
    )


def question_not_found() -> ContentProblem:
    return ContentProblem(
        "question_not_found", "That question isn't in this lesson.", 422, field="question_id"
    )


def option_not_found() -> ContentProblem:
    return ContentProblem(
        "option_not_found",
        "That answer isn't one of this question's options.",
        422,
        field="option_id",
    )


def questions_unanswered(question_ids: list[str]) -> ContentProblem:
    return ContentProblem(
        "questions_unanswered",
        "Answer every question before finishing the lesson.",
        409,
        extra={"question_ids": question_ids},
    )


def reported_version_not_found() -> ContentProblem:
    """A report names a version this lesson never had (SCRUM-82)."""
    return ContentProblem(
        "version_not_found", "That version isn't one of this lesson's.", 422, field="version"
    )


def card_not_found() -> ContentProblem:
    return ContentProblem("card_not_found", "That card isn't in this lesson.", 422, field="card_id")


def report_not_found() -> ContentProblem:
    return ContentProblem("report_not_found", "We couldn't find that report.", 404)
