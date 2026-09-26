"""Upload validation: extension allow-list, size limits and content sniffing."""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass

from django.conf import settings
from PIL import Image

IMAGE_EXTENSIONS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
IMAGE_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
VIDEO_EXTENSIONS = {"mp4": "video/mp4", "webm": "video/webm"}

# Refuse decompression bombs early (60 megapixels is far beyond any phone photo).
Image.MAX_IMAGE_PIXELS = 60_000_000


class UploadError(ValueError):
    """Raised with a user-facing message when an upload is rejected."""


@dataclass(frozen=True)
class ValidatedImage:
    format: str
    content_type: str
    width: int
    height: int


def _extension(name: str) -> str:
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def _check_size(upload, limit_mb: int) -> None:
    if upload.size is None or upload.size <= 0:
        raise UploadError("The file is empty.")
    if upload.size > limit_mb * 1024 * 1024:
        raise UploadError(f"The file is larger than the {limit_mb} MB limit.")


def validate_image(upload) -> ValidatedImage:
    ext = _extension(upload.name)
    if ext not in IMAGE_EXTENSIONS:
        raise UploadError("Only JPG, JPEG, PNG and WEBP images are allowed.")
    _check_size(upload, settings.MAX_IMAGE_UPLOAD_MB)
    try:
        upload.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as img:
                fmt = img.format
                width, height = img.size
                img.verify()
    except UploadError:
        raise
    except Exception as exc:  # Pillow raises many exception types for bad files
        raise UploadError("The file is not a valid image.") from exc
    finally:
        upload.seek(0)
    if fmt not in IMAGE_MIME:
        raise UploadError("The image format is not supported.")
    if IMAGE_EXTENSIONS[ext] != fmt:
        raise UploadError("The file extension does not match the image contents.")
    return ValidatedImage(fmt, IMAGE_MIME[fmt], width, height)


def validate_video(upload) -> str:
    ext = _extension(upload.name)
    if ext not in VIDEO_EXTENSIONS:
        raise UploadError("Only MP4 and WebM videos are allowed.")
    _check_size(upload, settings.MAX_VIDEO_UPLOAD_MB)
    upload.seek(0)
    head = upload.read(16)
    upload.seek(0)
    if ext == "mp4" and head[4:8] != b"ftyp":
        raise UploadError("The file is not a valid MP4 video.")
    if ext == "webm" and head[:4] != b"\x1a\x45\xdf\xa3":
        raise UploadError("The file is not a valid WebM video.")
    return VIDEO_EXTENSIONS[ext]


def validate_video_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.lower().startswith("https://"):
        raise UploadError("Video links must use HTTPS.")
    return url
