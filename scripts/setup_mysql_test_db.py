"""Apply the approved test-only SQL via mysql.exe's local password prompt.

Never reuse an existing schema automatically; report its contents and stop.
No development migrations, custom User SQL, password changes or .env writes.
"""
import os
from pathlib import Path
import subprocess
import sys

from setup_mysql_dev import admin_sql

ROOT = Path(__file__).resolve().parents[1]
TEST_DB = "test_yippee_club_db"


def run():
    if os.name != "nt" or not sys.stdin.isatty():
        raise RuntimeError("Run from a local Windows PowerShell console without redirection.")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings

    target = settings.DATABASES["default"]
    if (target["ENGINE"] != "django.db.backends.mysql" or
            target["NAME"] != "yippee_club_db" or target["USER"] != "yippee_app" or
            target["HOST"] != "127.0.0.1" or int(target["PORT"]) != 3306 or
            target["TEST"]["NAME"] != TEST_DB or settings.AUTH_USER_MODEL != "auth.User"):
        raise RuntimeError("Unexpected database/User settings; stopped before any changes.")

    print("Root preflight: enter your password in the local MySQL CLI prompt.")
    result = admin_sql(
        "SELECT @@GLOBAL.partial_revokes;\n"
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_app' AND Host='localhost';\n"
        f"SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{TEST_DB}';\n"
    ).splitlines()
    if len(result) != 3 or result[0:2] != ["0", "1"]:
        raise RuntimeError("partial_revokes/account preflight differs from approved SQL. No changes made.")
    if result[2] == "1":
        print("Existing test database detected. Inspecting only; it will not be granted, reused or deleted.")
        tables = admin_sql(
            f"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='{TEST_DB}';\n"
        ).splitlines()
        print(f"Existing table/view count: {len(tables)}")
        if tables:
            queries = []
            for table in tables:
                quoted = table.replace('`', '``')
                queries.append(f"SELECT EXISTS(SELECT 1 FROM `{TEST_DB}`.`{quoted}` LIMIT 1);")
            rows = admin_sql("\n".join(queries) + "\n").splitlines()
            if len(rows) != len(tables) or any(row not in {"0", "1"} for row in rows):
                raise RuntimeError("Could not verify existing data. No changes made.")
            print(f"Tables/views containing rows: {rows.count('1')}")
        else:
            print("No tables or table data present.")
        print("STOPPED: report these counts before requesting permission to reuse the existing schema.")
        return 2
    if result[2] != "0":
        raise RuntimeError("Unexpected preflight response. No changes made.")

    print("Test database absent. Authenticating to create it and grant the approved schema-only privileges.")
    # No IF NOT EXISTS: if another process creates the schema after preflight,
    # fail rather than accidentally reuse it. The CLI aborts batch SQL on error.
    grants = admin_sql(
        f"CREATE DATABASE `{TEST_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES "
        "ON `test\\_yippee\\_club\\_db`.* TO 'yippee_app'@'localhost';\n"
        "SHOW GRANTS FOR 'yippee_app'@'localhost';\n"
    )
    print("Test database created. SHOW GRANTS result:")
    print(grants)

    # Verify the app account really has effective access and the new schema is
    # still empty before Django creates any test tables. No production query.
    import MySQLdb
    db = MySQLdb.connect(
        host=target["HOST"], port=int(target["PORT"]), user=target["USER"],
        passwd=target["PASSWORD"], db=TEST_DB, charset="utf8mb4",
    )
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT DATABASE(), CURRENT_USER()")
            if cursor.fetchone() != (TEST_DB, "yippee_app@localhost"):
                raise RuntimeError("Unexpected test connection identity.")
            cursor.execute("SHOW GRANTS FOR CURRENT_USER")
            effective_grants = [row[0] for row in cursor.fetchall()]
            if not any("test\\_yippee\\_club\\_db" in grant for grant in effective_grants):
                raise RuntimeError("Exact test database grant was not found.")
            cursor.execute("SHOW FULL TABLES")
            if cursor.fetchall():
                raise RuntimeError("Test schema gained tables concurrently; stopped before tests.")
    finally:
        db.close()
    print("App-account test connection and exact grant verified.")

    command = [sys.executable, "manage.py", "test", "--keepdb", "--noinput",
               "--settings=config.settings", "--verbosity=2"]
    test_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    completed = subprocess.run(command, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=test_env)
    output = completed.stdout + completed.stderr
    for secret in (target["PASSWORD"], settings.SECRET_KEY):
        if secret:
            output = output.replace(secret, "[REDACTED]")
    print(output, end="")
    if completed.returncode:
        raise RuntimeError("Integration tests failed. Test DB retained; no automatic retry or cleanup.")
    print("SUCCESS: integration tests passed; test DB retained. No development migration was run.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except KeyboardInterrupt:
        print("\nInterrupted. No automatic retry. Check test schema state before continuing.")
        sys.exit(1)
    except Exception as error:
        if isinstance(error, RuntimeError):
            print(f"STOPPED: {error}")
        else:
            print(f"STOPPED: {type(error).__name__}; sensitive details suppressed.")
        print("No automatic retry, database deletion or production migration will be attempted.")
        sys.exit(1)
