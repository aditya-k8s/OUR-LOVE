"""WSGI entry point (gunicorn config.wsgi, and Vercel's Django runtime)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

# Serverless without a persistent database: rebuild the environment-defined accounts
# once per cold start, before the first request is served.
from django.conf import settings  # noqa: E402

if settings.ENV_ACCOUNTS:
    from apps.accounts.bootstrap import ensure_env_accounts  # noqa: E402

    ensure_env_accounts()
