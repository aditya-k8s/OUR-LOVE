"""Small cache-backed fixed-window rate limiter (no Redis required)."""
from __future__ import annotations

from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse
from django.template.response import TemplateResponse

from .middleware import client_ip


def _key(scope: str, ident: str) -> str:
    return f"ourlove:rl:{scope}:{ident}"


def hit(scope: str, ident: str, window: int) -> int:
    key = _key(scope, ident)
    if cache.add(key, 1, window):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window)
        return 1


def count(scope: str, ident: str) -> int:
    return cache.get(_key(scope, ident), 0)


def reset(scope: str, ident: str) -> None:
    cache.delete(_key(scope, ident))


def rate_limit(scope: str, limit: int, window: int, methods: tuple[str, ...] = ("POST",)):
    """Limit a view per client IP. Returns 429 with a friendly page or JSON."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods and hit(scope, client_ip(request), window) > limit:
                if request.headers.get("Accept", "").startswith("application/json") or request.path.startswith("/api/"):
                    return JsonResponse({"detail": "Too many requests. Please wait a moment."}, status=429)
                return TemplateResponse(request, "errors/429.html", status=429)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
