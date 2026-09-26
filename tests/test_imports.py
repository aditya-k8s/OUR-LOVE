import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.core.repository import repo
from apps.imports.duplicates import find_duplicates, similarity
from apps.imports.extractor import extract, find_dates
from apps.imports.parsers import ParseError, SourceText, parse_upload
from apps.imports.services import run_import

pytestmark = pytest.mark.django_db

SPEC_EXAMPLE = """2025-07-19
I proposed to her in the evening and she said yes.

2025-07-20
We met at the cafe in Bhagalpur for the first time in person.

2025-07-21
She said "I will always choose you" and we talked for hours.
"""


def test_find_dates_formats():
    text = "On 19 July 2025, then July 20th, 2025, then 21/07/2025 and 2025-07-22."
    assert [d[1] for d in find_dates(text)] == ["2025-07-19", "2025-07-20", "2025-07-21", "2025-07-22"]


def test_find_dates_ignores_impossible_dates():
    assert find_dates("2025-02-30") == []


def test_extract_spec_example():
    candidates, examined = extract([SourceText(SPEC_EXAMPLE)])
    assert examined == 3
    main = [c for c in candidates if c.target != "messages"]
    assert [c.date for c in main] == ["2025-07-19", "2025-07-20", "2025-07-21"]
    proposal = main[0]
    assert proposal.category == "milestone"
    assert proposal.importance == "high"
    assert proposal.title.startswith("I proposed to her")
    meeting = main[1]
    assert meeting.location["city"] == "Bhagalpur"
    quotes = [c for c in candidates if c.target == "messages"]
    assert quotes and quotes[0].quote == "I will always choose you"


def test_extract_never_invents_dates():
    candidates, _ = extract([SourceText("We went on our first date and laughed the whole evening at dinner.")])
    assert candidates
    assert candidates[0].date is None
    assert candidates[0].confidence == "low"
    assert any("No date" in r for r in candidates[0].reasons)


def test_partial_date_is_reported_but_not_used():
    candidates, _ = extract([SourceText("On 14 February we exchanged gifts and she gave me a watch.")])
    assert candidates[0].date is None
    assert any("no year" in r for r in candidates[0].reasons)


def test_first_key_detection():
    candidates, _ = extract([SourceText("2025-08-01\nOur first kiss happened by the river.")])
    assert candidates[0].first_key == "first_kiss"


def test_irrelevant_text_is_skipped():
    candidates, examined = extract([SourceText("Okay.\n\nThanks!\n\nWhat is the capital of France")])
    assert examined == 3 and candidates == []


def test_chatgpt_export_uses_only_user_messages():
    export = [{
        "title": "Our story",
        "mapping": {
            "a": {"message": {"author": {"role": "user"}, "create_time": 1752900000,
                              "content": {"parts": ["2025-07-19\nI proposed to her and she said yes."]}}},
            "b": {"message": {"author": {"role": "assistant"}, "create_time": 1752900100,
                              "content": {"parts": ["2025-07-25\nYou went to Paris together on 25 July 2025."]}}},
        },
    }]
    _, texts = parse_upload("conversations.json", json.dumps(export).encode())
    assert len(texts) == 1
    assert "proposed" in texts[0].text
    assert texts[0].written_on == "2025-07-19"


def test_chatgpt_html_export():
    payload = json.dumps([{"title": "t", "mapping": {"x": {"message": {"author": {"role": "user"}, "content": {"parts": ["hello there 2025-01-01"]}}}}}])
    html = f"<html><script>var jsonData = {payload};\n</script></html>"
    _, texts = parse_upload("chat.html", html.encode())
    assert texts[0].text == "hello there 2025-01-01"


def test_plain_html_strips_scripts():
    _, texts = parse_upload("page.html", b"<p>We met in 2025-07-20</p><script>alert(1)</script>")
    assert "alert" not in texts[0].text and "We met" in texts[0].text


def test_rejects_unsupported_and_fake_pdf():
    with pytest.raises(ParseError):
        parse_upload("virus.exe", b"MZ")
    with pytest.raises(ParseError):
        parse_upload("fake.pdf", b"not a pdf")


def test_run_import_creates_pending_only():
    job = run_import("story.txt", SPEC_EXAMPLE.encode())
    assert job["status"] == "ready"
    assert job["stats"]["candidates"] >= 3
    assert repo("pending_memories").count({"status": "pending"}) == job["stats"]["candidates"]
    assert repo("memories").count() == 0 and repo("timeline_events").count() == 0


def test_imported_memories_are_invisible_until_approved(admin_client):
    run_import("story.txt", SPEC_EXAMPLE.encode())
    assert "I proposed" not in admin_client.get(reverse("content:story")).content.decode()


def test_upload_review_approve_flow(admin_client):
    upload = SimpleUploadedFile("story.txt", SPEC_EXAMPLE.encode(), content_type="text/plain")
    response = admin_client.post(reverse("imports:index"), {"file": upload})
    assert response.status_code == 302
    pending = repo("pending_memories").find_one({"suggested.date": "2025-07-19", "target": "timeline"})
    review_url = reverse("imports:review", args=[pending["id"]])
    assert admin_client.get(review_url).status_code == 200

    response = admin_client.post(review_url, {
        "action": "approve", "target": "timeline", "title": "The day I proposed", "date": "2025-07-19",
        "category": "milestone", "importance": "high", "description": "I proposed to her.",
    })
    assert response.status_code == 302
    event = repo("timeline_events").find_one({"title": "The day I proposed"})
    assert event and event["source"]["type"] == "import" and event["is_public"] is False
    assert repo("pending_memories").get(pending["id"])["status"] == "approved"
    assert "The day I proposed" in admin_client.get(reverse("content:story")).content.decode()


def test_reject_and_bulk_reject(admin_client):
    job = run_import("story.txt", SPEC_EXAMPLE.encode())
    first = repo("pending_memories").find({"job_id": job["id"]})[0]
    admin_client.post(reverse("imports:review", args=[first["id"]]), {"action": "reject"})
    assert repo("pending_memories").get(first["id"])["status"] == "rejected"
    admin_client.post(reverse("imports:bulk", args=[job["id"]]), {"action": "reject_low"})
    assert repo("pending_memories").count({"job_id": job["id"], "status": "pending", "confidence": "low"}) == 0


def test_approve_timeline_without_date_is_refused(admin_client):
    job = run_import("s.txt", b"We went on our first date and laughed the whole evening at dinner.")
    pending = repo("pending_memories").find({"job_id": job["id"]})[0]
    admin_client.post(reverse("imports:review", args=[pending["id"]]), {
        "action": "approve", "target": "timeline", "title": "First date", "category": "date", "importance": "high",
    })
    assert repo("timeline_events").count() == 0
    assert repo("pending_memories").get(pending["id"])["status"] == "pending"


def test_duplicate_detection_example_from_spec():
    repo("timeline_events").insert({"title": "Our First Meeting", "date": "2025-07-20", "description": ""})
    cand = {"title": "First time we met", "date": "2025-07-20", "description": ""}
    dups = find_duplicates(cand)
    assert dups and dups[0]["title"] == "Our First Meeting"


def test_unrelated_memory_is_not_duplicate():
    repo("memories").insert({"title": "Trip to the mountains", "date": "2025-12-01", "description": "Snow"})
    assert find_duplicates({"title": "Birthday dinner", "date": "2025-03-19", "description": "Cake"}) == []
    assert similarity({"title": "a b"}, {"title": "c d"}) < 0.55


def test_import_flags_duplicates_and_merge(admin_client):
    existing = repo("timeline_events").insert({"title": "We met at the cafe", "date": "2025-07-20",
                                               "description": "Short note.", "tags": ["cafe"], "category": "meeting"})
    job = run_import("story.txt", SPEC_EXAMPLE.encode())
    assert job["stats"]["duplicates"] >= 1
    pending = repo("pending_memories").find_one({"suggested.date": "2025-07-20", "target": {"$ne": "messages"}})
    assert pending["possible_duplicates"][0]["id"] == existing

    admin_client.post(reverse("imports:review", args=[pending["id"]]), {
        "action": "merge", "merge_into": f"timeline_events:{existing}", "target": "timeline",
        "title": "First time in person", "date": "2025-07-20", "category": "meeting", "importance": "high",
        "description": "We met at the cafe for the first time in person.", "tags": "firsts",
    })
    merged = repo("timeline_events").get(existing)
    assert "Short note." in merged["description"] and "first time in person" in merged["description"]
    assert merged["title"] == "We met at the cafe"  # existing values are never overwritten
    assert merged["tags"] == ["cafe", "firsts"]
    assert repo("timeline_events").count() == 1
    assert repo("pending_memories").get(pending["id"])["status"] == "merged"


def test_import_command(tmp_path):
    from django.core.management import call_command

    path = tmp_path / "chat.md"
    path.write_text(SPEC_EXAMPLE, encoding="utf-8")
    call_command("import_chat_history", str(path))
    assert repo("pending_memories").count() >= 3
