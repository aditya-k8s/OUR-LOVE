"""Create or update the admin account without using the Django shell.

    python manage.py createadmin                 # username from ADMIN_USERNAME
    python manage.py createadmin --username me   # explicit username
    python manage.py createadmin --viewer --username partner   # read-only viewer

The password is read from ADMIN_PASSWORD (useful in containers) or prompted for.
"""
import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update the Our Love admin (or a viewer) account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.environ.get("ADMIN_USERNAME"))
        parser.add_argument("--viewer", action="store_true", help="Create a signed-in viewer without admin rights.")
        parser.add_argument("--no-input", action="store_true", help="Fail instead of prompting for a password.")

    def handle(self, *args, **opts):
        username = (opts["username"] or "").strip()
        if not username:
            raise CommandError("Provide --username or set ADMIN_USERNAME.")
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            if opts["no_input"]:
                raise CommandError("ADMIN_PASSWORD is not set.")
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("Passwords do not match.")

        User = get_user_model()
        user = User.objects.filter(username=username).first() or User(username=username)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))
        user.set_password(password)
        user.is_staff = not opts["viewer"]
        user.is_superuser = not opts["viewer"]
        user.is_active = True
        user.save()
        role = "viewer" if opts["viewer"] else "admin"
        self.stdout.write(self.style.SUCCESS(f"Saved {role} account '{username}'."))
