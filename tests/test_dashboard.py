import pytest
from django.urls import reverse

from apps.core.repository import repo
from apps.core.site_settings import get_settings

pytestmark = pytest.mark.django_db


def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard:home"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


def test_dashboard_forbidden_for_non_staff(viewer_client):
    assert viewer_client.get(reverse("dashboard:home")).status_code == 403
    response = viewer_client.post(reverse("dashboard:create", args=["memories"]), {"title": "x"})
    assert response.status_code == 403
    assert repo("memories").count() == 0


def test_dashboard_home_renders(admin_client):
    response = admin_client.get(reverse("dashboard:home"))
    assert response.status_code == 200
    assert b"Pending imports" in response.content


@pytest.mark.parametrize("key", ["timeline", "memories", "photos", "videos", "letters", "messages", "places", "gifts", "dates", "future"])
def test_every_list_and_form_renders(admin_client, key):
    assert admin_client.get(reverse("dashboard:list", args=[key])).status_code == 200
    response = admin_client.get(reverse("dashboard:create", args=[key]))
    assert response.status_code in (200, 302)


def test_create_timeline_event_appears_in_story(admin_client):
    response = admin_client.post(reverse("dashboard:create", args=["timeline"]), {
        "title": "Our first meeting", "date": "2025-07-20", "category": "meeting", "first_key": "first_meeting",
        "importance": "high", "location__city": "Bhagalpur", "tags": "firsts, meeting", "is_published": "on",
    })
    assert response.status_code == 302
    event = repo("timeline_events").find_one({"title": "Our first meeting"})
    assert event["date"] == "2025-07-20"
    assert event["tags"] == ["firsts", "meeting"]
    assert event["location"] == {"name": "", "city": "Bhagalpur", "country": ""}
    assert event["is_public"] is False
    assert event["order"] == 1

    body = admin_client.get(reverse("content:story")).content.decode()
    assert "Our first meeting" in body and "2025" in body
    home = admin_client.get("/").content.decode()
    assert "First meeting" in home and "Our first meeting" in home


def test_timeline_requires_date_and_category(admin_client):
    response = admin_client.post(reverse("dashboard:create", args=["timeline"]), {"title": "No date"})
    assert response.status_code == 200
    assert repo("timeline_events").count() == 0


def test_create_memory_with_uploaded_photo(admin_client):
    from tests.conftest import make_image

    response = admin_client.post(reverse("dashboard:create", args=["memories"]), {
        "title": "The day we met", "date": "2025-07-20", "category": "meeting", "importance": "high",
        "description": "Some moments are ordinary until they are not.", "is_published": "on",
        "photo_ids__upload": make_image(),
    })
    assert response.status_code == 302
    memory = repo("memories").find_one({"title": "The day we met"})
    assert len(memory["photo_ids"]) == 1
    assert repo("photos").count() == 1
    page = admin_client.get(reverse("content:memory_detail", args=[memory["id"]])).content.decode()
    assert "Some moments are ordinary" in page


def test_edit_toggle_and_delete(admin_client):
    doc_id = repo("letters").insert({"title": "A letter", "content": "Dear you", "is_published": True})
    response = admin_client.post(reverse("dashboard:edit", args=["letters", doc_id]),
                                 {"title": "A letter to you", "content": "Dear you,", "is_published": "on"})
    assert response.status_code == 302
    assert repo("letters").get(doc_id)["title"] == "A letter to you"

    admin_client.post(reverse("dashboard:toggle", args=["letters", doc_id, "is_published"]))
    assert repo("letters").get(doc_id)["is_published"] is False
    assert "A letter to you" not in admin_client.get(reverse("content:letters")).content.decode()

    admin_client.post(reverse("dashboard:delete", args=["letters", doc_id]))
    assert repo("letters").count() == 0


def test_toggle_rejects_unknown_fields(admin_client):
    doc_id = repo("letters").insert({"title": "A letter", "content": "x"})
    assert admin_client.post(reverse("dashboard:toggle", args=["letters", doc_id, "title"])).status_code == 404


def test_reorder_future_plans(admin_client):
    a = repo("future_plans").insert({"title": "A", "order": 1, "completed": False})
    b = repo("future_plans").insert({"title": "B", "order": 2, "completed": False})
    admin_client.post(reverse("dashboard:reorder", args=["future", b, "up"]))
    assert repo("future_plans").get(b)["order"] == 1
    assert repo("future_plans").get(a)["order"] == 2


def test_mark_future_plan_completed_sets_date(admin_client):
    doc_id = repo("future_plans").insert({"title": "Watch the sunrise", "completed": False})
    admin_client.post(reverse("dashboard:toggle", args=["future", doc_id, "completed"]))
    plan = repo("future_plans").get(doc_id)
    assert plan["completed"] is True and plan["completion_date"]


def test_settings_save_and_duration_on_home(admin_client):
    response = admin_client.post(reverse("dashboard:settings"), {
        "person_one": "A", "person_two": "B", "start_date": "2024-05-10",
        "accent_color": "#D94F70", "gold_color": "#C9A96E", "default_theme": "dark",
        "app_name": "Our Love", "short_name": "Our Love", "theme_color": "#080808", "background_color": "#080808",
        "easter_enabled": "on", "easter_message": "You found a little secret.",
    })
    assert response.status_code == 302
    assert get_settings()["relationship"]["start_date"] == "2024-05-10"
    body = admin_client.get("/").content.decode()
    assert "Together for" in body


def test_home_shows_not_added_when_empty(admin_client):
    body = admin_client.get("/").content.decode()
    assert "Not added yet" in body
    assert "No memory recorded for this day yet." in body
    assert "Together for" not in body  # no start date, nothing invented


def test_stats_are_counted_not_invented(admin_client):
    repo("memories").insert({"title": "One", "is_published": True})
    repo("memories").insert({"title": "Two", "is_published": True})
    from apps.content.services import stats
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = type("U", (), {"is_authenticated": True})()
    values = {s["label"]: s["value"] for s in stats(request)}
    assert values["Memories"] == 2
    assert values["Days together"] is None


def test_on_this_day(admin_client):
    from apps.content.services import on_this_day
    from apps.core.dates import today
    from django.test import RequestFactory

    t = today()
    repo("memories").insert({"title": "Anniversary memory", "date": f"{t.year - 1}-{t.month:02d}-{t.day:02d}", "is_published": True})
    request = RequestFactory().get("/")
    request.user = type("U", (), {"is_authenticated": True})()
    items = on_this_day(request)
    assert items and items[0]["ago"] == "1 year ago"


def test_export_json_and_restore(admin_client, tmp_path):
    repo("memories").insert({"title": "Kept", "date": "2025-01-01", "is_published": True})
    response = admin_client.get(reverse("dashboard:export") + "?format=json")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment")
    path = tmp_path / "export.json"
    path.write_bytes(response.content)

    repo("memories").col.delete_many({})
    from django.core.management import call_command

    call_command("restore_story", str(path))
    assert repo("memories").find_one({"title": "Kept"})


def test_export_zip(admin_client):
    response = admin_client.get(reverse("dashboard:export") + "?format=zip")
    assert response.status_code == 200
    assert b"".join(response.streaming_content)[:2] == b"PK"


def test_seed_data_is_clearly_demo(db):
    from django.core.management import call_command

    call_command("seed_data")
    for doc in repo("memories").find({}):
        assert doc["title"].startswith("Demo") and doc["is_demo"] is True
    call_command("seed_data", "--clear")
    assert repo("memories").count() == 0
