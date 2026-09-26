from django.core.management.base import BaseCommand

from apps.core.indexes import ensure_indexes


class Command(BaseCommand):
    help = "Create the MongoDB indexes used by Our Love (safe to run repeatedly)."

    def handle(self, *args, **opts):
        for collection, names in ensure_indexes().items():
            self.stdout.write(f"{collection}: {', '.join(names)}")
        self.stdout.write(self.style.SUCCESS("Indexes are up to date."))
