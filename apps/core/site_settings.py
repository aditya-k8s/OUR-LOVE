"""Site-wide settings stored in the `settings` collection (single document)."""
from __future__ import annotations

import copy
import re

from django.core.cache import cache

from .mongo import get_db
from .repository import now_utc

SETTINGS_ID = "site"
CACHE_KEY = "ourlove:site-settings"
CACHE_SECONDS = 30

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULTS: dict = {
    "relationship": {
        "person_one": "",
        "person_two": "",
        "start_date": "",
        "first_meeting_date": "",
        "anniversary_date": "",
        "description": "",
        "story_intro": "",
        "person_one_photo_id": "",
        "person_two_photo_id": "",
    },
    "appearance": {
        "accent_color": "#D94F70",
        "gold_color": "#C9A96E",
        "hero_title": "Our Love",
        "hero_subtitle": "Two people.\nThousands of moments.\nOne story.",
        "hero_photo_id": "",
        "hero_video_id": "",
        "final_quote": "And this is only the beginning.",
        "default_theme": "dark",
    },
    "pwa": {
        "app_name": "Our Love",
        "short_name": "Our Love",
        "theme_color": "#080808",
        "background_color": "#080808",
    },
    "privacy": {
        "allow_search_indexing": False,
    },
    "music": {
        "enabled": False,
        "url": "",
        "title": "",
    },
    "easter_egg": {
        "enabled": True,
        "message": "You found a little secret.",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _merge(out[key], value)
        elif key in out:
            out[key] = value
    return out


def get_settings() -> dict:
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    stored = get_db()["settings"].find_one({"_id": SETTINGS_ID}) or {}
    stored.pop("_id", None)
    merged = _merge(DEFAULTS, stored)
    cache.set(CACHE_KEY, merged, CACHE_SECONDS)
    return merged


def save_settings(values: dict) -> dict:
    """Persist a (partial) settings dict; unknown keys are ignored."""
    merged = _merge(get_settings(), values)
    for section in ("appearance", "pwa"):
        for key, val in merged[section].items():
            if key.endswith("_color") and not HEX_COLOR.match(str(val)):
                merged[section][key] = DEFAULTS[section][key]
    get_db()["settings"].update_one(
        {"_id": SETTINGS_ID}, {"$set": {**merged, "updated_at": now_utc()}}, upsert=True
    )
    cache.delete(CACHE_KEY)
    return merged


def clear_cache() -> None:
    cache.delete(CACHE_KEY)
