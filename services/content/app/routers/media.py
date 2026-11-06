"""Serving lesson images and audio (SCRUM-19).

Public on purpose: asset ids cannot be guessed, lesson media is not private, and one
address then works in both front ends, whose sessions are kept separate. Files never change
once stored, so browsers may keep them for good.
"""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app import media
from app.db import get_db

router = APIRouter()

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CACHE_FOREVER = "public, max-age=31536000, immutable"


@router.get(
    "/media/{asset_id}",
    responses={
        200: {"description": "The file"},
        206: {"description": "Part of the file, for a Range request"},
        304: {"description": "Unchanged since the copy the browser has"},
        404: {"description": "No file with that id"},
    },
)
def get_media(asset_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> Response:
    """An image or audio file. Supports one byte range, so audio can be scrubbed."""
    asset = media.get_file(db, asset_id)
    if asset is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "media_not_found", "message": "That file no longer exists."},
        )
    etag = f'"{asset.sha256}"'
    headers = {
        "Cache-Control": CACHE_FOREVER,
        "ETag": etag,
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    data, size = asset.data, len(asset.data)
    match = _RANGE.match(request.headers.get("range", "").strip())
    if match and (match[1] or match[2]):
        if match[1]:
            start = int(match[1])
            end = min(int(match[2]), size - 1) if match[2] else size - 1
        else:  # "bytes=-500": the last 500 bytes
            start, end = max(size - int(match[2]), 0), size - 1
        if start >= size or start > end:
            return Response(
                status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
                headers={**headers, "Content-Range": f"bytes */{size}"},
            )
        return Response(
            data[start : end + 1],
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type=asset.mime,
            headers={**headers, "Content-Range": f"bytes {start}-{end}/{size}"},
        )
    return Response(data, media_type=asset.mime, headers=headers)
