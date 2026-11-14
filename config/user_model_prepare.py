"""Approval-required bootstrap configuration; keeps the active auth.User.

Use only for the reviewed accounts migrations after a verified backup.
Importing this module does not apply any migration or switch the active User.
"""
from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

# Explicit legacy override: settings now defaults to accounts.User. Keep the
# installed accounts app so its initial migration can run before the switch.
AUTH_USER_MODEL = "auth.User"
if DATABASES["default"]["NAME"] != "yippee_club_db":  # noqa: F405
    raise ImproperlyConfigured("User preparation is restricted to yippee_club_db.")
