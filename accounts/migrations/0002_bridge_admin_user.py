"""Bridge an empty legacy database; retain all old tables and records.

On a fresh custom-User installation, Admin's FK already targets accounts_user:
the operation then performs no DDL. Existing populated installations are rejected.
"""
from django.db import migrations


def bridge_admin_user(apps, schema_editor):
    connection = schema_editor.connection
    database = connection.settings_dict["NAME"]
    if connection.vendor != "mysql" or not (
        database == "yippee_club_db" or database.startswith("test_yippee_")
    ):
        raise RuntimeError("User bridge requires an approved YIPPEE MySQL database.")
    quote = schema_editor.quote_name
    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        if not {"accounts_user", "django_admin_log"} <= tables:
            raise RuntimeError("User bridge prerequisite tables are missing.")
        constraints = connection.introspection.get_constraints(cursor, "django_admin_log")
        references = [
            (name, details["foreign_key"])
            for name, details in constraints.items()
            if details.get("columns") == ["user_id"] and details.get("foreign_key")
        ]
        if len(references) != 1:
            raise RuntimeError("Unexpected Admin user FK count; no changes made.")
        old_name, target = references[0]
        if target == ("accounts_user", "id"):
            return  # Fresh install or already-correct physical schema.
        if target != ("auth_user", "id") or "auth_user" not in tables:
            raise RuntimeError("Unexpected Admin FK target; no changes made.")
        for table in ("auth_user", "accounts_user", "django_admin_log",
                      "auth_user_groups", "auth_user_user_permissions"):
            if table not in tables:
                raise RuntimeError("Legacy prerequisite table missing; no changes made.")
            cursor.execute(f"SELECT COUNT(*) FROM {quote(table)}")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("Empty-user bridge cannot migrate existing user records or links.")
        cursor.execute(
            "SELECT COUNT(*) FROM auth_group_permissions gp "
            "JOIN auth_permission p ON gp.permission_id=p.id "
            "JOIN django_content_type ct ON p.content_type_id=ct.id "
            "WHERE ct.app_label='auth' AND ct.model='user'"
        )
        if cursor.fetchone()[0]:
            raise RuntimeError("Legacy User group permissions require a separate mapping plan.")
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_TYPE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND "
            "((TABLE_NAME='django_admin_log' AND COLUMN_NAME='user_id') OR "
            "(TABLE_NAME='accounts_user' AND COLUMN_NAME='id'))"
        )
        types = dict(cursor.fetchall())
        if types.get("django_admin_log") != types.get("accounts_user") or not types.get("accounts_user"):
            raise RuntimeError("Admin and User key types do not match; no changes made.")
    # MySQL introspection supplies the actual constraint name. No DROP TABLE,
    # deletion, manual migration-recorder edits or FK-check disabling is used.
    new_name = "django_admin_log_user_id_fk_accounts_user"
    schema_editor.execute(
        f"ALTER TABLE {quote('django_admin_log')} "
        f"DROP FOREIGN KEY {quote(old_name)}, "
        f"ADD CONSTRAINT {quote(new_name)} FOREIGN KEY ({quote('user_id')}) "
        f"REFERENCES {quote('accounts_user')} ({quote('id')})"
    )
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, "django_admin_log")
        if constraints.get(new_name, {}).get("foreign_key") != ("accounts_user", "id"):
            raise RuntimeError("Admin FK postcheck failed; stop and inspect before retrying.")


class Migration(migrations.Migration):
    atomic = False  # MySQL DDL is not transactionally rolled back.
    dependencies = [
        ("accounts", "0001_initial"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]
    # Deliberately irreversible: blindly restoring the old FK after new users
    # exist is unsafe. Recovery must be separately reviewed; never unapply 0001.
    operations = [migrations.RunPython(bridge_admin_user)]
