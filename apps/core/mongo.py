"""MongoDB connection management.

A single `MongoClient` is shared per process (PyMongo clients are thread-safe and
pool connections). `mongomock://` URIs are supported for the test-suite only.
"""
from __future__ import annotations

import threading

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_lock = threading.Lock()
_client = None


def _create_client():
    uri = settings.MONGODB_URI
    if not uri:
        raise ImproperlyConfigured(
            "MONGODB_URI is not set. Copy .env.example to .env and add your MongoDB Atlas connection string."
        )
    if uri.startswith("mongomock://"):
        import mongomock

        return mongomock.MongoClient(tz_aware=True)

    from pymongo import MongoClient

    return MongoClient(
        uri,
        serverSelectionTimeoutMS=settings.MONGODB_TIMEOUT_MS,
        tz_aware=True,
        appname="our-love",
        retryWrites=True,
    )


def get_client():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = _create_client()
    return _client


def get_db():
    return get_client()[settings.MONGODB_DATABASE]


def reset_client() -> None:
    """Drop the cached client (used by tests to get a fresh in-memory database)."""
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # pragma: no cover - best effort
                pass
        _client = None


def ping() -> bool:
    get_client().admin.command("ping")
    return True
