"""Content's lesson document rules, copied for the tests only (api/app/lesson_doc.py).

The tests stand in for Content: they take the short documents the monolith's tests wrote,
fill them in as Content stores them (`dump`), and work out what
`content.lesson_version.published` carries (questions, reading time, plain text). The
Learning service itself never imports this.
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


_LIST_BULLET = re.compile(r"^\s*[-+*]\s+", re.MULTILINE)
_MARKERS = re.compile(r"[*_`~#>]+")


def plain_text(markdown: str) -> str:
    """Card text as a reader sees it, on one line, for learners' search (SCRUM-85): list
    markers, emphasis and link syntax dropped, and the blank shown as ___. So "**chope** lah"
    reads "chope lah"."""
    text = _LINK.sub(r"\1", _LIST_NUMBER.sub("", _LIST_BULLET.sub("", markdown)))
    # The blank is set aside first, or its underscores would be stripped as emphasis.
    text = _MARKERS.sub("", BLANK.sub("\0", text))
    return " ".join(text.replace("\0", "___").split())


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
