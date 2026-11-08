"""Reading a published lesson deck (contracts/events/content.lesson_version.published).

A tolerant reader, written from the contract rather than copied from Content's
lesson_doc.py: it takes the fields Learning uses, fills in what is missing with the
contract's meaning, and ignores anything it does not know, so Content can add a field
without breaking Learning.

What lesson_doc.is_scored and lesson_doc.correct_option used to work out arrives ready in
the deck's `questions`, so Learning holds none of Content's document rules.
"""

import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field


class _Tolerant(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Option(_Tolerant):
    id: str = ""
    text: str = ""
    correct: bool = False
    why_not: str = ""


class Question(_Tolerant):
    type: str = "choice"
    id: str = ""
    options: list[Option] = Field(default_factory=list)
    explanation: str = ""
    shuffle: bool = True


class ImageRef(_Tolerant):
    asset_id: uuid.UUID
    alt: str = ""


class AudioRef(_Tolerant):
    asset_id: uuid.UUID
    transcript: str = ""


class Card(_Tolerant):
    type: str = "story"
    id: str = ""
    text: str = ""
    image: ImageRef | None = None
    audio: AudioRef | None = None
    question: Question | None = None


class Doc(_Tolerant):
    cards: list[Card] = Field(default_factory=list)


@dataclass(frozen=True)
class QuestionFacts:
    """What Content worked out for one question (`questions[]` in the event)."""

    scored: bool
    correct_option_id: str


@dataclass
class Deck:
    """A deck's document plus the facts about each question, by question id."""

    doc: Doc
    facts: dict[str, QuestionFacts] = field(default_factory=dict)

    @property
    def questions(self) -> list[Question]:
        return [card.question for card in self.doc.cards if card.question is not None]

    def is_scored(self, question: Question) -> bool:
        """Only a real choice counts toward a score; a one-option tap always succeeds."""
        facts = self.facts.get(question.id)
        return facts.scored if facts else len(question.options) >= 2

    def correct_option(self, question: Question) -> Option | None:
        """The option that is right, as Content marked it."""
        facts = self.facts.get(question.id)
        if facts is not None:
            return next((o for o in question.options if o.id == facts.correct_option_id), None)
        marked = [option for option in question.options if option.correct]
        if len(marked) == 1:
            return marked[0]
        if not marked and len(question.options) == 1:
            return question.options[0]
        return None


def read(doc: dict, questions: list | None = None) -> Deck:
    facts = {
        item["question_id"]: QuestionFacts(
            scored=bool(item.get("scored", True)),
            correct_option_id=str(item.get("correct_option_id", "")),
        )
        for item in questions or []
        if isinstance(item, dict) and "question_id" in item
    }
    return Deck(doc=Doc.model_validate(doc), facts=facts)


def of(row) -> Deck:
    """The deck of a `LessonDeck` row."""
    return read(row.doc, row.questions)
