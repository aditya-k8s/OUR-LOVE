"""Print a password hash for ADMIN_PASSWORD_HASH / VIEWER_PASSWORD_HASH.

    python manage.py hash_password

Storing the hash instead of the password keeps the plain password out of your
hosting provider's settings.
"""
import getpass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Hash a password for the ADMIN_PASSWORD_HASH or VIEWER_PASSWORD_HASH environment variable."

    def handle(self, *args, **opts):
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Password (again): "):
            raise CommandError("Passwords do not match.")
        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        self.stdout.write(make_password(password))
