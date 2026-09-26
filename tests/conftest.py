import io

import pytest
from django.core.cache import cache
from PIL import Image

from apps.core import mongo


@pytest.fixture(autouse=True)
def fresh_state(settings, tmp_path):
    """Every test gets an empty in-memory MongoDB, empty cache and its own media folder."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage",
                    "OPTIONS": {"location": str(tmp_path / "media")}},
    }
    mongo.reset_client()
    cache.clear()
    yield
    mongo.reset_client()
    cache.clear()


@pytest.fixture
def admin_user(django_user_model):
    return django_user_model.objects.create_user("admin", password="a-strong-test-password", is_staff=True)


@pytest.fixture
def viewer_user(django_user_model):
    return django_user_model.objects.create_user("viewer", password="a-strong-test-password")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def viewer_client(client, viewer_user):
    client.force_login(viewer_user)
    return client


def make_image(fmt="PNG", size=(64, 48), exif_gps=False, name=None):
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = io.BytesIO()
    img = Image.new("RGB", size, (200, 80, 110))
    kwargs = {}
    if exif_gps and fmt == "JPEG":
        exif = Image.Exif()
        exif[0x010F] = "TestCamera"  # Make
        exif[0x8825] = {1: "N", 2: (25.0, 15.0, 0.0)}  # GPS IFD
        kwargs["exif"] = exif
    img.save(buf, fmt, **kwargs)
    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[fmt]
    content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    return SimpleUploadedFile(name or f"photo.{ext}", buf.getvalue(), content_type=content_type)
