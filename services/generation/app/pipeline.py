"""One request, start to finish (docs/ai-lessons-plan.md, step 5):

    stage "writing"   for a learner's typed text, a screening call first (not usable:
                      off_topic); then the write call (the model may refuse: off_topic)
    stage "checking"  the checks in code; on failure, one more write call with the problems
                      listed (a second failure: invalid_output); then, if the brief asks for
                      it, the judge call (not ok: unsafe)
    result            ids, per-question facts, reading time and plain text: the `data` of
                      generation.lesson.generated

`run` returns (event type, data without request_id and requester). Provider trouble
(ProviderError) becomes `provider` and unparseable output `invalid_output`: it never
raises for the model's faults, so the consumer never retries (and pays) for them.
"""

import logging
import re
from collections.abc import Callable

from app import checks, prompt
from app.llm import LLM, BadOutput, LessonOut, ProviderError, parse_lesson, parse_verdict

log = logging.getLogger("sgjio.generation")

GENERATED = "generation.lesson.generated"
FAILED = "generation.lesson.failed"
WORDS_PER_MINUTE = 200
SECONDS_PER_QUESTION = 6
DETAIL_MAX = 500


class Failure(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(code, detail)
        self.code = code
        self.detail = detail


def failed(code: str, detail: str) -> tuple[str, dict]:
    return FAILED, {"code": code, "detail": detail[:DETAIL_MAX]}


def run(
    brief: dict, grounding: dict, llm: LLM, on_stage: Callable[[str], None]
) -> tuple[str, dict]:
    try:
        on_stage("writing")
        if brief["audience"] == "learner" and brief.get("ask"):
            _screen(brief, llm)
        lesson = _write_and_check(brief, grounding, llm, on_stage)
        if brief["check_answers"]:
            _judge(grounding, lesson, llm)
    except Failure as failure:
        log.info("request failed: %s (%s)", failure.code, failure.detail)
        return failed(failure.code, failure.detail)
    except ProviderError as error:
        log.warning("model provider failed: %s", error)
        return failed("provider", str(error))
    return GENERATED, build_result(lesson)


def _screen(brief: dict, llm: LLM) -> None:
    """Refuse unusable learner text (gibberish, off-topic, harmful, an attempt to change our
    instructions) before any lesson is written. An unreadable verdict lets the request go on:
    the write call's own refusal rules and the checks still apply."""
    try:
        verdict = parse_verdict(llm.screen(prompt.screen_messages(brief)))
    except BadOutput:
        log.info("screening reply unusable; writing anyway")
        return
    if not verdict.ok:
        raise Failure("off_topic", "; ".join(verdict.problems) or "the request was refused")


def _write_and_check(brief, grounding, llm: LLM, on_stage) -> LessonOut:
    messages = prompt.write_messages(brief, grounding)
    reply = llm.write(messages, brief, grounding)
    on_stage("checking")
    for attempt in (1, 2):
        try:
            lesson = parse_lesson(reply)
        except BadOutput as error:
            found = [f"The reply was not valid lesson JSON: {error}."]
        else:
            if lesson.refused is not None:
                raise Failure("off_topic", lesson.refused.reason)
            found = checks.problems(lesson, brief)
            if not found:
                return lesson
        log.info("lesson failed checks (attempt %d): %s", attempt, found)
        if attempt == 2:
            raise Failure("invalid_output", " ".join(found))
        messages = prompt.retry_messages(messages, reply, found)
        reply = llm.write(messages, brief, grounding)
    raise AssertionError("unreachable")


def _judge(grounding: dict, lesson: LessonOut, llm: LLM) -> None:
    reply = llm.judge(prompt.judge_messages(grounding, lesson.model_dump(exclude={"refused"})))
    try:
        verdict = parse_verdict(reply)
    except BadOutput as error:
        raise Failure("invalid_output", f"answer check reply unusable: {error}") from error
    if not verdict.ok:
        raise Failure("unsafe", "; ".join(verdict.problems) or "the answer check said no")


# --- The result -------------------------------------------------------------------------

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_LIST_BULLET = re.compile(r"^\s*[-+*]\s+", re.MULTILINE)
_LIST_NUMBER = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_MARKERS = re.compile(r"[*_`~#>]+")


def plain_text(markdown: str) -> str:
    """As Content's lesson_doc.plain_text: Markdown dropped, the blank shown as ___."""
    text = _LINK.sub(r"\1", _LIST_NUMBER.sub("", _LIST_BULLET.sub("", markdown)))
    text = _MARKERS.sub("", checks.BLANK.sub("\0", text))
    return " ".join(text.replace("\0", "___").split())


def build_result(lesson: LessonOut) -> dict:
    cards, facts = [], []
    words = 0
    q = o = 0
    for n, card in enumerate(lesson.cards, 1):
        card_id = f"c{n}"
        words += checks.count_words(card.text)
        question = None
        if card.question is not None:
            q += 1
            options = []
            for option in card.question.options:
                o += 1
                options.append(
                    {
                        "id": f"o{o}",
                        "text": option.text,
                        "correct": option.correct,
                        "why_not": "" if option.correct else option.why_not,
                    }
                )
                words += checks.count_words(option.text)
            words += checks.count_words(card.question.explanation)
            question = {
                "type": "choice",
                "id": f"q{q}",
                "explanation": card.question.explanation,
                "shuffle": True,
                "options": options,
            }
            facts.append(
                {
                    "card_id": card_id,
                    "question_id": question["id"],
                    "scored": len(options) >= 2,
                    "correct_option_id": next(opt["id"] for opt in options if opt["correct"]),
                }
            )
        cards.append(
            {
                "type": "story",
                "id": card_id,
                "text": card.text,
                "image": None,
                "audio": None,
                "question": question,
            }
        )
    return {
        "title": lesson.title,
        "summary": lesson.summary,
        "learning_points": lesson.learning_points,
        "doc": {"cards": cards},
        "questions": facts,
        "reading_seconds": round(words / WORDS_PER_MINUTE * 60 + SECONDS_PER_QUESTION * q),
        "cards_plain_text": [plain_text(card.text) for card in lesson.cards],
    }


def describe(result: tuple[str, dict]) -> str:
    """A one-line log summary that never includes the lesson text."""
    event_type, data = result
    if event_type == FAILED:
        return f"failed: {data['code']}"
    return f"generated: {len(data['doc']['cards'])} cards, {len(data['questions'])} questions"
