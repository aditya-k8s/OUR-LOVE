"""Restore an export created by `export_story` or Admin -> Export.

    python manage.py restore_story our-love.json
    python manage.py restore_story our-love.zip      # also restores media files

Documents are upserted by id, so running it twice is safe. Existing documents
with the same id are replaced.
"""
import json
import zipfile
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.core.mongo import get_db
from apps.core.site_settings import clear_cache
from apps.dashboard.export import EXPORT_COLLECTIONS

DATETIME_FIELDS = ("created_at", "updated_at")


def restore_doc(doc: dict) -> dict:
    raw_id = doc.get("_id")
    if isinstance(raw_id, str) and ObjectId.is_valid(raw_id):
        doc["_id"] = ObjectId(raw_id)
    for field in DATETIME_FIELDS:
        if isinstance(doc.get(field), str):
            try:
                doc[field] = datetime.fromisoformat(doc[field])
            except ValueError:
                pass
    return doc


class Command(BaseCommand):
    help = "Restore story data (and media from a ZIP) produced by export_story."

    def add_arguments(self, parser):
        parser.add_argument("source", type=Path)

    def handle(self, *args, source: Path, **opts):
        if not source.is_file():
            raise CommandError(f"File not found: {source}")
        media_files = 0
        if source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as zf:
                data = json.loads(zf.read("our-love.json"))
                for name in zf.namelist():
                    if name.startswith("media/") and not name.endswith("/") and ".." not in name:
                        key = name[len("media/"):]
                        if not default_storage.exists(key):
                            default_storage.save(key, ContentFile(zf.read(name)))
                            media_files += 1
        else:
            data = json.loads(source.read_text(encoding="utf-8"))
        if data.get("app") != "our-love":
            raise CommandError("This file is not an Our Love export.")
        db = get_db()
        total = 0
        for name, docs in data.get("collections", {}).items():
            if name not in EXPORT_COLLECTIONS:
                continue
            for doc in docs:
                doc = restore_doc(doc)
                db[name].replace_one({"_id": doc["_id"]}, doc, upsert=True)
                total += 1
        clear_cache()
        self.stdout.write(self.style.SUCCESS(f"Restored {total} documents and {media_files} media files."))
