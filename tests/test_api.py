import pytest

from apps.core.repository import repo

pytestmark = pytest.mark.django_db


def test_api_requires_login_when_private(client):
    assert client.get("/api/memories/").status_code == 403


def test_api_list_is_paginated(viewer_client):
    for i in range(25):
        repo("memories").insert({"title": f"Memory {i}", "date": f"2025-01-{i + 1:02d}", "is_published": True})
    data = viewer_client.get("/api/memories/?page_size=10&page=2").json()
    assert data["count"] == 25 and data["page"] == 2 and len(data["results"]) == 10 and data["next"] is True


def test_api_mutations_require_staff(viewer_client):
    response = viewer_client.post("/api/memories/", {"title": "Nope"}, content_type="application/json")
    assert response.status_code == 403
    assert repo("memories").count() == 0


def test_api_create_update_delete(admin_client):
    response = admin_client.post("/api/timeline/", {
        "title": "Our first call", "date": "2025-07-18", "category": "first", "first_key": "first_call",
        "tags": ["call"], "location": {"city": "Bhagalpur"},
    }, content_type="application/json")
    assert response.status_code == 201, response.content
    doc = response.json()
    assert doc["tags"] == ["call"] and doc["location"]["city"] == "Bhagalpur"

    response = admin_client.patch(f"/api/timeline/{doc['id']}/", {"title": "Our very first call"}, content_type="application/json")
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Our very first call" and updated["date"] == "2025-07-18" and updated["tags"] == ["call"]

    assert admin_client.delete(f"/api/timeline/{doc['id']}/").status_code == 204
    assert repo("timeline_events").count() == 0


def test_api_validation_errors(admin_client):
    response = admin_client.post("/api/timeline/", {"title": "No date"}, content_type="application/json")
    assert response.status_code == 400
    assert "date" in response.json()["errors"]


def test_api_unknown_type_is_404(viewer_client):
    assert viewer_client.get("/api/unknown/").status_code == 404


def test_api_hides_storage_keys(viewer_client):
    repo("photos").insert({"caption": "c", "storage_key": "photos/x.png", "thumb_key": "photos/x_480.webp", "is_published": True})
    result = viewer_client.get("/api/photos/").json()["results"][0]
    assert "storage_key" not in result and result["urls"]["thumb"].startswith("/media/")


def test_api_search_and_stats(viewer_client):
    repo("memories").insert({"title": "Evening walk", "location": {"city": "Bhagalpur"}, "is_published": True})
    data = viewer_client.get("/api/search/?q=bhagal").json()
    assert data["results"]["memories"][0]["title"] == "Evening walk"
    stats = viewer_client.get("/api/stats/").json()
    assert stats["together"] is None


def test_api_public_mode_only_public(client, settings):
    settings.PUBLIC_SITE_ENABLED = True
    repo("letters").insert({"title": "Private", "content": "x", "is_public": False, "is_published": True})
    repo("letters").insert({"title": "Public", "content": "y", "is_public": True, "is_published": True})
    titles = [d["title"] for d in client.get("/api/letters/").json()["results"]]
    assert titles == ["Public"]
