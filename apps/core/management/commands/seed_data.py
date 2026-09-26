"""Optional demo content, clearly labelled as such.

Every document is titled "Demo ..." and flagged `is_demo: true` so it can never
be mistaken for a real memory. Remove it with `--clear` or from the dashboard.
"""
from django.core.management.base import BaseCommand

from apps.core.registry import CONTENT_TYPES
from apps.core.repository import repo

EMPTY_LOCATION = {"name": "", "city": "", "country": ""}

DEMO = {
    "timeline_events": [
        {"title": "Demo Moment: The Beginning", "date": "2000-01-01", "category": "first", "first_key": "first_message",
         "description": "Demo text. Replace this with your own story from the dashboard.", "importance": "high"},
        {"title": "Demo Moment: A Milestone", "date": "2000-02-14", "category": "milestone", "first_key": "",
         "description": "Demo text for layout preview only.", "importance": "medium"},
    ],
    "memories": [
        {"title": "Demo Memory", "date": "2000-01-15", "category": "memory",
         "description": "This is placeholder text to preview the memory card layout.", "importance": "medium",
         "tags": ["demo"]},
    ],
    "letters": [
        {"title": "Demo Letter", "date": "2000-03-01", "recipient": "Demo recipient", "author": "Demo author",
         "content": "This is a demo letter used only to preview the letter layout."},
    ],
    "messages": [
        {"message": "Demo message text for previewing quote cards.", "date": "2000-01-20", "sender": "Demo",
         "context": "Demo context", "category": "other"},
    ],
    "places": [
        {"name": "Demo Place", "city": "Demo City", "country": "Demo Country", "date": "2000-01-10",
         "description": "Demo place for layout preview.", "latitude": None, "longitude": None},
    ],
    "gifts": [
        {"gift": "Demo Gift", "date": "2000-02-01", "given_by": "Demo", "given_to": "Demo", "occasion": "Demo",
         "description": "Demo gift for layout preview."},
    ],
    "important_dates": [
        {"title": "Demo Date", "date": "2000-06-01", "kind": "other", "recurring_yearly": True, "description": "Demo date."},
    ],
    "future_plans": [
        {"title": "Demo Plan", "description": "Demo plan for layout preview.", "target_date": "", "completed": False, "order": 1},
    ],
}


class Command(BaseCommand):
    help = "Insert clearly-labelled demo content (use --clear to remove it)."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove all demo documents.")

    def handle(self, *args, clear=False, **opts):
        collections = {ct.collection for ct in CONTENT_TYPES.values()}
        if clear:
            removed = sum(repo(c).col.delete_many({"is_demo": True}).deleted_count for c in collections)
            self.stdout.write(self.style.SUCCESS(f"Removed {removed} demo documents."))
            return
        created = 0
        for collection, docs in DEMO.items():
            for doc in docs:
                first_field = next(iter(doc))
                if repo(collection).count({"is_demo": True, first_field: doc[first_field]}):
                    continue
                repo(collection).insert({
                    "is_demo": True, "is_published": True, "is_public": False, "tags": [], "people": [],
                    "photo_ids": [], "video_ids": [], "location": dict(EMPTY_LOCATION), **doc,
                })
                created += 1
        self.stdout.write(self.style.SUCCESS(f"Created {created} demo documents (all titled 'Demo ...')."))
