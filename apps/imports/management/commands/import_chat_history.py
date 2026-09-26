"""python manage.py import_chat_history <file>

Parses a chat export and stores candidates as *pending* memories. Nothing is
published; review them in Admin -> Import History.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.imports.services import run_import


class Command(BaseCommand):
    help = "Extract candidate memories from a chat export into Pending Memories."

    def add_arguments(self, parser):
        parser.add_argument("file", type=Path)

    def handle(self, *args, file: Path, **opts):
        if not file.is_file():
            raise CommandError(f"File not found: {file}")
        if file.stat().st_size > settings.MAX_IMPORT_UPLOAD_MB * 1024 * 1024:
            raise CommandError(f"File is larger than {settings.MAX_IMPORT_UPLOAD_MB} MB.")
        job = run_import(file.name, file.read_bytes())
        if job["status"] == "failed":
            raise CommandError(job["error"])
        stats = job["stats"]
        self.stdout.write(self.style.SUCCESS(
            f"Examined {stats['passages']} passages and found {stats['candidates']} candidates "
            f"(high {stats['high']}, medium {stats['medium']}, low {stats['low']}; "
            f"{stats['duplicates']} possible duplicates)."
        ))
        self.stdout.write("Nothing has been published. Review them in Admin -> Import History.")
