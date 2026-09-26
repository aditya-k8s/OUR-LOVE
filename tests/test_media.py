import io

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.core.repository import repo
from apps.media.services import store_photo
from apps.media.validation import UploadError, validate_image, validate_video
from tests.conftest import make_image

pytestmark = pytest.mark.django_db


def test_valid_image_is_stored_with_thumbnails():
    photo = store_photo(make_image(size=(2000, 1500)))
    assert photo["width"] == 2000 and photo["content_type"] == "image/png"
    for key in ("storage_key", "thumb_key", "medium_key"):
        assert default_storage.exists(photo[key])
    with default_storage.open(photo["thumb_key"]) as fh:
        assert max(Image.open(fh).size) == 480
    assert photo["is_public"] is False


def test_exif_and_gps_are_stripped():
    photo = store_photo(make_image("JPEG", exif_gps=True))
    with default_storage.open(photo["storage_key"]) as fh:
        img = Image.open(fh)
        exif = img.getexif()
        assert 0x8825 not in exif and 0x010F not in exif


def test_rejects_non_image_with_image_extension():
    fake = SimpleUploadedFile("photo.jpg", b"<?php echo 'x'; ?>", content_type="image/jpeg")
    with pytest.raises(UploadError):
        validate_image(fake)


def test_rejects_mismatched_extension():
    png_named_jpg = make_image("PNG", name="photo.jpg")
    with pytest.raises(UploadError, match="extension"):
        validate_image(png_named_jpg)


def test_rejects_dangerous_extension():
    with pytest.raises(UploadError):
        validate_image(SimpleUploadedFile("photo.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml"))


def test_rejects_oversized_image(settings):
    settings.MAX_IMAGE_UPLOAD_MB = 0
    with pytest.raises(UploadError, match="larger"):
        validate_image(make_image())


def test_video_signature_check():
    mp4 = SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64, content_type="video/mp4")
    assert validate_video(mp4) == "video/mp4"
    webm = SimpleUploadedFile("clip.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 64, content_type="video/webm")
    assert validate_video(webm) == "video/webm"
    with pytest.raises(UploadError):
        validate_video(SimpleUploadedFile("clip.mp4", b"MZ" + b"\x00" * 64))
    with pytest.raises(UploadError):
        validate_video(SimpleUploadedFile("clip.avi", b"RIFF" + b"\x00" * 64))


def test_upload_endpoint_json(admin_client):
    response = admin_client.post(reverse("dashboard:upload", args=["photo"]), {"file": make_image()},
                                 HTTP_ACCEPT="application/json")
    assert response.status_code == 200 and response.json()["ok"] is True
    bad = admin_client.post(reverse("dashboard:upload", args=["photo"]),
                            {"file": SimpleUploadedFile("x.png", b"nope", content_type="image/png")})
    assert bad.status_code == 400 and bad.json()["ok"] is False


def test_upload_endpoint_requires_staff(viewer_client):
    response = viewer_client.post(reverse("dashboard:upload", args=["photo"]), {"file": make_image()})
    assert response.status_code == 403
    assert repo("photos").count() == 0


def test_media_view_access_rules(client, viewer_client, settings):
    photo = store_photo(make_image())
    url = reverse("media:serve", args=[photo["thumb_key"]])
    assert viewer_client.get(url).status_code == 200
    assert viewer_client.get(url)["Cache-Control"].startswith("private")

    client.logout()
    anon = client.get(url)
    assert anon.status_code == 302  # private site: redirected to login

    settings.PUBLIC_SITE_ENABLED = True
    assert client.get(url).status_code == 404  # not public
    repo("photos").update(photo["id"], {"is_public": True})
    assert client.get(url).status_code == 200


def test_media_view_supports_range_requests(viewer_client):
    photo = store_photo(make_image())
    url = reverse("media:serve", args=[photo["storage_key"]])
    response = viewer_client.get(url, HTTP_RANGE="bytes=0-9")
    assert response.status_code == 206
    assert len(b"".join(response.streaming_content)) == 10


def test_unknown_media_key_is_404(viewer_client):
    assert viewer_client.get(reverse("media:serve", args=["photos/2026/01/missing.png"])).status_code == 404


def test_deleting_photo_removes_files_and_references(admin_client):
    photo = store_photo(make_image())
    mem = repo("memories").insert({"title": "m", "photo_ids": [photo["id"]]})
    admin_client.post(reverse("dashboard:delete", args=["photos", photo["id"]]))
    assert repo("photos").count() == 0
    assert not default_storage.exists(photo["storage_key"])
    assert repo("memories").get(mem)["photo_ids"] == []
