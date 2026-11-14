"""Backup read-only source; restore/migrate only a new local MySQL instance.

No service installation, source writes, drops, fake migrations or cleanup.
Artifacts and datadir remain under the ignored .mysql-rehearsal directory.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid

import MySQLdb

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin")
PORT = 33307
SERVER_ID = 9133307
LEGACY = "test_yippee_migration_legacy"
FRESH = "test_yippee_migration_fresh"
REJECT = "test_yippee_migration_reject"
SUITE = "test_yippee_migration_suite"
TARGETS = (LEGACY, FRESH, REJECT, SUITE)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def migration_hashes():
    return {str(path.relative_to(ROOT)): digest(path.read_bytes())
            for app in ("accounts", "email_verification")
            for path in (ROOT / app / "migrations").glob("*.py")}


def snapshot(db):
    """Read schema plus full row digests without saving user data in the report."""
    with db.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
        try:
            cursor.execute("SHOW FULL TABLES")
            tables = cursor.fetchall()
            if any(kind != "BASE TABLE" for _, kind in tables):
                raise RuntimeError("Views require a separately reviewed backup plan.")
            result = {}
            for table, _ in tables:
                quoted = "`" + table.replace("`", "``") + "`"
                cursor.execute("SHOW CREATE TABLE " + quoted)
                schema = cursor.fetchone()[1]
                # MySQL may print redundant column CHARACTER SET after restore.
                # Compare actual column metadata too, so this display-only
                # normalization cannot hide charset/collation/type changes.
                cursor.execute("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,"
                               "CHARACTER_SET_NAME,COLLATION_NAME,GENERATION_EXPRESSION "
                               "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                               "AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (table,))
                columns = cursor.fetchall()
                schema = re.sub(r" CHARACTER SET \w+(?= COLLATE )", "", schema)
                cursor.execute("SELECT * FROM " + quoted)
                rows = sorted(json.dumps(row, default=str, ensure_ascii=True) for row in cursor.fetchall())
                result[table] = {"count": len(rows), "rows_sha256": digest("\n".join(rows).encode()),
                                 "row_hashes": [digest(row.encode()) for row in rows],
                                 "schema": schema, "columns": columns}
            cursor.execute("SELECT app,name FROM django_migrations ORDER BY app,name")
            migrations = cursor.fetchall()
            cursor.execute("SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME "
                           "FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() "
                           "AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY TABLE_NAME,COLUMN_NAME")
            fks = cursor.fetchall()
            return {"tables": result, "migrations": migrations, "foreign_keys": fks}
        finally:
            db.rollback()


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.conf import settings

    source = settings.DATABASES["default"]
    if source["NAME"] != "yippee_club_db" or int(source["PORT"]) == PORT:
        raise RuntimeError("Source must be yippee_club_db on a different port.")
    for binary in ("mysqld.exe", "mysqldump.exe", "mysql.exe"):
        if not (BIN / binary).is_file():
            raise RuntimeError("MySQL binary missing: " + binary)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))  # Refuse an occupied port; never reuse a server.
    run = ROOT / ".mysql-rehearsal" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    # Restrict backup/datadir access to the current Windows identity and SYSTEM.
    identity = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r",
                    identity + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    report = {"artifact_directory": str(run), "migration_hashes_before": migration_hashes(), "steps": []}
    report_path = run / "report.json"
    print("ARTIFACTS=" + str(run), flush=True)
    process = None
    admin = None
    verified_instance = False
    source_db = None
    root_password = secrets.token_hex(32)
    password = secrets.token_hex(32)
    hidden = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def save():
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    def step(message):
        report["steps"].append(message)
        save()
        print(message, flush=True)

    def connect(database=None, root=False):
        return MySQLdb.connect(host="127.0.0.1", port=PORT,
                               user="root" if root else "yippee_rehearsal",
                               passwd=root_password if root else password,
                               db=database, charset="utf8mb4", connect_timeout=5)

    def manage(database, arguments, legacy=False, expected_failure=False):
        if database not in TARGETS:
            raise RuntimeError("Unapproved target")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8",
               "YIPPEE_REHEARSAL_DATABASE": database, "YIPPEE_REHEARSAL_PORT": str(PORT),
               "YIPPEE_REHEARSAL_PASSWORD": password}
        module = "config.user_model_rehearsal_prepare" if legacy else "config.user_model_rehearsal"
        command = [sys.executable, "manage.py", *arguments, "--settings=" + module]
        result = subprocess.run(command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        output = result.stdout + result.stderr
        for secret in (password, root_password, source["PASSWORD"], settings.SECRET_KEY):
            if secret:
                output = output.replace(secret, "[REDACTED]")
        log = run / (str(len(report["steps"])) + "-" + database + "-" + arguments[0] + ".txt")
        log.write_text(output, encoding="utf-8")
        if expected_failure:
            if not result.returncode or "Empty-user bridge cannot migrate" not in output:
                raise RuntimeError("Expected populated-user rejection was not observed; see " + str(log))
        elif result.returncode:
            raise RuntimeError("Django command failed; see " + str(log))
        step(database + " " + " ".join(arguments) + (" EXPECTED REJECTION" if expected_failure else " OK"))

    def target_snapshot(database):
        db = connect(database)
        try:
            return snapshot(db)
        finally:
            db.close()

    try:
        source_db = MySQLdb.connect(host=source["HOST"], port=int(source["PORT"]),
                                   user=source["USER"], passwd=source["PASSWORD"], db=source["NAME"],
                                   charset="utf8mb4", connect_timeout=5)
        with source_db.cursor() as cursor:
            cursor.execute("SELECT DATABASE(), CURRENT_USER(), @@server_uuid, @@version")
            report["source_identity"] = cursor.fetchone()
            if report["source_identity"][0] != "yippee_club_db":
                raise RuntimeError("Source identity mismatch")
            # No hidden stored objects: a table-only portable dump must be complete.
            for table, schema_column in (("TRIGGERS", "TRIGGER_SCHEMA"), ("ROUTINES", "ROUTINE_SCHEMA"), ("EVENTS", "EVENT_SCHEMA")):
                cursor.execute(f"SELECT COUNT(*) FROM information_schema.{table} WHERE {schema_column}=%s", (source["NAME"],))
                if cursor.fetchone()[0]:
                    raise RuntimeError("Stored objects require a separately reviewed backup plan.")
        report["source_before"] = snapshot(source_db)
        step("Source schema/data/history captured read-only")
        # Configure mysqldump privately, never through command-line passwords.
        client = run / "source-client.cnf"
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        client.write_text("[client]\n" + "\n".join(
            key + "=" + option(value) for key, value in (
                ("host", source["HOST"]), ("port", source["PORT"]),
                ("user", source["USER"]), ("password", source["PASSWORD"]))) + "\n", encoding="utf-8")
        backup = run / "yippee_club_db.sql"
        dump = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(client),
                               "--protocol=TCP", "--single-transaction", "--skip-lock-tables",
                               "--no-tablespaces", "--set-gtid-purged=OFF", "--skip-add-drop-table",
                               # Empty isolated targets need neither table locks
                               # nor non-InnoDB bulk-load key disabling in the dump.
                               "--skip-add-locks", "--skip-disable-keys",
                               "--hex-blob", "--default-character-set=utf8mb4",
                               "--result-file=" + str(backup), "yippee_club_db"], capture_output=True)
        if dump.returncode:
            raise RuntimeError("Read-only mysqldump failed (details suppressed to protect credentials).")
        report["backup"] = {"path": str(backup), "sha256": digest(backup.read_bytes()), "bytes": backup.stat().st_size}
        if report["backup"]["bytes"] == 0:
            raise RuntimeError("Empty backup")
        step("Read-only backup completed and SHA256 recorded")
        datadir = run / "data"
        init = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
                               "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)],
                              capture_output=True, creationflags=hidden)
        (run / "initialize.txt").write_bytes(init.stdout + init.stderr)
        if init.returncode:
            raise RuntimeError("Isolated mysqld initialization failed; see initialize.txt")
        server_log = run / "server.log"
        with (run / "console.txt").open("wb") as console:
            process = subprocess.Popen([
                str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=" + str(PORT), "--bind-address=127.0.0.1",
                "--server-id=" + str(SERVER_ID), "--mysqlx=OFF", "--skip-log-bin",
                "--log-error=" + str(server_log), "--pid-file=" + str(run / "mysqld.pid"),
            ], stdout=console, stderr=console, creationflags=hidden)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Isolated server exited; see server.log")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=PORT, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError:
                time.sleep(0.5)
        if admin is None:
            raise RuntimeError("Isolated server startup timed out")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            report["target_identity"] = identity
            if (identity[:2] != (SERVER_ID, PORT) or Path(identity[2]).resolve() != datadir.resolve()
                    or identity[3] == report["source_identity"][2]):
                raise RuntimeError("Isolation identity mismatch; no target DDL allowed")
            verified_instance = True
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            (run / "root-client.cnf").write_text(
                "[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + root_password + "\n",
                encoding="utf-8",
            )
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            for database in TARGETS:
                cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (database,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("Rehearsal schema already exists; refusing reuse")
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                scope = database.replace("_", r"\_")
                cursor.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,REFERENCES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        step("Separate MySQL instance identity/datadir/port verified; four empty isolated schemas created")
        # Restore through the local Python client. mysql CLI credentials are private.
        target_client = run / "target-client.cnf"
        target_client.write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=yippee_rehearsal\npassword=" + password + "\n", encoding="utf-8")
        for database in (LEGACY, REJECT):
            with backup.open("rb") as payload:
                restored = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(target_client),
                                           "--protocol=TCP", "--default-character-set=utf8mb4", database],
                                          stdin=payload, capture_output=True)
            if restored.returncode:
                (run / (database + "-restore-error.txt")).write_bytes(restored.stderr)
                raise RuntimeError("Restore failed on isolated target " + database)
            state = target_snapshot(database)
            if state != report["source_before"]:
                report["restore_mismatch"] = state
                raise RuntimeError("Restored schema/data/history differs from source")
            report[database + "_restored"] = state
            step(database + " backup restore matches every table schema, full row digest, FK and migration history")
        # Legacy settings may safely inspect the restored 18-migration state.
        manage(LEGACY, ["check"], legacy=True)
        manage(LEGACY, ["migrate", "accounts", "0001", "--plan"], legacy=True)
        manage(LEGACY, ["migrate", "accounts", "0001", "--noinput"], legacy=True)
        report["legacy_after_0001"] = target_snapshot(LEGACY)
        manage(LEGACY, ["migrate", "accounts", "0002_bridge_admin_user", "--noinput"], legacy=True)
        report["legacy_after_0002"] = target_snapshot(LEGACY)
        expected_fk = ("django_admin_log", "user_id", "accounts_user", "id")
        if expected_fk not in report["legacy_after_0002"]["foreign_keys"]:
            raise RuntimeError("Bridge FK postcheck failed")
        manage(LEGACY, ["migrate", "--plan"])
        manage(LEGACY, ["migrate", "--noinput"])
        manage(LEGACY, ["check", "--database", "default"])
        manage(LEGACY, ["makemigrations", "--check", "--dry-run"])
        manage(LEGACY, ["shell", "-c", "from scripts.rehearsal_checks import run_smoke; run_smoke()"])
        report["legacy_final"] = target_snapshot(LEGACY)
        # Restore-created data remains intact. Admin schema changes, not rows.
        for table, before in report["source_before"]["tables"].items():
            after = report["legacy_final"]["tables"][table]
            if not set(before["row_hashes"]) <= set(after["row_hashes"]):
                raise RuntimeError("Original restored rows were modified or removed: " + table)
            if table not in ("django_migrations", "django_content_type", "auth_permission"):
                if before["count"] != after["count"] or before["rows_sha256"] != after["rows_sha256"]:
                    raise RuntimeError("Restored legacy rows changed: " + table)
        step("Legacy restored data preserved; AUTH_USER_MODEL switch and physical Admin FK verified")
        manage(FRESH, ["migrate", "--noinput"])
        report["fresh_final"] = target_snapshot(FRESH)
        if expected_fk not in report["fresh_final"]["foreign_keys"]:
            raise RuntimeError("Fresh Admin FK mismatch")
        manage(FRESH, ["check", "--database", "default"])
        manage(FRESH, ["shell", "-c", "from scripts.rehearsal_checks import run_smoke; run_smoke()"])
        manage(REJECT, ["migrate", "accounts", "0001", "--noinput"], legacy=True)
        manage(REJECT, ["shell", "-c", "from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='rehearsal-existing', email='existing@example.com', password='ExamplePwd!729384')"], legacy=True)
        reject_before = target_snapshot(REJECT)
        manage(REJECT, ["migrate", "accounts", "0002_bridge_admin_user", "--noinput"], legacy=True, expected_failure=True)
        reject_after = target_snapshot(REJECT)
        if reject_before != reject_after:
            raise RuntimeError("Rejected bridge changed schema/data/history")
        report["populated_user_rejection_unchanged"] = True
        step("Existing-user rejection preserved all schema, rows, FK and migration history")
        manage(FRESH, ["test", "--keepdb", "--noinput", "-v", "2"])
        report["source_after"] = snapshot(source_db)
        if report["source_before"] != report["source_after"]:
            raise RuntimeError("Source changed during rehearsal; investigate concurrent activity")
        report["migration_hashes_after"] = migration_hashes()
        if report["migration_hashes_before"] != report["migration_hashes_after"]:
            raise RuntimeError("Migration files changed")
        report["success"] = True
        step("PASS: source unchanged; original migration files unchanged; full Django suite completed")
    except Exception as error:
        report["success"] = False
        report["failure"] = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        save()
        print("STOPPED: " + report["failure"], flush=True)
        raise
    finally:
        if source_db is not None:
            source_db.close()
        if admin is not None and verified_instance:
            try:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            except MySQLdb.Error:
                report["isolated_server_shutdown"] = False
            admin.close()
        if process is not None:
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                report["isolated_server_shutdown"] = False
        save()
        print("Report: " + str(report_path), flush=True)


if __name__ == "__main__":
    main()
