# Our Love - production image (gunicorn + WhiteNoise). MongoDB Atlas is external.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Pillow wheels bundle their own image libraries; nothing else is needed at runtime.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Collect and fingerprint static files at build time. The throwaway key is only
# used for this step and never reaches the running container.
RUN SECRET_KEY="build-only-$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
    ALLOWED_HOSTS=localhost SQLITE_PATH=/tmp/build.sqlite3 \
    python manage.py collectstatic --noinput \
    && rm -f /tmp/build.sqlite3

RUN useradd --create-home --uid 10001 ourlove \
    && mkdir -p /app/data /app/media \
    && chown -R ourlove:ourlove /app/data /app/media \
    && chmod +x /app/docker/entrypoint.sh

USER ourlove

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120", "--access-logfile", "-"]
