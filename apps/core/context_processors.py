"""Values every template needs: site settings, navigation and privacy flags."""
from __future__ import annotations

import logging

from django.conf import settings
from django.urls import reverse

from .site_settings import DEFAULTS, get_settings

logger = logging.getLogger(__name__)

MAIN_NAV = [
    ("content:home", "Home"),
    ("content:story", "Story"),
    ("content:memories", "Memories"),
    ("content:gallery", "Gallery"),
    ("content:letters", "Letters"),
    ("content:calendar", "Calendar"),
]

MOBILE_NAV = [
    ("content:home", "Home", "home"),
    ("content:story", "Story", "story"),
    ("content:memories", "Memories", "memories"),
    ("content:gallery", "Gallery", "gallery"),
    ("content:more", "More", "more"),
]


def site(request):
    try:
        site_settings = get_settings()
    except Exception:  # database unavailable: keep pages (e.g. errors) rendering
        logger.exception("Could not load site settings")
        site_settings = DEFAULTS
    path = request.path
    try:
        nav = [
            {"url": reverse(name), "label": label, "active": path == reverse(name) if name == "content:home" else path.startswith(reverse(name))}
            for name, label in MAIN_NAV
        ]
        mobile_nav = [
            {"url": reverse(name), "label": label, "icon": icon, "active": path == reverse(name) if name == "content:home" else path.startswith(reverse(name))}
            for name, label, icon in MOBILE_NAV
        ]
    except Exception:  # pragma: no cover
        nav, mobile_nav = [], []
    rel = site_settings["relationship"]
    names = [n for n in (rel.get("person_one"), rel.get("person_two")) if n]
    return {
        "site": site_settings,
        "app_name": site_settings["pwa"]["app_name"],
        "couple_names": " & ".join(names),
        "public_site": settings.PUBLIC_SITE_ENABLED,
        "request_limit_bytes": int(settings.REQUEST_LIMIT_MB * 1024 * 1024),
        "media_ephemeral": settings.MEDIA_EPHEMERAL,
        "allow_indexing": settings.PUBLIC_SITE_ENABLED and site_settings["privacy"]["allow_search_indexing"],
        "nav": nav,
        "mobile_nav": mobile_nav,
        "is_admin": request.user.is_authenticated and request.user.is_staff if hasattr(request, "user") else False,
    }
