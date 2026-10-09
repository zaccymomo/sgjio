"""What a lesson is: a deck of cards (SCRUM-19).

A lesson's content is one JSON document, `{"cards": [...]}`, stored on the lesson as its
working draft and copied into `lesson_versions` each time it is published. The same shape
is what the admin portal edits and what `content/` lesson files hold, so everything that
decides what a valid lesson is lives here:

- the models, which say what a document may contain. A save is refused (422) only when a
  document is malformed or too large; a draft may be incomplete.
- `issues()`, which says what still stops a lesson being published (blockers) and what is
  worth a second look (warnings). The admin portal shows these; it never repeats the rules.
- `stats()`, the counts and reading time the editor shows.

Every card has a `type` and every question has a `type`, so later formats (chat threads,
hotspot scenes, comic panels; ordering or matching questions) are new kinds of card or
question in the same deck rather than a different kind of lesson.

Cards, questions and options carry short ids that stay the same across edits, so a learner's
answers can always name the question they answered. Missing ids are filled in on save.
"""

import re
import secrets
import string
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# --- The document --------------------------------------------------------------------------

MAX_CARDS = 30
MAX_OPTIONS = 4
MAX_CARD_TEXT = 1_500
MAX_OPTION_TEXT = 160
MAX_WHY_NOT = 400
MAX_EXPLANATION = 800
MAX_ALT = 300
MAX_TRANSCRIPT = 1_000

ShortId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,40}$")]


class _Strict(BaseModel):
    # A typo in a hand-written lesson file ("explaination") is refused rather than dropped.
    model_config = ConfigDict(extra="forbid")


class Option(_Strict):
    id: ShortId | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_OPTION_TEXT)] = ""
    correct: bool = False
    # Shown when a learner picks this option and it is wrong: why it is not the norm.
    why_not: Annotated[str, Field(max_length=MAX_WHY_NOT)] = ""


class ChoiceQuestion(_Strict):
    """Pick one option. With a single option it is a tap to fill the blank: it keeps the
    learner doing something, and is left out of the score."""

    type: Literal["choice"] = "choice"
    id: ShortId | None = None
    options: list[Option] = Field(default_factory=list, max_length=MAX_OPTIONS)
    # Shown after answering, right or wrong.
    explanation: Annotated[str, Field(max_length=MAX_EXPLANATION)] = ""
    # Whether learners see the options in a random order. Off for options with a natural
    # order, such as "Once / Twice / Three times".
    shuffle: bool = True


# A union of question types once there is more than one, discriminated by `type`.
Question = ChoiceQuestion


class ImageRef(_Strict):
    asset_id: uuid.UUID
    alt: Annotated[str, Field(max_length=MAX_ALT)] = ""


class AudioRef(_Strict):
    asset_id: uuid.UUID
    transcript: Annotated[str, Field(max_length=MAX_TRANSCRIPT)] = ""


class StoryCard(_Strict):
    """Optional image and audio, then text in Markdown, then optionally a question.

    The text may hold one `{{blank}}`, which the question's answer fills.
    """

    type: Literal["story"] = "story"
    id: ShortId | None = None
    text: Annotated[str, Field(max_length=MAX_CARD_TEXT)] = ""
    image: ImageRef | None = None
    audio: AudioRef | None = None
    question: Question | None = None


# A union of card types once there is more than one, discriminated by `type`.
Card = StoryCard


class LessonDoc(_Strict):
    cards: list[Card] = Field(default_factory=list, max_length=MAX_CARDS)


EMPTY_DOC: dict = {"cards": []}

# --- Ids -----------------------------------------------------------------------------------

_ID_ALPHABET = string.ascii_letters + string.digits


def new_id(length: int = 8) -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(length))


class DuplicateIdError(ValueError):
    def __init__(self, duplicate: str):
        super().__init__(f'The id "{duplicate}" is used more than once in this lesson.')
        self.duplicate = duplicate


def _parts_with_ids(doc: LessonDoc) -> Iterator[tuple[str, Card | Question | Option]]:
    """Every part that carries an id, with a path that names it (for generated ids)."""
    for n, card in enumerate(doc.cards):
        yield f"c{n}", card
        if card.question is not None:
            yield f"c{n}q", card.question
            for m, option in enumerate(card.question.options):
                yield f"c{n}q{m}", option


def assign_ids(doc: LessonDoc, make_id: Callable[[str], str] | None = None) -> LessonDoc:
    """Fill in missing ids and refuse duplicates. Changes `doc` in place and returns it.

    `make_id(path)` makes an id for the part at `path` ("c2q1" is card 2's option 1). The
    importer passes one derived from the lesson's key, so importing the same file twice
    gives the same ids; everywhere else ids are random.
    """
    seen: set[str] = set()
    for _, part in _parts_with_ids(doc):
        if part.id is not None:
            if part.id in seen:
                raise DuplicateIdError(part.id)
            seen.add(part.id)
    for path, part in _parts_with_ids(doc):
        if part.id is None:
            candidate = make_id(path) if make_id else new_id()
            while candidate in seen:
                candidate = new_id()
            part.id = candidate
            seen.add(candidate)
    return doc


def dump(doc: LessonDoc) -> dict:
    """The document as stored: JSON-ready, with every field present, so two documents that
    say the same thing compare equal."""
    return doc.model_dump(mode="json")


# --- Text ----------------------------------------------------------------------------------

# The admin portal's renderer uses the same pattern (packages/ui/src/lesson/blank.ts).
BLANK = re.compile(r"\{\{\s*blank\s*\}\}")
BLANK_TOKEN = "{{blank}}"

# Words as a reader sees them, as in the admin portal's reading-time estimate: most Markdown
# syntax has no letters or digits, so it is never counted.
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_LIST_NUMBER = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")

WORDS_PER_MINUTE = 200
READING_LIMIT_SECONDS = 120
CARD_WORD_LIMIT = 50
AUDIO_LENGTH_LIMIT_MS = 20_000


def count_blanks(text: str) -> int:
    return len(BLANK.findall(text))


def count_words(markdown: str) -> int:
    visible = _LINK.sub(r"\1", _LIST_NUMBER.sub("", BLANK.sub(" ", markdown)))
    return len(_WORD.findall(visible))


def correct_option(question: ChoiceQuestion) -> Option | None:
    """The option that is right. A question with one option needs no marking: that option
    is the answer."""
    marked = [option for option in question.options if option.correct]
    if len(marked) == 1:
        return marked[0]
    if not marked and len(question.options) == 1:
        return question.options[0]
    return None


def is_scored(question: ChoiceQuestion) -> bool:
    """Only a real choice counts toward a score; a one-option tap always succeeds."""
    return len(question.options) >= 2


# --- What the editor shows -----------------------------------------------------------------


@dataclass(frozen=True)
class MediaFacts:
    """What issues() and stats() need to know about an image or audio file."""

    kind: str
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class Issue:
    severity: Literal["blocker", "warning"]
    code: str
    message: str
    card_id: str | None = None
    # The field on the card it is about: "text", "image", "audio", "question",
    # "question.explanation", "question.options", or "question.options.<option id>".
    field: str | None = None


@dataclass(frozen=True)
class Stats:
    cards: int
    questions: int
    scored_questions: int
    words: int
    audio_seconds: int
    reading_seconds: int


def _card_words(card: Card) -> int:
    words = count_words(card.text)
    if card.question is not None:
        words += sum(count_words(option.text) for option in card.question.options)
        words += count_words(card.question.explanation)
    return words


def stats(doc: LessonDoc, media: dict[uuid.UUID, MediaFacts] | None = None) -> Stats:
    """Counts for the editor's header. Reading time covers everything a learner reads,
    including options and explanations, plus the length of any audio."""
    media = media or {}
    questions = [card.question for card in doc.cards if card.question is not None]
    words = sum(_card_words(card) for card in doc.cards)
    audio_ms = 0
    for card in doc.cards:
        if card.audio is not None:
            facts = media.get(card.audio.asset_id)
            audio_ms += (facts.duration_ms or 0) if facts else 0
    audio_seconds = round(audio_ms / 1000)
    return Stats(
        cards=len(doc.cards),
        questions=len(questions),
        scored_questions=sum(1 for question in questions if is_scored(question)),
        words=words,
        audio_seconds=audio_seconds,
        reading_seconds=round(words / WORDS_PER_MINUTE * 60) + audio_seconds,
    )


def issues(
    doc: LessonDoc,
    *,
    title: str,
    has_topic: bool,
    topic_archived: bool = False,
    media: dict[uuid.UUID, MediaFacts] | None = None,
) -> list[Issue]:
    """Everything that stops this lesson being published (blockers), then everything worth
    a second look (warnings), in the order the editor shows them: lesson first, then card
    by card."""
    media = media or {}
    found: list[Issue] = []

    def blocker(code: str, message: str, card: Card | None = None, field: str | None = None):
        found.append(Issue("blocker", code, message, card.id if card else None, field))

    def warning(code: str, message: str, card: Card | None = None, field: str | None = None):
        found.append(Issue("warning", code, message, card.id if card else None, field))

    if not title.strip():
        blocker("missing_title", "Give the lesson a title.")
    if not has_topic:
        blocker("missing_topic", "Choose a topic. Every published lesson belongs to one.")
    elif topic_archived:
        warning(
            "topic_archived",
            "This topic is archived, so users won't see the lesson until it is restored.",
        )
    if not doc.cards:
        blocker("no_cards", "Add at least one card.")
    elif not any(card.question is not None for card in doc.cards):
        blocker("no_questions", "Add a question to at least one card.")

    for card in doc.cards:
        _card_issues(card, media, blocker, warning)

    reading = stats(doc, media).reading_seconds
    if reading > READING_LIMIT_SECONDS:
        minutes = -(-reading // 60)
        warning(
            "long_lesson",
            f"Lessons should take under 2 minutes. This one takes about {minutes}.",
        )
    # Blockers first, keeping each group in order.
    return sorted(found, key=lambda issue: issue.severity != "blocker")


def _card_issues(card: Card, media, blocker, warning) -> None:
    blanks = count_blanks(card.text)
    if not card.text.strip() or (blanks and not BLANK.sub("", card.text).strip()):
        blocker("card_text_missing", "Write the card's text.", card, "text")
    elif count_words(card.text) > CARD_WORD_LIMIT:
        warning(
            "card_text_long",
            f"Cards read best under {CARD_WORD_LIMIT} words. Consider splitting this one.",
            card,
            "text",
        )
    if blanks > 1:
        blocker("too_many_blanks", "A card can have only one blank.", card, "text")
    if blanks and card.question is None:
        blocker("blank_without_question", "Add a question to fill this card's blank.", card, "text")

    if card.image is not None:
        facts = media.get(card.image.asset_id)
        if facts is None or facts.kind != "image":
            blocker(
                "image_missing", "This image is no longer available. Choose another.", card, "image"
            )
        else:
            if not card.image.alt.strip():
                warning(
                    "image_alt_missing",
                    "Describe the image for people who can't see it.",
                    card,
                    "image",
                )
            if facts.width and facts.height and not 1.2 <= facts.width / facts.height <= 1.5:
                warning(
                    "image_shape",
                    "Images look best at 4:3. This one will be shown whole, with space around it.",
                    card,
                    "image",
                )
    if card.audio is not None:
        facts = media.get(card.audio.asset_id)
        if facts is None or facts.kind != "audio":
            blocker(
                "audio_missing", "This audio is no longer available. Choose another.", card, "audio"
            )
        else:
            if not card.audio.transcript.strip():
                warning(
                    "audio_transcript_missing",
                    "Add a transcript for people who can't listen.",
                    card,
                    "audio",
                )
            if (facts.duration_ms or 0) > AUDIO_LENGTH_LIMIT_MS:
                warning(
                    "audio_long",
                    "Card audio works best under 20 seconds.",
                    card,
                    "audio",
                )

    question = card.question
    if question is None:
        return
    if not question.options:
        blocker("question_no_options", "Add at least one option.", card, "question.options")
    for option in question.options:
        if not option.text:
            blocker(
                "option_text_missing",
                "Write this option, or remove it.",
                card,
                f"question.options.{option.id}",
            )
    marked = sum(1 for option in question.options if option.correct)
    if len(question.options) >= 2 and marked == 0:
        blocker("question_no_correct", "Mark the correct option.", card, "question.options")
    elif marked > 1:
        blocker(
            "question_many_correct", "Mark only one option as correct.", card, "question.options"
        )
    texts = [option.text.casefold() for option in question.options if option.text]
    if len(texts) != len(set(texts)):
        # Each option must be a distinct answer (SCRUM-15 AC6).
        blocker(
            "option_duplicate",
            "Two options say the same thing. Make each one a different answer.",
            card,
            "question.options",
        )
    if not question.explanation.strip():
        blocker(
            "question_explanation_missing",
            "Explain the answer. Learners see this after answering.",
            card,
            "question.explanation",
        )
