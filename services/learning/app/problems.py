"""The rules a learner's request can break, as the monolith answered them (api/app/problems.py).

Each returns the platform's `Problem`, which `install_error_handlers` turns into
{"detail": {"code", "message", ...extra, "field"?}} with the same status, code and wording
as before the split.
"""

from app.platform.errors import Problem

# --- Learners (SCRUM-15, SCRUM-16) ---------------------------------------------------------


def lesson_unavailable() -> Problem:
    """The lesson is not published (withdrawn, in an archived topic, or never published).
    Answered as if it did not exist, so learners cannot tell drafts from missing lessons."""
    return Problem(
        "lesson_unavailable", "This lesson isn't available any more. It may have been removed.", 404
    )


def topic_unavailable() -> Problem:
    """The topic is archived or does not exist. Learners get one answer for both (SCRUM-53)."""
    return Problem(
        "topic_unavailable", "This topic isn't available any more. It may have been removed.", 404
    )


def lesson_updated() -> Problem:
    return Problem(
        "lesson_updated",
        "This lesson has just been updated. Reload it to see the new version.",
        409,
    )


def attempt_not_found() -> Problem:
    return Problem("attempt_not_found", "We couldn't find that attempt.", 404)


def attempt_finished() -> Problem:
    return Problem(
        "attempt_finished",
        "This attempt is already finished. Start the lesson again to retake it.",
        409,
    )


def question_not_found() -> Problem:
    return Problem(
        "question_not_found", "That question isn't in this lesson.", 422, field="question_id"
    )


def option_not_found() -> Problem:
    return Problem(
        "option_not_found",
        "That answer isn't one of this question's options.",
        422,
        field="option_id",
    )


def questions_unanswered(question_ids: list[str]) -> Problem:
    return Problem(
        "questions_unanswered",
        "Answer every question before finishing the lesson.",
        409,
        extra={"question_ids": question_ids},
    )


# --- Administrators (SCRUM-84) -------------------------------------------------------------


def version_not_found() -> Problem:
    return Problem("version_not_found", "That version of the lesson doesn't exist.", 404)


# --- Aptitude quiz (SCRUM-97) -------------------------------------------------------------


def aptitude_problem(code: str, message: str, status_code: int = 422) -> Problem:
    """The quiz's errors carry only a code and a message, as AptitudeError did."""
    return Problem(code, message, status_code)
