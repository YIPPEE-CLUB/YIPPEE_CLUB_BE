"""Read-only deployment gate. Never runs Django migrations or DDL."""
import argparse
import json
import os
from pathlib import Path
import sys

import MySQLdb

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("initial", "prepared", "bridged", "final"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.conf import settings
    from scripts.run_mysql_rehearsal import snapshot

    config = settings.DATABASES["default"]
    if config["NAME"] != "yippee_club_db" or int(config["PORT"]) != 3306:
        raise RuntimeError("Expected development database yippee_club_db on port 3306; no connection attempted.")
    db = MySQLdb.connect(host=config["HOST"], port=int(config["PORT"]), user=config["USER"],
                         passwd=config["PASSWORD"], db=config["NAME"], charset="utf8mb4", connect_timeout=5)
    try:
        with db.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SELECT DATABASE(),CURRENT_USER(),@@server_uuid,@@port")
            identity = cursor.fetchone()
            if identity[0] != "yippee_club_db" or identity[3] != 3306:
                raise RuntimeError("Connected database/port rejected")
        state = snapshot(db)
        applied = set(map(tuple, state["migrations"]))
        stages = ("initial", "prepared", "bridged", "final")
        stage = stages.index(args.stage)
        expected_extra = (
            ("accounts", "0001_initial"),
            ("accounts", "0002_bridge_admin_user"),
            ("email_verification", "0001_initial"),
        )[:stage]
        if len(applied) != 18 + stage or set(key for key in applied if key[0] in {"accounts", "email_verification"}) != set(expected_extra):
            raise RuntimeError("Unexpected migration history for " + args.stage)
        expected_tables = (10, 13, 13, 15)[stage]
        if len(state["tables"]) != expected_tables:
            raise RuntimeError("Unexpected table count for " + args.stage)
        empty_tables = ["auth_user", "auth_user_groups", "auth_user_user_permissions", "django_admin_log"]
        if stage:
            empty_tables += ["accounts_user", "accounts_user_groups", "accounts_user_user_permissions"]
        if any(state["tables"].get(table, {}).get("count") != 0 for table in empty_tables):
            raise RuntimeError("User/Admin data exists or prerequisite table missing; stop and review mapping plan")
        target = "accounts_user" if stage >= 2 else "auth_user"
        admin_fks = [fk for fk in state["foreign_keys"] if fk[:2] == ("django_admin_log", "user_id")]
        if admin_fks != [("django_admin_log", "user_id", target, "id")]:
            raise RuntimeError("Unexpected physical Admin user FK")
        if stage:
            user_type = next(col[1] for col in state["tables"]["accounts_user"]["columns"] if col[0] == "id")
            admin_type = next(col[1] for col in state["tables"]["django_admin_log"]["columns"] if col[0] == "user_id")
            if user_type != admin_type:
                raise RuntimeError("User and Admin column type mismatch")
        with db.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM auth_group_permissions gp JOIN auth_permission p "
                           "ON gp.permission_id=p.id JOIN django_content_type ct ON p.content_type_id=ct.id "
                           "WHERE ct.app_label='auth' AND ct.model='user'")
            if cursor.fetchone()[0]:
                raise RuntimeError("Legacy User group permissions require mapping")
        print(json.dumps({"status": "PASS", "stage": args.stage, "identity": identity,
                          "table_count": len(state["tables"]), "migration_count": len(applied),
                          "admin_user_fk": admin_fks, "counts": {key: value["count"] for key, value in state["tables"].items()}}, indent=2))
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
