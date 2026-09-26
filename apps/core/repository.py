"""Thin repository layer over PyMongo collections.

Keeps queries explicit and centralises timestamps, id handling and the
visibility rules (published / public) that every public page must respect.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings

from .mongo import get_db


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except (InvalidId, TypeError):
        return None


def serialize(doc: dict | None) -> dict | None:
    """Return a template/JSON friendly copy: `_id` becomes the string `id`."""
    if doc is None:
        return None
    out: dict = {}
    for key, value in doc.items():
        if key == "_id":
            out["id"] = str(value)
        elif isinstance(value, ObjectId):
            out[key] = str(value)
        elif isinstance(value, list):
            out[key] = [str(v) if isinstance(v, ObjectId) else v for v in value]
        else:
            out[key] = value
    return out


def can_see_private(request) -> bool:
    """Signed-in users see everything; anonymous visitors only public content."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


def visibility_filter(request, publishable: bool = True) -> dict:
    query: dict = {}
    if publishable:
        query["is_published"] = {"$ne": False}
    if not can_see_private(request):
        # Anonymous access only happens when PUBLIC_SITE_ENABLED=True (middleware),
        # and then strictly for documents explicitly marked public.
        query["is_public"] = True
    return query


def regex_contains(text: str) -> dict:
    return {"$regex": re.escape(text.strip()), "$options": "i"}


class Repository:
    def __init__(self, collection: str):
        self.name = collection

    @property
    def col(self):
        return get_db()[self.name]

    # -- reads ---------------------------------------------------------------

    def find(
        self,
        query: dict | None = None,
        sort: Iterable[tuple[str, int]] | None = None,
        limit: int = 0,
        skip: int = 0,
        projection: dict | None = None,
    ) -> list[dict]:
        cursor = self.col.find(query or {}, projection)
        if sort:
            cursor = cursor.sort(list(sort))
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return [serialize(d) for d in cursor]

    def find_one(self, query: dict) -> dict | None:
        return serialize(self.col.find_one(query))

    def get(self, doc_id: Any, extra: dict | None = None) -> dict | None:
        oid = to_object_id(doc_id)
        if oid is None:
            return None
        return self.find_one({"_id": oid, **(extra or {})})

    def get_many(self, ids: Iterable[Any], extra: dict | None = None) -> list[dict]:
        """Fetch documents by id, preserving the order of `ids`."""
        oids = [oid for oid in (to_object_id(i) for i in ids or []) if oid]
        if not oids:
            return []
        docs = {d["id"]: d for d in self.find({"_id": {"$in": oids}, **(extra or {})})}
        return [docs[str(o)] for o in oids if str(o) in docs]

    def count(self, query: dict | None = None) -> int:
        return self.col.count_documents(query or {})

    def distinct(self, field: str, query: dict | None = None) -> list:
        return sorted(v for v in self.col.distinct(field, query or {}) if v not in (None, ""))

    # -- writes --------------------------------------------------------------

    def insert(self, data: dict) -> str:
        stamp = now_utc()
        doc = {**data, "created_at": stamp, "updated_at": stamp}
        return str(self.col.insert_one(doc).inserted_id)

    def update(self, doc_id: Any, fields: dict, unset: Iterable[str] = ()) -> bool:
        oid = to_object_id(doc_id)
        if oid is None:
            return False
        change: dict = {"$set": {**fields, "updated_at": now_utc()}}
        unset = [u for u in unset if u not in fields]
        if unset:
            change["$unset"] = {u: "" for u in unset}
        return self.col.update_one({"_id": oid}, change).matched_count == 1

    def delete(self, doc_id: Any) -> bool:
        oid = to_object_id(doc_id)
        return bool(oid) and self.col.delete_one({"_id": oid}).deleted_count == 1

    def pull_reference(self, field: str, value: str) -> None:
        """Remove an id from an array field in every document (e.g. a deleted photo)."""
        self.col.update_many({field: value}, {"$pull": {field: value}})


def repo(collection: str) -> Repository:
    return Repository(collection)


def mongo_ready() -> bool:
    return bool(settings.MONGODB_URI)
