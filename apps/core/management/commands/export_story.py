from pathlib import Path

from django.core.management.base import BaseCommand

from apps.dashboard import export


class Command(BaseCommand):
    help = "Export the whole story to JSON, or to a ZIP including media (--zip)."

    def add_arguments(self, parser):
        parser.add_argument("output", type=Path)
        parser.add_argument("--zip", action="store_true", help="Write a ZIP with JSON, metadata and media files.")
        parser.add_argument("--no-media", action="store_true", help="With --zip, leave media files out.")

    def handle(self, *args, output: Path, **opts):
        if opts["zip"]:
            with export.export_zip_file(include_media=not opts["no_media"]) as handle:
                output.write_bytes(handle.read())
        else:
            output.write_bytes(export.export_json_bytes())
        self.stdout.write(self.style.SUCCESS(f"Wrote {output} ({output.stat().st_size:,} bytes)."))
