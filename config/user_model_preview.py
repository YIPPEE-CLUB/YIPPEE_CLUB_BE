"""Custom user design review only. Never use this to migrate the development DB.

Inherits the service's custom User settings and blocks SQL. This module always
targets the isolated test DB; it never validates the actual database schema.
"""
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

USER_MODEL_OFFLINE_PREVIEW = True

DATABASES = deepcopy(DATABASES)  # noqa: F405
DATABASES["default"]["ENGINE"] = "config.offline_mysql"
_preview_database = DATABASES["default"]["TEST"]["NAME"]
if _preview_database != "test_yippee_club_db":
    raise ImproperlyConfigured("User model preview requires test_yippee_club_db.")
DATABASES["default"]["NAME"] = _preview_database

# AppConfig installs an SQL blocker: this module is for offline checks only.
# Full database tests require a separately approved, prepared MySQL schema.
DATABASES["default"]["TEST"]["NAME"] = _preview_database
