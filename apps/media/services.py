"""Media processing and storage.

Binaries go to the configured Django storage (local disk or S3-compatible);
only metadata and storage keys are written to MongoDB.
"""
from __future__ import annotations

import io
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from PIL import Image, ImageOps

from apps.core.dates import today
from apps.core.repository import repo

from .validation import UploadError, validate_image, validate_video

EPHEMERAL_MESSAGE = (
    "Uploads are switched off because this deployment has no permanent file storage. "
    "Set MEDIA_STORAGE_PROVIDER=s3 and the AWS_* variables (S3 or Cloudflare R2), then redeploy."
)


def _require_permanent_storage() -> None:
    if settings.MEDIA_EPHEMERAL:
        raise UploadError(EPHEMERAL_MESSAGE)


THUMB_SIZES = {"thumb": 480, "medium": 1280}

# Fields elsewhere that reference photos/videos by id.
PHOTO_LIST_REFS = [("timeline_events", "photo_ids"), ("memories", "photo_ids"), ("places", "photo_ids")]
PHOTO_SINGLE_REFS = [
    ("letters", "photo_id"),
    ("gifts", "photo_id"),
    ("future_plans", "completion_photo_id"),
    ("videos", "poster_photo_id"),
]
VIDEO_LIST_REFS = [("timeline_events", "video_ids"), ("memories", "video_ids")]


def _key(folder: str, suffix: str) -> str:
    d = today()
    return f"{folder}/{d.year}/{d.month:02d}/{uuid.uuid4().hex}{suffix}"


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    elif fmt == "PNG":
        img.save(buf, "PNG", optimize=True)
    else:
        img.save(buf, "WEBP", quality=88, method=4)
    return buf.getvalue()


def _variant(img: Image.Image, max_side: int) -> bytes:
    copy = img.copy()
    copy.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if copy.mode not in ("RGB", "RGBA"):
        copy = copy.convert("RGBA" if "A" in copy.getbands() else "RGB")
    buf = io.BytesIO()
    copy.save(buf, "WEBP", quality=82, method=4)
    return buf.getvalue()


def store_photo(upload, metadata: dict | None = None) -> dict:
    """Validate, strip metadata (EXIF/GPS), create thumbnails and save a photo document."""
    _require_permanent_storage()
    info = validate_image(upload)
    with Image.open(upload) as raw:
        img = ImageOps.exif_transpose(raw)
        img.load()
    # Re-encoding drops EXIF, GPS and any other embedded metadata.
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[info.format]
    base = _key("photos", "")
    keys = {
        "storage_key": default_storage.save(base + ext, ContentFile(_encode(img, info.format))),
        "thumb_key": default_storage.save(base + "_480.webp", ContentFile(_variant(img, THUMB_SIZES["thumb"]))),
        "medium_key": default_storage.save(base + "_1280.webp", ContentFile(_variant(img, THUMB_SIZES["medium"]))),
    }
    width, height = img.size
    doc = {
        **keys,
        "original_name": (upload.name or "")[:200],
        "content_type": info.content_type,
        "size": upload.size,
        "width": width,
        "height": height,
        "caption": "",
        "date": "",
        "location": {"name": "", "city": "", "country": ""},
        "tags": [],
        "is_public": False,
        "is_published": True,
        **(metadata or {}),
    }
    doc_id = repo("photos").insert(doc)
    return repo("photos").get(doc_id)


def store_video(upload, metadata: dict | None = None) -> dict:
    _require_permanent_storage()
    content_type = validate_video(upload)
    ext = ".mp4" if content_type == "video/mp4" else ".webm"
    key = default_storage.save(_key("videos", ext), upload)
    doc = {
        "storage_key": key,
        "external_url": "",
        "original_name": (upload.name or "")[:200],
        "content_type": content_type,
        "size": upload.size,
        "title": "",
        "caption": "",
        "date": "",
        "poster_photo_id": "",
        "location": {"name": "", "city": "", "country": ""},
        "tags": [],
        "is_public": False,
        "is_published": True,
        **(metadata or {}),
    }
    doc_id = repo("videos").insert(doc)
    return repo("videos").get(doc_id)


def _delete_keys(*keys: str) -> None:
    for key in keys:
        if key:
            try:
                default_storage.delete(key)
            except Exception:  # pragma: no cover - storage errors must not block deletion
                pass


def delete_photo(photo_id: str) -> bool:
    photo = repo("photos").get(photo_id)
    if not photo:
        return False
    _delete_keys(photo.get("storage_key"), photo.get("thumb_key"), photo.get("medium_key"))
    for collection, field in PHOTO_LIST_REFS:
        repo(collection).pull_reference(field, photo_id)
    for collection, field in PHOTO_SINGLE_REFS:
        repo(collection).col.update_many({field: photo_id}, {"$set": {field: ""}})
    return repo("photos").delete(photo_id)


def delete_video(video_id: str) -> bool:
    video = repo("videos").get(video_id)
    if not video:
        return False
    _delete_keys(video.get("storage_key"))
    for collection, field in VIDEO_LIST_REFS:
        repo(collection).pull_reference(field, video_id)
    return repo("videos").delete(video_id)


def media_url(key: str | None) -> str:
    return reverse("media:serve", args=[key]) if key else ""


def photo_urls(photo: dict | None) -> dict:
    if not photo:
        return {}
    return {
        "thumb": media_url(photo.get("thumb_key") or photo.get("storage_key")),
        "medium": media_url(photo.get("medium_key") or photo.get("storage_key")),
        "original": media_url(photo.get("storage_key")),
    }


def attach_photo_urls(photos: list[dict]) -> list[dict]:
    for p in photos:
        p["urls"] = photo_urls(p)
    return photos


def video_src(video: dict | None) -> str:
    if not video:
        return ""
    return video.get("external_url") or media_url(video.get("storage_key"))
