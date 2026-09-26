import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.urls import reverse

from apps.accounts.bootstrap import ensure_env_accounts, stable_hash

pytestmark = pytest.mark.django_db


@pytest.fixture
def env_accounts(settings, monkeypatch):
    settings.ENV_ACCOUNTS = True
    settings.SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
    monkeypatch.setenv("ADMIN_USERNAME", "aditya")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-long-admin-password")
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("VIEWER_USERNAME", raising=False)
    return monkeypatch


def test_disabled_by_default():
    assert ensure_env_accounts(migrate=False) == []


def test_admin_created_from_environment(env_accounts):
    assert ensure_env_accounts(migrate=False) == ["aditya"]
    user = get_user_model().objects.get(id=1)
    assert user.username == "aditya" and user.is_staff and user.check_password("a-long-admin-password")


def test_hash_is_stable_across_cold_starts(env_accounts):
    ensure_env_accounts(migrate=False)
    first = get_user_model().objects.get(id=1).password
    get_user_model().objects.all().delete()  # a new instance starts with an empty database
    ensure_env_accounts(migrate=False)
    assert get_user_model().objects.get(id=1).password == first
    assert stable_hash("x", "a") == stable_hash("x", "a")


def test_session_survives_a_cold_start(client, env_accounts):
    ensure_env_accounts(migrate=False)
    response = client.post(reverse("accounts:login"), {"username": "aditya", "password": "a-long-admin-password"})
    assert response.status_code == 302
    get_user_model().objects.all().delete()
    ensure_env_accounts(migrate=False)
    assert client.get(reverse("dashboard:home")).status_code == 200


def test_viewer_and_precomputed_hash(env_accounts):
    env_accounts.setenv("VIEWER_USERNAME", "partner")
    env_accounts.setenv("VIEWER_PASSWORD_HASH", make_password("another-long-password"))
    assert ensure_env_accounts(migrate=False) == ["aditya", "partner"]
    viewer = get_user_model().objects.get(id=2)
    assert not viewer.is_staff and viewer.check_password("another-long-password")


def test_missing_password_creates_nothing(env_accounts):
    env_accounts.delenv("ADMIN_PASSWORD")
    assert ensure_env_accounts(migrate=False) == []
    assert get_user_model().objects.count() == 0
