"""Test settings: in-memory MongoDB (mongomock), temporary media, fast hashing."""
import os
import tempfile

os.environ["OURLOVE_TESTING"] = "1"
os.environ.setdefault("MONGODB_URI", "mongomock://localhost")
os.environ.setdefault("MONGODB_DATABASE", "our_love_test")
os.environ["MEDIA_STORAGE_PROVIDER"] = "local"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="ourlove-test-media-")
os.environ["SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(prefix="ourlove-test-db-"), "auth.sqlite3")
os.environ["PUBLIC_SITE_ENABLED"] = "false"
os.environ["DEBUG"] = "false"

from .settings import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["testserver", "localhost"]
