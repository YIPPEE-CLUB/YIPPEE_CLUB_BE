"""Fresh favorite rehearsal instance only; never development or a previous datadir."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from .user_model_rehearsal import *  # noqa: F403

_uuid = os.environ.get("YIPPEE_FAVORITES_REHEARSAL_UUID", "")
_datadir = Path(os.environ.get("YIPPEE_FAVORITES_REHEARSAL_DATADIR", "")).resolve()
_evidence = _datadir.parent
if (not _uuid or _evidence.parent != (BASE_DIR / ".mysql-rehearsal").resolve() or  # noqa: F405
        not _evidence.name.startswith("favorites-deploy-") or _datadir.name != "data"):
    raise ImproperlyConfigured("Explicit fresh favorites rehearsal identity required")
ACTIVITY_PRIVATE_ROOT = Path(os.environ["YIPPEE_FAVORITES_REHEARSAL_FILES"]).resolve()
if ACTIVITY_PRIVATE_ROOT.parent != _evidence:
    raise ImproperlyConfigured("Isolated upload directory must be inside this run")


def guard_fresh_connection(sender, connection, **kwargs):
    c = connection.settings_dict
    if (c["HOST"] != "127.0.0.1" or int(c["PORT"]) != 33307 or c["USER"] != "yippee_rehearsal" or
            c["NAME"] not in ("test_yippee_migration_fresh", "test_yippee_migration_legacy", "test_yippee_migration_suite", None)):
        raise ImproperlyConfigured("Fresh favorites connection rejected")
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid,@@datadir,@@port,@@server_id")
        actual = cursor.fetchone()
    if actual[0] != _uuid or Path(actual[1]).resolve() != _datadir or actual[2:] != (33307, 9133307):
        raise ImproperlyConfigured("Fresh favorites instance identity rejected")


connection_created.connect(guard_fresh_connection, weak=False)
