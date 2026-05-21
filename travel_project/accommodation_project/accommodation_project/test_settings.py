"""
Test settings override — use SQLite for isolated, fast test runs.

Usage:
    python manage.py test chat_api recommendations --settings=accommodation_project.test_settings
"""
from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Suppress Django system-check warnings for test-only env
SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008"]
