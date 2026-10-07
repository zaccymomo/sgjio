"""SCRUM-19: images and audio for lesson cards: uploading, serving and using them."""

import io
import struct
import uuid
import wave
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

from app import media
from app.models import Lesson, LessonVersion, MediaAsset, UserRole

ADMIN = {"email": "admin@example.com", "password": "AdminPass123"}
USER = {"email": "user@example.com", "password": "Password123"}
UPLOAD = "/api/admin/media"


@pytest.fixture
def admin(client, make_user):
    make_user(ADMIN["email"], ADMIN["password"], role=UserRole.ADMIN)
    assert client.post("/api/admin/auth/sign-in", json=ADMIN).status_code == 200
    return client


def _png(width=800, height=600, colour=(230, 80, 90), alpha=False) -> bytes:
    background = (255, 255, 255, 0) if alpha else "white"  # transparent, or white
    image = Image.new("RGBA" if alpha else "RGB", (width, height), background)
    # A coloured block on white, like a flat illustration.
    image.paste(colour, (width // 4, height // 4, width * 3 // 4, height * 3 // 4))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (400, 300), (40, 120, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees to display
    exif[0x010F] = "Phone maker"
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()


def _mpo() -> bytes:
    """A camera JPEG with a second embedded frame: Pillow reports its format as MPO."""
    image = Image.new("RGB", (400, 300), (40, 120, 200))
    out = io.BytesIO()
    image.save(out, "MPO", save_all=True, append_images=[Image.new("RGB", (80, 60))])
    assert Image.open(io.BytesIO(out.getvalue())).format == "MPO"
    return out.getvalue()


def _wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(rate)
        recording.writeframes(struct.pack("<h", 0) * int(seconds * rate))
    return out.getvalue()


def _upload(
    client, data: bytes, name: str = "file", content_type: str = "application/octet-stream"
):
    return client.post(UPLOAD, files={"file": (name, data, content_type)})


# --- Uploading ----------------------------------------------------------------------------


def test_an_image_is_stored_as_webp_with_a_placeholder_and_colour(admin, db):
    response = _upload(admin, _png(), "stall.png", "image/png")

    assert response.status_code == 201
    asset = response.json()
    assert asset["kind"] == "image"
    assert asset["mime"] == "image/webp"
    assert (asset["width"], asset["height"]) == (800, 600)
    assert asset["duration_ms"] is None
    assert asset["placeholder"].startswith("data:image/webp;base64,")
    assert asset["color"] == "#e6505a"  # the illustration's colour, not its white background
    assert asset["filename"] == "stall.png"
    assert asset["url"] == f"/api/media/{asset['id']}"
    stored = db.get(MediaAsset, uuid.UUID(asset["id"]))
    assert Image.open(io.BytesIO(stored.data)).format == "WEBP"
    assert stored.size == len(stored.data)


def test_wide_images_are_shrunk_to_1600_pixels(admin):
    asset = _upload(admin, _png(3200, 2400)).json()
    assert (asset["width"], asset["height"]) == (1600, 1200)


def test_transparency_is_kept(admin, db):
    asset = _upload(admin, _png(alpha=True)).json()
    stored = db.get(MediaAsset, uuid.UUID(asset["id"]))
    assert Image.open(io.BytesIO(stored.data)).mode == "RGBA"


def test_photos_are_turned_upright_and_lose_their_exif(admin, db):
    asset = _upload(admin, _jpeg_with_exif(), "photo.jpg").json()

    assert (asset["width"], asset["height"]) == (300, 400)  # rotated
    stored = Image.open(io.BytesIO(db.get(MediaAsset, uuid.UUID(asset["id"])).data))
    assert not stored.getexif()


def test_a_camera_jpeg_with_extra_frames_is_accepted(admin):
    asset = _upload(admin, _mpo(), "DSC_0040.JPG", "image/jpeg")

    assert asset.status_code == 201
    assert (asset.json()["width"], asset.json()["height"]) == (400, 300)


def test_audio_is_stored_as_uploaded_with_its_length(admin, db):
    data = _wav(seconds=1.5)

    asset = _upload(admin, data, "kopi.wav", "audio/wav").json()

    assert asset["kind"] == "audio"
    assert asset["mime"] == "audio/wav"
    assert asset["duration_ms"] == 1500
    assert (asset["width"], asset["placeholder"], asset["color"]) == (None, None, None)
    assert db.get(MediaAsset, uuid.UUID(asset["id"])).data == data


def test_uploading_the_same_file_again_returns_the_stored_one(admin, db):
    first = _upload(admin, _png(), "a.png").json()
    second = _upload(admin, _png(), "b.png").json()

    assert second["id"] == first["id"]
    assert db.query(MediaAsset).count() == 1


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"just some text", 415, "media_unsupported"),
        (b"\x89PNG\r\n\x1a\n" + b"not really a png", 422, "media_unreadable"),
        (b"GIF89a" + b"\x00" * 20, 415, "media_unsupported"),
    ],
)
def test_files_that_are_not_supported_images_or_audio_are_refused(admin, db, data, status, code):
    response = _upload(admin, data)

    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert db.query(MediaAsset).count() == 0


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20, "HEIC"),
        (b"GIF89a" + b"\x00" * 20, "GIF"),
    ],
)
def test_other_image_formats_are_named_in_the_error(admin, data, name):
    response = _upload(admin, data)

    assert response.status_code == 415
    assert name in response.json()["detail"]["message"]


def test_files_over_the_limits_are_refused(admin, db, monkeypatch):
    monkeypatch.setattr(media, "largest_upload_bytes", lambda: 1000)
    response = _upload(admin, _png())
    assert (response.status_code, response.json()["detail"]["code"]) == (413, "media_too_large")


def test_audio_over_the_length_limit_is_refused(admin, db, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "media_max_audio_seconds", 1)
    response = _upload(admin, _wav(seconds=2))
    assert (response.status_code, response.json()["detail"]["code"]) == (413, "media_too_large")


def test_only_administrators_can_upload(client, make_user):
    assert _upload(client, _png()).status_code == 401
    make_user(**USER)
    client.post("/api/auth/sign-in", json=USER)
    assert _upload(client, _png()).status_code == 401


# --- Serving ------------------------------------------------------------------------------


def test_files_are_served_publicly_and_cached_for_good(admin, client):
    asset = _upload(admin, _wav()).json()
    admin.post("/api/admin/auth/sign-out")

    response = client.get(asset["url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.content == _wav()


def test_a_browser_with_the_file_gets_not_modified(admin):
    asset = _upload(admin, _png()).json()
    etag = admin.get(asset["url"]).headers["etag"]

    response = admin.get(asset["url"], headers={"If-None-Match": etag})

    assert response.status_code == 304


@pytest.mark.parametrize(
    ("header", "first", "last"),
    # Offsets from the end are negative, resolved against the file's size below.
    [("bytes=0-1", 0, 1), ("bytes=10-", 10, -1), ("bytes=-4", -4, -1)],
)
def test_byte_ranges(admin, header, first, last):
    data = _wav()
    asset = _upload(admin, data).json()
    first, last = first % len(data), last % len(data)

    response = admin.get(asset["url"], headers={"Range": header})

    assert response.status_code == 206
    assert response.content == data[first : last + 1]
    assert response.headers["content-range"] == f"bytes {first}-{last}/{len(data)}"


def test_a_range_past_the_end_is_refused(admin):
    asset = _upload(admin, _wav()).json()
    response = admin.get(asset["url"], headers={"Range": "bytes=999999-"})
    assert response.status_code == 416


def test_an_unknown_file_is_not_found(client):
    response = client.get(f"/api/media/{uuid.uuid4()}")
    assert (response.status_code, response.json()["detail"]["code"]) == (404, "media_not_found")


# --- Using media on cards -----------------------------------------------------------------


def test_a_card_with_an_image_and_audio(admin):
    image = _upload(admin, _png(1000, 1000)).json()
    audio = _upload(admin, _wav(seconds=2)).json()
    card = {
        "text": "Uncle says hello.",
        "image": {"asset_id": image["id"], "alt": ""},
        "audio": {"asset_id": audio["id"], "transcript": "Hello!"},
    }

    response = admin.post("/api/admin/lessons", json={"doc": {"cards": [card]}})

    assert response.status_code == 201
    body = response.json()
    assert set(body["assets"]) == {image["id"], audio["id"]}
    assert body["assets"][image["id"]] == image
    assert body["stats"]["audio_seconds"] == 2
    codes = [issue["code"] for issue in body["issues"]]
    assert "image_alt_missing" in codes and "image_shape" in codes
    [row] = admin.get("/api/admin/lessons").json()
    assert row["cover_asset_id"] == image["id"]


def test_a_card_cannot_use_audio_as_an_image(admin):
    audio = _upload(admin, _wav()).json()
    card = {"text": "Wrong kind", "image": {"asset_id": audio["id"]}}

    response = admin.post("/api/admin/lessons", json={"doc": {"cards": [card]}})

    assert response.status_code == 422
    assert "no image" in response.json()["detail"][0]["msg"]


def test_pruning_keeps_files_that_lessons_use(db, admin):
    used_by_draft = _upload(admin, _png(colour=(1, 2, 3))).json()
    used_by_version = _upload(admin, _png(colour=(4, 5, 6))).json()
    unused = _upload(admin, _png(colour=(7, 8, 9))).json()
    recent_unused = _upload(admin, _png(colour=(10, 11, 12))).json()
    lesson = Lesson(
        title="Uses media",
        draft={
            "cards": [
                {
                    "type": "story",
                    "id": "a",
                    "text": "x",
                    "image": {"asset_id": used_by_draft["id"], "alt": ""},
                    "audio": None,
                    "question": None,
                }
            ]
        },
    )
    lesson.versions.append(
        LessonVersion(
            number=1,
            title="Uses media",
            doc={
                "cards": [
                    {
                        "type": "story",
                        "id": "a",
                        "text": "x",
                        "image": {"asset_id": used_by_version["id"], "alt": ""},
                        "audio": None,
                        "question": None,
                    }
                ]
            },
            published_at=datetime.now(UTC),
        )
    )
    db.add(lesson)
    for row in db.query(MediaAsset).filter(MediaAsset.id != uuid.UUID(recent_unused["id"])):
        row.created_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()

    assert media.prune(db) == 1

    remaining = {str(row.id) for row in db.query(MediaAsset)}
    assert remaining == {used_by_draft["id"], used_by_version["id"], recent_unused["id"]}
    assert unused["id"] not in remaining
