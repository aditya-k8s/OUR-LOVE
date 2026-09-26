from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.mongo import get_db, ping


class Command(BaseCommand):
    help = "Test the MongoDB Atlas connection configured in MONGODB_URI."

    def handle(self, *args, **opts):
        try:
            ping()
            names = get_db().list_collection_names()
        except Exception as exc:
            raise CommandError(f"Could not reach MongoDB: {exc.__class__.__name__}: {exc}")
        self.stdout.write(self.style.SUCCESS(
            f"Connected. Database '{settings.MONGODB_DATABASE}' has {len(names)} collections."
        ))
