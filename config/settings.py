"""Django settings for Our Love.

Every secret and deployment-specific value comes from the environment
(optionally loaded from a local `.env` file). Nothing sensitive is hard-coded.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value in (None, "") else value


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = env(name)
    return int(value) if value is not None else default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in (env(name, default) or "").split(",") if item.strip()]


# --------------------------------------------------------------------------- core

DEBUG = env_bool("DEBUG", False)
TESTING = env_bool("OURLOVE_TESTING", False)
# Vercel sets VERCEL=1 during the build and at runtime (serverless, read-only code directory).
ON_VERCEL = bool(env("VERCEL")) and not TESTING

_INSECURE_KEY = "dev-only-insecure-key-change-me"
SECRET_KEY = env("SECRET_KEY", _INSECURE_KEY if (DEBUG or TESTING) else None)
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set in the environment when DEBUG=False."
        + (" On Vercel: Project Settings > Environment Variables, for Production and Preview, then redeploy."
           if ON_VERCEL else "")
    )
if not (DEBUG or TESTING) and (SECRET_KEY == _INSECURE_KEY or len(SECRET_KEY) < 40):
    raise ImproperlyConfigured("SECRET_KEY is too weak for production (use 50+ random characters).")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if ON_VERCEL:
    # Vercel's system variables name the deployment, branch and production domains.
    for _name in ("VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        _host = env(_name)
        if _host and _host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_host)
            CSRF_TRUSTED_ORIGINS.append(f"https://{_host}")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.media",
    "apps.content",
    "apps.imports",
    "apps.dashboard",
    "apps.api",
]

MIDDLEWARE = [
    "apps.core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.AccessControlMiddleware",
    "apps.core.middleware.CachePolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    },
]

# ----------------------------------------------------------------- SQL (auth only)
# Users and sessions live in a small SQL database (see docs/ARCHITECTURE.md, D2).

_database_url = env("DATABASE_URL") or env("POSTGRES_URL")
if _database_url and _database_url.startswith(("postgres://", "postgresql://")):
    _db = urlparse(_database_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _db.path.lstrip("/"),
            "USER": _db.username,
            "PASSWORD": _db.password,
            "HOST": _db.hostname,
            "PORT": _db.port or 5432,
            "CONN_MAX_AGE": 0 if ON_VERCEL else 60,
            # Keeps provider options such as sslmode=require (Neon, Supabase, RDS).
            "OPTIONS": dict(parse_qsl(_db.query)),
        }
    }
elif ON_VERCEL:
    raise ImproperlyConfigured(
        "On Vercel the app needs a Postgres database for sign-in and sessions, because the filesystem is "
        "temporary. Add one (e.g. Vercel Storage > Neon) and set DATABASE_URL, then redeploy."
    )
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": env("SQLITE_PATH", str(BASE_DIR / "data" / "auth.sqlite3")),
        }
    }
    try:
        Path(DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
    except OSError:  # read-only filesystem; Django reports the real problem on first query
        pass

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------------ MongoDB

MONGODB_URI = env("MONGODB_URI", "mongomock://localhost" if TESTING else None)
MONGODB_DATABASE = env("MONGODB_DATABASE", "our_love")
MONGODB_TIMEOUT_MS = env_int("MONGODB_TIMEOUT_MS", 8000)

# -------------------------------------------------------------------- auth/session

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "content:home"
LOGOUT_REDIRECT_URL = "accounts:login"
ADMIN_USERNAME = env("ADMIN_USERNAME")

SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 30)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# ------------------------------------------------------------------------ security

SECURE_HTTPS = env_bool("SECURE_HTTPS", not DEBUG and not TESTING)
SESSION_COOKIE_SECURE = SECURE_HTTPS
CSRF_COOKIE_SECURE = SECURE_HTTPS
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", SECURE_HTTPS)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000 if SECURE_HTTPS else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if env_bool("BEHIND_PROXY", ON_VERCEL):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

# --------------------------------------------------------------- access / privacy

PUBLIC_SITE_ENABLED = env_bool("PUBLIC_SITE_ENABLED", False)

# ------------------------------------------------------------------ i18n / time

LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------- static / media

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_STORAGE_PROVIDER = (env("MEDIA_STORAGE_PROVIDER", "local") or "local").lower()
# On Vercel, local disk is temporary: uploads are refused until S3-compatible storage is configured.
MEDIA_EPHEMERAL = ON_VERCEL and MEDIA_STORAGE_PROVIDER == "local"
MEDIA_ROOT = Path(env("MEDIA_ROOT", "/tmp/our-love-media" if MEDIA_EPHEMERAL else str(BASE_DIR / "media")))
MEDIA_SIGNED_URL_SECONDS = env_int("MEDIA_SIGNED_URL_SECONDS", 3600)

_media_backend: dict = {
    "BACKEND": "django.core.files.storage.FileSystemStorage",
    "OPTIONS": {"location": str(MEDIA_ROOT)},
}
if MEDIA_STORAGE_PROVIDER == "s3":
    _media_backend = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            "bucket_name": env("AWS_BUCKET_NAME"),
            "region_name": env("AWS_REGION"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL"),
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": MEDIA_SIGNED_URL_SECONDS,
            "file_overwrite": False,
            "object_parameters": {"CacheControl": "private, max-age=86400"},
        },
    }
elif MEDIA_STORAGE_PROVIDER != "local":
    raise ImproperlyConfigured("MEDIA_STORAGE_PROVIDER must be 'local' or 's3'.")

STORAGES = {
    "default": _media_backend,
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if (DEBUG or TESTING)
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

MAX_IMAGE_UPLOAD_MB = env_int("MAX_IMAGE_UPLOAD_MB", 20)
MAX_VIDEO_UPLOAD_MB = env_int("MAX_VIDEO_UPLOAD_MB", 300)
MAX_IMPORT_UPLOAD_MB = env_int("MAX_IMPORT_UPLOAD_MB", 25)
# Largest request the platform accepts (Vercel functions: 4.5 MB). Browsers resize photos to fit.
REQUEST_LIMIT_MB = float(env("REQUEST_LIMIT_MB", "4.5" if ON_VERCEL else "0") or 0)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000

# -------------------------------------------------------------------------- cache

_redis_url = env("REDIS_URL")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _redis_url}
        if _redis_url
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "our-love"}
    )
}

# ----------------------------------------------------------------- REST framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.api.permissions.SiteAccessPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min"},
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# ------------------------------------------------------------------------ logging

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
    "loggers": {"django.security": {"level": "WARNING"}},
}

# Bumped automatically from the static file contents; used to version the SW cache.
APP_VERSION = env("APP_VERSION", "1.0.0")
