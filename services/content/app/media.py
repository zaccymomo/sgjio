"""Images and audio for lesson cards (SCRUM-19).

Files are uploaded by administrators, processed once, and stored in the database
(models.MediaAsset). Lesson documents refer to them by id; every lesson the API returns
carries an `assets` map with what a page needs to show them, so neither front end has to
look anything up separately.

- images: JPEG (including the "MPO" kind many cameras write), PNG or WebP. Turned the right way
  up, stripped of EXIF data (which can hold where a photo was taken), shrunk to at most 1600px
  wide and stored as WebP, with a tiny blurred placeholder and the image's main colour.
- audio: MP3, M4A (AAC), WAV or Ogg, stored as uploaded. Its length is read from the file.
- uploading a file that is already stored returns the stored asset rather than a copy.
- files are served publicly at /api/media/{id}: the ids cannot be guessed, lesson media is
  not private, and a public address works in both front ends, whose sessions are separate.
"""

import base64
import colorsys
import hashlib
import io
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import mutagen
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.config import get_settings
from app.lesson_doc import LessonDoc, MediaFacts
from app.models import Lesson, LessonVersion, MediaAsset, MediaKind
from app.problems import ContentProblem

MAX_IMAGE_WIDTH = 1600
WEBP_QUALITY = 82
PLACEHOLDER_WIDTH = 24
# Refuse images that would take too much memory to open (a "decompression bomb").
Image.MAX_IMAGE_PIXELS = 60_000_000

# Pillow calls a camera JPEG with extra embedded frames (e.g. Nikon, Samsung) "MPO"; it opens
# as a normal JPEG and its first frame is the photo.
IMAGE_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
# Image formats we recognise but do not accept, so the error can name them.
_HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis"}
AUDIO_TYPES = {
    "MP3": "audio/mpeg",
    "MP4": "audio/mp4",
    "WAVE": "audio/wav",
    "OggOpus": "audio/ogg",
    "OggVorbis": "audio/ogg",
}


class MediaReferenceError(ValueError):
    """A card refers to an image or audio file that does not exist, or is the wrong kind."""


def _unsupported(other_image: str | None = None) -> ContentProblem:
    """`other_image` names an image format we recognised but do not accept, e.g. "HEIC"."""
    if other_image:
        message = f"That looks like a {other_image} image. Save it as a JPEG, PNG or WebP image."
    else:
        message = "Upload a JPEG, PNG or WebP image, or MP3, M4A, WAV or Ogg audio."
    return ContentProblem("media_unsupported", message, 415)


def _too_large(what: str, limit: str) -> ContentProblem:
    return ContentProblem(
        "media_too_large", f"That {what} is too large. The limit is {limit}.", 413
    )


@dataclass(frozen=True)
class Asset:
    """An asset as both front ends receive it (schemas.AssetOut)."""

    id: uuid.UUID
    kind: MediaKind
    mime: str
    size: int
    width: int | None
    height: int | None
    duration_ms: int | None
    placeholder: str | None
    color: str | None
    filename: str

    @property
    def url(self) -> str:
        return f"/api/media/{self.id}"


def _asset(row: MediaAsset) -> Asset:
    return Asset(
        id=row.id,
        kind=row.kind,
        mime=row.mime,
        size=row.size,
        width=row.width,
        height=row.height,
        duration_ms=row.duration_ms,
        placeholder=row.placeholder,
        color=row.color,
        filename=row.filename,
    )


# --- Processing ----------------------------------------------------------------------------


def _main_colour(image: Image.Image) -> str:
    """The most common colour that is neither washed out nor near black or white, so a flat
    illustration on a white background gives its own colour rather than white."""
    small = image.convert("RGB")
    small.thumbnail((64, 64))
    counts = small.quantize(colors=8).convert("RGB").getcolors(64 * 64) or []
    for _, (r, g, b) in sorted(counts, reverse=True):
        _, lightness, saturation = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if saturation > 0.2 and 0.15 < lightness < 0.85:
            return f"#{r:02x}{g:02x}{b:02x}"
    r, g, b = small.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


def _webp(image: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    image.save(out, "WEBP", quality=quality, method=6)
    return out.getvalue()


def _process_image(data: bytes) -> dict:
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in IMAGE_FORMATS:
            raise _unsupported(image.format)
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise ContentProblem(
            "media_unreadable", "That image could not be opened. Try saving it again.", 422
        ) from None
    image = ImageOps.exif_transpose(image)
    has_alpha = image.mode in ("RGBA", "LA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    if image.width > MAX_IMAGE_WIDTH:
        image = image.resize(
            (MAX_IMAGE_WIDTH, round(image.height * MAX_IMAGE_WIDTH / image.width)),
            Image.Resampling.LANCZOS,
        )
    tiny = image.copy()
    tiny.thumbnail((PLACEHOLDER_WIDTH, PLACEHOLDER_WIDTH * 4))
    placeholder = base64.b64encode(_webp(tiny, 40)).decode()
    return {
        "kind": MediaKind.IMAGE,
        "mime": "image/webp",
        "data": _webp(image, WEBP_QUALITY),  # saved without EXIF
        "width": image.width,
        "height": image.height,
        "placeholder": f"data:image/webp;base64,{placeholder}",
        "color": _main_colour(image),
    }


def _process_audio(data: bytes, audio: mutagen.FileType) -> dict:
    mime = AUDIO_TYPES.get(type(audio).__name__)
    if mime is None:
        raise _unsupported()
    duration_ms = round(audio.info.length * 1000)
    limit = get_settings().media_max_audio_seconds
    if duration_ms > limit * 1000:
        raise _too_large("recording", f"{limit} seconds")
    return {"kind": MediaKind.AUDIO, "mime": mime, "data": data, "duration_ms": duration_ms}


def _looks_like_image(data: bytes) -> bool:
    return data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")) or (
        data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    )


def _other_image_format(data: bytes) -> str | None:
    """The name of an image format we do not accept, if the file is one."""
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "GIF"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIC_BRANDS:
        return "HEIC"
    return None


def store(db: Session, data: bytes, filename: str, created_by: uuid.UUID | None) -> Asset:
    """Process and keep an uploaded file, or return the stored asset if it is the same file.

    Raises a ContentProblem if the file is not a supported image or audio file, is damaged,
    or is over the size limits in the settings.
    """
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(MediaAsset).options(load_only(*_INFO_COLUMNS)).where(MediaAsset.sha256 == digest)
    )
    if existing is not None:
        return _asset(existing)

    settings = get_settings()
    if _looks_like_image(data):
        if len(data) > settings.media_max_image_mb * 1024 * 1024:
            raise _too_large("image", f"{settings.media_max_image_mb} MB")
        processed = _process_image(data)
    else:
        try:
            audio = mutagen.File(io.BytesIO(data))
        except mutagen.MutagenError:
            audio = None
        if audio is None or getattr(audio, "info", None) is None:
            raise _unsupported(_other_image_format(data))
        if len(data) > settings.media_max_audio_mb * 1024 * 1024:
            raise _too_large("recording", f"{settings.media_max_audio_mb} MB")
        processed = _process_audio(data, audio)

    row = MediaAsset(
        sha256=digest,
        size=len(processed["data"]),
        filename=filename[:255],
        created_by=created_by,
        **processed,
    )
    db.add(row)
    db.commit()
    return _asset(row)


def largest_upload_bytes() -> int:
    settings = get_settings()
    return max(settings.media_max_image_mb, settings.media_max_audio_mb) * 1024 * 1024


# --- What lessons use ----------------------------------------------------------------------

_INFO_COLUMNS = (
    MediaAsset.id,
    MediaAsset.kind,
    MediaAsset.mime,
    MediaAsset.sha256,
    MediaAsset.size,
    MediaAsset.width,
    MediaAsset.height,
    MediaAsset.duration_ms,
    MediaAsset.placeholder,
    MediaAsset.color,
    MediaAsset.filename,
)


def referenced_ids(doc: LessonDoc) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for card in doc.cards:
        if card.image is not None:
            ids.add(card.image.asset_id)
        if card.audio is not None:
            ids.add(card.audio.asset_id)
    return ids


def _rows(db: Session, ids: set[uuid.UUID]) -> list[MediaAsset]:
    if not ids:
        return []
    return list(
        db.scalars(
            select(MediaAsset).options(load_only(*_INFO_COLUMNS)).where(MediaAsset.id.in_(ids))
        )
    )


def check_references(db: Session, doc: LessonDoc) -> None:
    """Refuse a document whose cards use files that do not exist or are the wrong kind."""
    kinds = {row.id: row.kind for row in _rows(db, referenced_ids(doc))}
    for card in doc.cards:
        if card.image is not None and kinds.get(card.image.asset_id) != MediaKind.IMAGE:
            raise MediaReferenceError(f"There is no image with the id {card.image.asset_id}.")
        if card.audio is not None and kinds.get(card.audio.asset_id) != MediaKind.AUDIO:
            raise MediaReferenceError(f"There is no audio with the id {card.audio.asset_id}.")


def facts_for(db: Session, doc: LessonDoc) -> dict[uuid.UUID, MediaFacts]:
    return {
        row.id: MediaFacts(row.kind.value, row.width, row.height, row.duration_ms)
        for row in _rows(db, referenced_ids(doc))
    }


def assets_for(db: Session, doc: LessonDoc) -> dict[str, Asset]:
    return {str(row.id): _asset(row) for row in _rows(db, referenced_ids(doc))}


def get_file(db: Session, asset_id: uuid.UUID) -> MediaAsset | None:
    """The asset with its file loaded, for serving."""
    return db.get(MediaAsset, asset_id, options=[load_only(*_INFO_COLUMNS, MediaAsset.data)])


def prune(db: Session, older_than: timedelta = timedelta(days=1)) -> int:
    """Delete files that no lesson draft or published version uses. Returns how many.

    Files a published version uses are always kept, since learners' history shows them.
    Recent uploads are kept too: an administrator may not have saved the card using it yet.
    """
    used: set[uuid.UUID] = set()
    for doc in [*db.scalars(select(Lesson.draft)), *db.scalars(select(LessonVersion.doc))]:
        used |= referenced_ids(LessonDoc.model_validate(doc))
    cutoff = datetime.now(UTC) - older_than
    candidates = db.scalars(
        select(MediaAsset).options(load_only(MediaAsset.id)).where(MediaAsset.created_at < cutoff)
    )
    unused = [row for row in candidates if row.id not in used]
    for row in unused:
        db.delete(row)
    db.commit()
    return len(unused)
