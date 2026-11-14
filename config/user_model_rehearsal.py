"""Dedicated local-instance rehearsal only; never inherits DB credentials from .env."""
import os
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

REHEARSAL_DATABASES = (
    "test_yippee_migration_legacy",
    "test_yippee_migration_fresh",
    "test_yippee_migration_reject",
)
_name = os.environ.get("YIPPEE_REHEARSAL_DATABASE")
_port = os.environ.get("YIPPEE_REHEARSAL_PORT")
_password = os.environ.get("YIPPEE_REHEARSAL_PASSWORD")
if _name not in REHEARSAL_DATABASES or _port != "33307" or not _password:
    raise ImproperlyConfigured("Explicit isolated rehearsal database/port/password required.")
DATABASES = deepcopy(DATABASES)  # noqa: F405
DATABASES["default"].update(
    NAME=_name, HOST="127.0.0.1", PORT=33307,
    USER="yippee_rehearsal", PASSWORD=_password,
    TEST={"NAME": "test_yippee_migration_suite"},
)
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
IS_USER_MODEL_REHEARSAL = True

# A second check runs before *every* statement, including test database creation.
# It proves this is the server started with our distinctive server_id, not :3306.
def guard_rehearsal_sql(execute, sql, params, many, context):
    wrapper = context["connection"]
    target = wrapper.settings_dict
    if (target["HOST"] != "127.0.0.1" or int(target["PORT"]) != 33307 or
            target["USER"] != "yippee_rehearsal" or
            target["NAME"] not in (*REHEARSAL_DATABASES, "test_yippee_migration_suite", None)):
        raise ImproperlyConfigured("Rehearsal SQL target rejected.")
    raw = wrapper.connection.cursor()
    try:
        raw.execute("SELECT @@server_id, @@port")
        if raw.fetchone() != (9133307, 33307):
            raise ImproperlyConfigured("Rehearsal server identity rejected.")
    finally:
        raw.close()
    return execute(sql, params, many, context)
