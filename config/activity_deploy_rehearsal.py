"""Only the brand-new activity deployment instance, never an old rehearsal DB."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created

from .user_model_rehearsal import *  # noqa: F403

_uuid = os.environ.get("YIPPEE_ACTIVITY_REHEARSAL_UUID", "")
_datadir = Path(os.environ.get("YIPPEE_ACTIVITY_REHEARSAL_DATADIR", "")).resolve()
_evidence = _datadir.parent
if (not _uuid or _evidence.parent != (BASE_DIR / ".mysql-rehearsal").resolve() or  # noqa: F405
        not _evidence.name.startswith("activity-deploy-") or _datadir.name != "data"):
    raise ImproperlyConfigured("Explicit fresh activity rehearsal identity required")

ACTIVITY_PRIVATE_ROOT = Path(os.environ["YIPPEE_ACTIVITY_REHEARSAL_FILES"])


def guard_fresh_connection(sender, connection, **kwargs):
    c = connection.settings_dict
    if (c["HOST"] != "127.0.0.1" or int(c["PORT"]) != 33307 or c["USER"] != "yippee_rehearsal" or
            c["NAME"] not in ("test_yippee_migration_fresh", "test_yippee_migration_suite", None)):
        raise ImproperlyConfigured("Fresh activity rehearsal connection rejected")
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid,@@datadir,@@port,@@server_id")
        result = cursor.fetchone()
    if result[0] != _uuid or Path(result[1]).resolve() != _datadir or result[2:] != (33307, 9133307):
        raise ImproperlyConfigured("An old rehearsal or development instance was reached; STOP")


connection_created.connect(guard_fresh_connection, weak=False)
