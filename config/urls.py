"""Root URL configuration."""
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("", include("apps.content.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("admin/import/", include("apps.imports.urls")),
    path("admin/", include("apps.dashboard.urls")),
    path("api/", include("apps.api.urls")),
    path("media/", include("apps.media.urls")),
    path("manifest.webmanifest", core_views.manifest, name="manifest"),
    path("service-worker.js", core_views.service_worker, name="service_worker"),
    path("theme.css", core_views.theme_css, name="theme_css"),
    path("offline/", core_views.offline, name="offline"),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    # /healthz/ is answered by apps.core.middleware.HealthCheckMiddleware
]

handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
