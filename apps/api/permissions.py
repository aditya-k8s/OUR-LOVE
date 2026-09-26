from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission


class SiteAccessPermission(BasePermission):
    """Reads follow the site's privacy mode; every mutation requires a staff user."""

    message = "Sign in to access this story."

    def has_permission(self, request, view):
        user = request.user
        if request.method in SAFE_METHODS:
            return bool(settings.PUBLIC_SITE_ENABLED or (user and user.is_authenticated))
        return bool(user and user.is_authenticated and user.is_staff)
