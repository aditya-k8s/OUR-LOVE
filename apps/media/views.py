"""Access-checked media delivery.

Local storage: the file is streamed after the access check (with HTTP Range
support so videos can seek). S3 storage: the viewer is redirected to a
short-lived pre-signed URL. Unknown or private keys return 404 so that the
existence of a file is never revealed.
"""
from __future__ import annotations

import mimetypes
import re

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.views.decorators.http import require_GET

from apps.core.repository import can_see_private, repo

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 64 * 1024


def _find_owner(key: str) -> dict | None:
    photo = repo("photos").find_one({"$or": [{"storage_key": key}, {"thumb_key": key}, {"medium_key": key}]})
    if photo:
        return photo
    return repo("videos").find_one({"storage_key": key})


def _allowed(request, owner: dict) -> bool:
    if can_see_private(request):
        return True
    return settings.PUBLIC_SITE_ENABLED and owner.get("is_public") is True and owner.get("is_published") is not False


def _file_iter(handle, start: int, length: int):
    handle.seek(start)
    remaining = length
    try:
        while remaining > 0:
            chunk = handle.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        handle.close()


@require_GET
def serve(request, key: str):
    if ".." in key or key.startswith("/"):
        raise Http404
    owner = _find_owner(key)
    if not owner or not _allowed(request, owner):
        raise Http404

    if settings.MEDIA_STORAGE_PROVIDER == "s3":
        response = HttpResponseRedirect(default_storage.url(key))
        response["Cache-Control"] = "private, no-store"
        return response

    if not default_storage.exists(key):
        raise Http404
    content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    size = default_storage.size(key)
    range_header = request.headers.get("Range", "")
    match = RANGE_RE.fullmatch(range_header.strip()) if range_header else None

    if match and (match.group(1) or match.group(2)):
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            start = max(size - int(last), 0)
            end = size - 1
        if start > end or start >= size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        length = end - start + 1
        response = StreamingHttpResponse(
            _file_iter(default_storage.open(key, "rb"), start, length), status=206, content_type=content_type
        )
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(length)
    else:
        response = FileResponse(default_storage.open(key, "rb"), content_type=content_type)
        response["Content-Length"] = str(size)

    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response
