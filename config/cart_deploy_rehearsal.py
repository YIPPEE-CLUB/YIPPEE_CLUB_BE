"""Only a new, explicitly identified cart deployment rehearsal instance."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.db.backends.signals import connection_created
from .user_model_rehearsal import *  # noqa: F403

_uuid = os.environ.get("YIPPEE_CART_REHEARSAL_UUID", "")
_datadir = Path(os.environ.get("YIPPEE_CART_REHEARSAL_DATADIR", "")).resolve()
_evidence = _datadir.parent
if (not _uuid or _evidence.parent != (BASE_DIR / ".mysql-rehearsal").resolve()  # noqa: F405
        or not _evidence.name.startswith("cart-deploy-") or _datadir.name != "data"):
    raise ImproperlyConfigured("Explicit fresh cart rehearsal identity required")
ACTIVITY_PRIVATE_ROOT = Path(os.environ["YIPPEE_CART_REHEARSAL_FILES"]).resolve()
if ACTIVITY_PRIVATE_ROOT.parent != _evidence:
    raise ImproperlyConfigured("Rehearsal files must stay inside this run")
if CART_PURCHASE_ENTITLEMENTS_VERIFIED:  # noqa: F405
    raise ImproperlyConfigured("Cart purchase verification must remain False")


def guard_fresh_connection(sender, connection, **kwargs):
    c = connection.settings_dict
    if (c["HOST"] != "127.0.0.1" or int(c["PORT"]) != 33307 or c["USER"] != "yippee_rehearsal"
            or c["NAME"] not in ("test_yippee_migration_fresh", "test_yippee_migration_suite", None)):
        raise ImproperlyConfigured("Fresh cart connection rejected")
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid,@@datadir,@@port,@@server_id")
        actual = cursor.fetchone()
    if actual[0] != _uuid or Path(actual[1]).resolve() != _datadir or actual[2:] != (33307, 9133307):
        raise ImproperlyConfigured("Fresh cart instance identity rejected")


connection_created.connect(guard_fresh_connection, weak=False)
