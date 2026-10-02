"""Errors the content-management logic raises (SCRUM-57, SCRUM-66).

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


def topic_not_found() -> ContentProblem:
    return ContentProblem("topic_not_found", "That topic does not exist.", 404)


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
