"""'Export Our Story': structured JSON, optionally zipped with media files."""
from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import date, datetime

from bson import ObjectId
from django.core.files.storage import default_storage

from apps.core.mongo import get_db
from apps.core.registry import CONTENT_TYPES
from apps.core.repository import now_utc

EXPORT_COLLECTIONS = [ct.collection for ct in CONTENT_TYPES.values()] + ["settings", "pending_memories", "import_jobs"]
FORMAT_VERSION = 1


def _default(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def build_export() -> dict:
    db = get_db()
    return {
        "app": "our-love",
        "format_version": FORMAT_VERSION,
        "exported_at": now_utc().isoformat(),
        "collections": {name: list(db[name].find({})) for name in EXPORT_COLLECTIONS},
    }


def export_json_bytes() -> bytes:
    return json.dumps(build_export(), default=_default, ensure_ascii=False, indent=2).encode("utf-8")


def media_keys(data: dict) -> list[str]:
    keys: list[str] = []
    for name in ("photos", "videos"):
        for doc in data["collections"].get(name, []):
            for field in ("storage_key", "thumb_key", "medium_key"):
                if doc.get(field):
                    keys.append(doc[field])
    return keys


def export_zip_file(include_media: bool = True):
    """Return an open temporary file containing the ZIP (caller streams and closes it)."""
    data = build_export()
    tmp = tempfile.TemporaryFile()
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("our-love.json", json.dumps(data, default=_default, ensure_ascii=False, indent=2))
        manifest = {"format_version": FORMAT_VERSION, "media": [], "missing": []}
        if include_media:
            for key in media_keys(data):
                try:
                    with default_storage.open(key, "rb") as fh:
                        zf.writestr(f"media/{key}", fh.read(), compress_type=zipfile.ZIP_STORED)
                    manifest["media"].append(key)
                except Exception:
                    manifest["missing"].append(key)
        zf.writestr("metadata.json", json.dumps(manifest, indent=2))
    tmp.seek(0)
    return tmp
