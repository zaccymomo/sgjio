"""Images and audio for lesson cards.

Placeholder until media storage arrives: lessons cannot refer to images or audio yet.
"""

import uuid

from sqlalchemy.orm import Session

from app.lesson_doc import LessonDoc, MediaFacts


class MediaReferenceError(ValueError):
    """A card refers to an image or audio file that does not exist, or is the wrong kind."""


def check_references(db: Session, doc: LessonDoc) -> None:
    for card in doc.cards:
        if card.image is not None or card.audio is not None:
            raise MediaReferenceError("Images and audio are not available yet.")


def facts_for(db: Session, doc: LessonDoc) -> dict[uuid.UUID, MediaFacts]:
    return {}


def assets_for(db: Session, doc: LessonDoc) -> dict:
    return {}
