"""Accounts from environment variables (serverless deployments without a persistent database).

On each cold start the throwaway SQLite database is migrated and the admin (and optional
viewer) account is recreated from:

    ADMIN_USERNAME + ADMIN_PASSWORD      (or ADMIN_PASSWORD_HASH from `manage.py hash_password`)
    VIEWER_USERNAME + VIEWER_PASSWORD    (optional, read-only access)

Ids and password hashes are deterministic, so signed-cookie sessions stay valid across
instances and cold starts. Changing a password (or SECRET_KEY) signs everyone out.
"""
from __future__ import annotations

import hashlib
import logging
import os

from django.conf import settings
from django.contrib.auth.hashers import identify_hasher, make_password

logger = logging.getLogger(__name__)

ACCOUNTS = (
    # (id, env prefix, is_staff)
    (1, "ADMIN", True),
    (2, "VIEWER", False),
)


def stable_hash(password: str, username: str) -> str:
    """Hash with a salt derived from SECRET_KEY, so every instance produces the same value."""
    salt = hashlib.sha256(f"our-love:{username}:{settings.SECRET_KEY}".encode()).hexdigest()[:22]
    return make_password(password, salt=salt)


def _password_hash(prefix: str, username: str) -> str | None:
    given_hash = os.environ.get(f"{prefix}_PASSWORD_HASH", "").strip()
    if given_hash:
        try:
            identify_hasher(given_hash)
            return given_hash
        except ValueError:
            logger.error("%s_PASSWORD_HASH is not a valid Django password hash.", prefix)
            return None
    password = os.environ.get(f"{prefix}_PASSWORD", "")
    if password:
        return stable_hash(password, username)
    return None


def ensure_env_accounts(migrate: bool = True) -> list[str]:
    """Create or refresh the environment-defined accounts. Returns the usernames prepared."""
    if not settings.ENV_ACCOUNTS:
        return []
    if migrate:
        from django.core.management import call_command

        call_command("migrate", interactive=False, verbosity=0)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    prepared = []
    for user_id, prefix, is_staff in ACCOUNTS:
        username = os.environ.get(f"{prefix}_USERNAME", "").strip()
        if not username:
            continue
        password_hash = _password_hash(prefix, username)
        if not password_hash:
            logger.error("%s_USERNAME is set but %s_PASSWORD (or %s_PASSWORD_HASH) is missing.", prefix, prefix, prefix)
            continue
        User.objects.update_or_create(
            id=user_id,
            defaults={"username": username, "password": password_hash, "is_staff": is_staff,
                      "is_superuser": is_staff, "is_active": True},
        )
        prepared.append(username)
    if not prepared:
        logger.error("No accounts configured: set ADMIN_USERNAME and ADMIN_PASSWORD in the environment.")
    return prepared
