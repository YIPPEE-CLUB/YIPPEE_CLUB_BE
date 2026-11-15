"""Fresh active-child deployment rehearsal only; never development."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from .user_model_rehearsal import *  # noqa: F403

_uuid = os.environ.get("YIPPEE_ACTIVE_CHILD_REHEARSAL_UUID", "")
_datadir = Path(os.environ.get("YIPPEE_ACTIVE_CHILD_REHEARSAL_DATADIR", "")).resolve()
_run = _datadir.parent
if (not _uuid or _run.parent != (BASE_DIR / ".mysql-rehearsal").resolve()  # noqa: F405
        or not _run.name.startswith("active-child-deploy-") or _datadir.name != "data"):
    raise ImproperlyConfigured("Explicit fresh active-child rehearsal identity required")
ACTIVITY_PRIVATE_ROOT = Path(os.environ["YIPPEE_ACTIVE_CHILD_REHEARSAL_FILES"]).resolve()
if ACTIVITY_PRIVATE_ROOT.parent != _run or CART_PURCHASE_ENTITLEMENTS_VERIFIED:  # noqa: F405
    raise ImproperlyConfigured("Isolated files or purchase verification setting rejected")


def guard_connection(sender, connection, **kwargs):
    c = connection.settings_dict
    if (c["HOST"] != "127.0.0.1" or int(c["PORT"]) != 33307 or c["USER"] != "yippee_rehearsal"
            or c["NAME"] not in ("test_yippee_migration_fresh", "test_yippee_migration_suite", None)):
        raise ImproperlyConfigured("Fresh active-child connection rejected")
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid,@@datadir,@@port,@@server_id")
        identity = cursor.fetchone()
    if identity[0] != _uuid or Path(identity[1]).resolve() != _datadir or identity[2:] != (33307, 9133307):
        raise ImproperlyConfigured("Fresh active-child server identity rejected")


connection_created.connect(guard_connection, weak=False)
