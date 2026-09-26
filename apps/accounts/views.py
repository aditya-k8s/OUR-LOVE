"""Sign in / sign out with brute-force protection."""
from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from apps.core import ratelimit
from apps.core.middleware import client_ip

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


def _safe_next(request) -> str:
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return settings.LOGIN_REDIRECT_URL


@sensitive_post_parameters("password")
@csrf_protect
@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    ip = client_ip(request)
    username = (request.POST.get("username") or "").strip().lower()
    locked = ratelimit.count("login-ip", ip) >= MAX_FAILURES or (
        username and ratelimit.count("login-user", username) >= MAX_FAILURES
    )

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if locked:
            return render(
                request,
                "accounts/login.html",
                {"form": AuthenticationForm(request), "locked": True, "next": _safe_next(request)},
                status=429,
            )
        if form.is_valid():
            ratelimit.reset("login-ip", ip)
            ratelimit.reset("login-user", username)
            login(request, form.get_user())  # rotates the session key
            return redirect(_safe_next(request))
        ratelimit.hit("login-ip", ip, LOCK_SECONDS)
        if username:
            ratelimit.hit("login-user", username, LOCK_SECONDS)

    return render(request, "accounts/login.html", {"form": form, "locked": False, "next": _safe_next(request)})


@require_POST
def logout_view(request):
    logout(request)
    response = redirect(settings.LOGOUT_REDIRECT_URL)
    # Remove any pages the browser or service worker may have kept.
    response["Clear-Site-Data"] = '"cache"'
    return response
