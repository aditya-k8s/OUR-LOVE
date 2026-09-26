"""Public pages, search, filters, PWA endpoints and security headers."""
import json

import pytest
from django.urls import reverse

from apps.core.repository import repo

pytestmark = pytest.mark.django_db

PAGES = ["home", "story", "memories", "gallery", "moments", "letters", "words", "places", "gifts", "calendar",
         "future", "search", "more"]


@pytest.mark.parametrize("name", PAGES)
def test_every_page_renders_empty(viewer_client, name):
    response = viewer_client.get(reverse(f"content:{name}"))
    assert response.status_code == 200


def test_pages_render_with_content(viewer_client):
    repo("timeline_events").insert({"title": "T", "date": "2025-07-20", "category": "meeting", "is_published": True})
    repo("memories").insert({"title": "M", "date": "2025-07-20", "tags": ["x"], "people": ["A"], "is_published": True})
    repo("letters").insert({"title": "L", "content": "Dear you", "recipient": "You", "is_published": True})
    repo("messages").insert({"message": "Words", "sender": "A", "is_published": True})
    repo("places").insert({"name": "P", "city": "C", "latitude": 25.2, "longitude": 87.0, "is_published": True})
    repo("gifts").insert({"gift": "G", "given_by": "A", "is_published": True})
    repo("important_dates").insert({"title": "Birthday", "date": "2000-03-19", "kind": "birthday", "recurring_yearly": True, "is_published": True})
    repo("future_plans").insert({"title": "Sunrise", "completed": True, "completion_date": "2026-01-01", "is_published": True})
    for name in PAGES:
        assert viewer_client.get(reverse(f"content:{name}")).status_code == 200
    assert b"Open map" in viewer_client.get(reverse("content:places")).content
    cal = viewer_client.get(reverse("content:calendar") + "?year=2026&month=3").content.decode()
    assert "Birthday" in cal


def test_place_coordinates_hidden_from_anonymous_unless_public(client, settings):
    settings.PUBLIC_SITE_ENABLED = True
    repo("places").insert({"name": "Secret spot", "latitude": 25.2, "longitude": 87.0, "is_public": True, "is_published": True})
    assert b"Open map" in client.get(reverse("content:places")).content


def test_search_finds_location_and_partial_words(viewer_client):
    repo("memories").insert({"title": "Evening by the river", "location": {"city": "Bhagalpur"}, "is_published": True})
    repo("letters").insert({"title": "Letter", "content": "I still think about Bhagalpur", "is_published": True})
    body = viewer_client.get(reverse("content:search") + "?q=Bhagalpur").content.decode()
    assert "Evening by the river" in body and "Letter" in body
    assert "2 results" in body


def test_search_escapes_regex(viewer_client):
    repo("memories").insert({"title": "a.b", "is_published": True})
    assert viewer_client.get(reverse("content:search") + "?q=.*(").status_code == 200


def test_memory_filters(viewer_client):
    repo("memories").insert({"title": "In 2025", "date": "2025-07-20", "category": "trip", "tags": ["sea"], "is_published": True})
    repo("memories").insert({"title": "In 2026", "date": "2026-03-19", "category": "birthday", "is_published": True})
    body = viewer_client.get(reverse("content:memories") + "?year=2025").content.decode()
    assert "In 2025" in body and "In 2026" not in body
    body = viewer_client.get(reverse("content:memories") + "?month=3").content.decode()
    assert "In 2026" in body and "In 2025" not in body
    body = viewer_client.get(reverse("content:memories") + "?tag=sea&category=trip").content.decode()
    assert "In 2025" in body and "In 2026" not in body


def test_xss_is_escaped(viewer_client):
    repo("memories").insert({"title": "<script>alert(1)</script>", "is_published": True})
    body = viewer_client.get(reverse("content:memories")).content.decode()
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_manifest(client):
    response = client.get("/manifest.webmanifest")
    assert response["Content-Type"] == "application/manifest+json"
    data = json.loads(response.content)
    assert data["name"] == "Our Love" and data["display"] == "standalone" and data["start_url"].startswith("/")
    sizes = {i["sizes"] for i in data["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i.get("purpose") == "maskable" for i in data["icons"])


def test_service_worker(client):
    response = client.get("/service-worker.js")
    assert response["Content-Type"] == "application/javascript"
    assert response["Service-Worker-Allowed"] == "/"
    body = response.content.decode()
    assert "/offline/" in body and "/admin/" in body  # admin is in the never-cache list
    assert "css/ourlove.css" in body


def test_security_headers(viewer_client):
    response = viewer_client.get("/")
    csp = response["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "noindex" in response["X-Robots-Tag"]
    assert response["Cache-Control"] == "private, no-store"
    assert b'name="robots" content="noindex' in response.content


def test_robots_txt_disallows_everything_by_default(client):
    assert client.get("/robots.txt").content.decode().strip().endswith("Disallow: /")


def test_custom_404(viewer_client, settings):
    settings.DEBUG = False
    response = viewer_client.get("/definitely-not-here/")
    assert response.status_code == 404
    assert b"wandered away" in response.content


def test_theme_css_uses_safe_colour(viewer_client):
    from apps.core.site_settings import save_settings

    save_settings({"appearance": {"accent_color": "red;} body{display:none"}})
    body = viewer_client.get("/theme.css").content.decode()
    assert "display:none" not in body and "#D94F70" in body


def test_healthz(client):
    assert client.get("/healthz/").json()["mongo"] == "ok"


def test_healthz_ignores_host_header(client):
    response = client.get("/healthz/", HTTP_HOST="10.0.3.17:8000")
    assert response.status_code == 200
