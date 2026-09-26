"""Security headers, private/public access control and cache policy."""
from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from .site_settings import get_settings

# Paths reachable without signing in even when the site is private.
ALWAYS_OPEN = (
    "/accounts/login/",
    "/static/",
    "/manifest.webmanifest",
    "/service-worker.js",
    "/offline/",
    "/robots.txt",
    "/healthz/",
    "/theme.css",
    "/api/",  # DRF permission classes answer with a JSON 403 instead of a redirect
)

NEVER_CACHE_PREFIXES = ("/admin/", "/accounts/", "/api/")


def build_csp() -> str:
    external_media = "https:"  # external video links / music URLs / S3 pre-signed URLs must be HTTPS
    directives = {
        "default-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self' https://fonts.googleapis.com",
        "font-src": "'self' https://fonts.gstatic.com",
        "img-src": f"'self' data: blob: {external_media if settings.MEDIA_STORAGE_PROVIDER == 's3' else ''}".strip(),
        "media-src": f"'self' blob: {external_media}",
        "connect-src": "'self'",
        "manifest-src": "'self'",
        "worker-src": "'self'",
        "frame-src": "'none'",
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "frame-ancestors": "'none'",
    }
    if settings.SECURE_HTTPS:
        directives["upgrade-insecure-requests"] = ""
    return "; ".join(f"{k} {v}".strip() for k, v in directives.items())


class HealthCheckMiddleware:
    """Answer /healthz/ before host validation so load-balancer probes (Host = container IP) succeed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            from django.http import JsonResponse

            from .mongo import ping

            try:
                ping()
                return JsonResponse({"status": "ok", "mongo": "ok"})
            except Exception:
                return JsonResponse({"status": "degraded", "mongo": "unreachable"}, status=503)
        return self.get_response(request)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.csp = build_csp()

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.csp)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("X-Content-Type-Options", "nosniff")
        if not _indexing_allowed():
            response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        return response


def _indexing_allowed() -> bool:
    if not settings.PUBLIC_SITE_ENABLED:
        return False
    try:
        return bool(get_settings()["privacy"]["allow_search_indexing"])
    except Exception:
        return False


class AccessControlMiddleware:
    """When PUBLIC_SITE_ENABLED is false, everything except ALWAYS_OPEN requires sign-in."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.PUBLIC_SITE_ENABLED and not request.user.is_authenticated:
            if not request.path.startswith(ALWAYS_OPEN):
                login_url = reverse(settings.LOGIN_URL)
                return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)


class CachePolicyMiddleware:
    """Mark anything personal as `private, no-store` so neither proxies nor the service worker keep it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(("/static/", "/media/", "/service-worker.js", "/manifest.webmanifest", "/theme.css")):
            return response
        personal = (
            request.user.is_authenticated
            or not settings.PUBLIC_SITE_ENABLED
            or request.path.startswith(NEVER_CACHE_PREFIXES)
        )
        if personal:
            response["Cache-Control"] = "private, no-store"
        elif "Cache-Control" not in response:
            response["Cache-Control"] = "no-cache"
        return response


def client_ip(request) -> str:
    if getattr(settings, "SECURE_PROXY_SSL_HEADER", None):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
