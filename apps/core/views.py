"""PWA endpoints, dynamic theme stylesheet, robots, health check and error pages."""
from __future__ import annotations

import hashlib
import json

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.views.decorators.http import require_GET

from .site_settings import get_settings

APP_SHELL = [
    "css/ourlove.css",
    "js/theme-init.js",
    "js/ourlove.js",
    "icons/icon-192.png",
    "icons/icon-512.png",
    "icons/logo.svg",
    "images/grain.png",
]


@require_GET
def manifest(request):
    pwa = get_settings()["pwa"]
    data = {
        "id": "/",
        "name": pwa["app_name"],
        "short_name": pwa["short_name"],
        "description": "A private, cinematic memory of our story.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "orientation": "portrait",
        "background_color": pwa["background_color"],
        "theme_color": pwa["theme_color"],
        "categories": ["lifestyle", "photo"],
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("icons/maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Our story", "url": "/story/"},
            {"name": "Memories", "url": "/memories/"},
            {"name": "Gallery", "url": "/gallery/"},
        ],
    }
    response = HttpResponse(json.dumps(data, indent=2), content_type="application/manifest+json")
    response["Cache-Control"] = "no-cache"
    return response


def _shell_urls() -> list[str]:
    urls = [static(path) for path in APP_SHELL]
    return urls + ["/offline/", "/manifest.webmanifest", "/theme.css"]


@require_GET
def service_worker(request):
    shell = _shell_urls()
    version = hashlib.sha256(("|".join(shell) + settings.APP_VERSION).encode()).hexdigest()[:12]
    body = render_to_string(
        "pwa/service-worker.js",
        {"version": version, "shell_json": json.dumps(shell), "static_prefix": settings.STATIC_URL},
    )
    response = HttpResponse(body, content_type="application/javascript")
    response["Cache-Control"] = "no-cache"
    response["Service-Worker-Allowed"] = "/"
    return response


@require_GET
def theme_css(request):
    appearance = get_settings()["appearance"]
    css = f":root {{ --accent: {appearance['accent_color']}; --gold: {appearance['gold_color']}; }}\n"
    response = HttpResponse(css, content_type="text/css")
    response["Cache-Control"] = "no-cache"
    return response


@require_GET
def offline(request):
    return render(request, "offline.html")


@require_GET
def robots_txt(request):
    allow = settings.PUBLIC_SITE_ENABLED and get_settings()["privacy"]["allow_search_indexing"]
    body = "User-agent: *\n" + ("Disallow: /admin/\nDisallow: /api/\nDisallow: /media/\n" if allow else "Disallow: /\n")
    return HttpResponse(body, content_type="text/plain")


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    # Rendered without the site context processor (the database may be the cause).
    return HttpResponse(render_to_string("errors/500.html"), status=500)
