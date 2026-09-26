import pytest
from django.urls import reverse

from apps.core.repository import repo

pytestmark = pytest.mark.django_db


def test_private_site_redirects_anonymous_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"].startswith(reverse("accounts:login"))
    assert "next=%2F" in response["Location"]


@pytest.mark.parametrize("path", ["/manifest.webmanifest", "/service-worker.js", "/offline/", "/robots.txt", "/accounts/login/"])
def test_open_paths_do_not_require_login(client, path):
    assert client.get(path).status_code == 200


def test_login_and_logout(client, admin_user):
    response = client.post(reverse("accounts:login"), {"username": "admin", "password": "a-strong-test-password"})
    assert response.status_code == 302
    assert client.get("/").status_code == 200
    assert client.get(reverse("accounts:logout")).status_code == 405  # logout is POST only
    response = client.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert response["Clear-Site-Data"] == '"cache"'
    assert client.get("/").status_code == 302


def test_login_rejects_open_redirect(client, admin_user):
    response = client.post(
        reverse("accounts:login") + "?next=https://evil.example/",
        {"username": "admin", "password": "a-strong-test-password", "next": "https://evil.example/"},
    )
    assert response.status_code == 302
    assert "evil.example" not in response["Location"]


def test_login_rate_limit_locks_after_failures(client, admin_user):
    for _ in range(5):
        response = client.post(reverse("accounts:login"), {"username": "admin", "password": "wrong"})
        assert response.status_code == 200
    # Even the correct password is refused while locked.
    response = client.post(reverse("accounts:login"), {"username": "admin", "password": "a-strong-test-password"})
    assert response.status_code == 429
    assert b"Too many attempts" in response.content


def test_public_mode_shows_only_public_content(client, settings):
    settings.PUBLIC_SITE_ENABLED = True
    repo("memories").insert({"title": "Private memory", "date": "2025-07-20", "is_public": False, "is_published": True})
    repo("memories").insert({"title": "Shared memory", "date": "2025-07-21", "is_public": True, "is_published": True})
    repo("memories").insert({"title": "Draft memory", "date": "2025-07-22", "is_public": True, "is_published": False})
    body = client.get(reverse("content:memories")).content.decode()
    assert "Shared memory" in body
    assert "Private memory" not in body
    assert "Draft memory" not in body


def test_signed_in_viewer_sees_private_but_not_drafts(viewer_client):
    repo("memories").insert({"title": "Private memory", "is_public": False, "is_published": True})
    repo("memories").insert({"title": "Draft memory", "is_public": False, "is_published": False})
    body = viewer_client.get(reverse("content:memories")).content.decode()
    assert "Private memory" in body
    assert "Draft memory" not in body


def test_private_detail_returns_404_for_anonymous_in_public_mode(client, settings):
    settings.PUBLIC_SITE_ENABLED = True
    doc_id = repo("memories").insert({"title": "Private", "is_public": False, "is_published": True})
    assert client.get(reverse("content:memory_detail", args=[doc_id])).status_code == 404


def test_invalid_object_id_is_404(viewer_client):
    assert viewer_client.get(reverse("content:memory_detail", args=["not-an-id"])).status_code == 404
