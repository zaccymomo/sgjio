"""Errors the content-management logic raises (SCRUM-57, SCRUM-66, SCRUM-64).

Routes catch a ContentProblem and answer with {"detail": {"code", "message", "field"?}},
the shape the front end reads through ApiError.
"""

import uuid


class ContentProblem(Exception):
    """A rule the request broke. `status_code` is the HTTP status the route answers with."""

    def __init__(self, code: str, message: str, status_code: int, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field


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


def lesson_not_draft() -> ContentProblem:
    return ContentProblem(
        "lesson_not_draft",
        "Only drafts can be edited here. Published lessons are edited or withdrawn instead.",
        409,
    )


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
