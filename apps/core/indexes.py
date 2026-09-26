"""MongoDB index definitions (applied by `python manage.py ensure_indexes`)."""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel

from .mongo import get_db


def _story_indexes() -> list[IndexModel]:
    return [
        IndexModel([("date", ASCENDING)]),
        IndexModel([("category", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("title", ASCENDING)]),
        IndexModel([("location.city", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("is_public", ASCENDING), ("is_published", ASCENDING)]),
    ]


def _media_indexes() -> list[IndexModel]:
    return [
        IndexModel([("date", ASCENDING)]),
        IndexModel([("tags", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
        IndexModel([("storage_key", ASCENDING)], unique=True, sparse=True),
    ]


INDEXES: dict[str, list[IndexModel]] = {
    "timeline_events": _story_indexes() + [IndexModel([("first_key", ASCENDING)], sparse=True)],
    "memories": _story_indexes(),
    "photos": _media_indexes(),
    "videos": _media_indexes(),
    "letters": [IndexModel([("date", ASCENDING)]), IndexModel([("created_at", DESCENDING)])],
    "messages": [IndexModel([("date", ASCENDING)]), IndexModel([("created_at", DESCENDING)])],
    "places": [IndexModel([("name", ASCENDING)]), IndexModel([("city", ASCENDING)]), IndexModel([("date", ASCENDING)])],
    "gifts": [IndexModel([("date", ASCENDING)])],
    "important_dates": [IndexModel([("date", ASCENDING)])],
    "future_plans": [IndexModel([("completed", ASCENDING), ("order", ASCENDING)])],
    "import_jobs": [IndexModel([("created_at", DESCENDING)])],
    "pending_memories": [
        IndexModel([("job_id", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ],
}


def ensure_indexes() -> dict[str, list[str]]:
    db = get_db()
    created: dict[str, list[str]] = {}
    for name, models in INDEXES.items():
        created[name] = db[name].create_indexes(models)
    return created
