"""Guarded activity deployment: inspect, fresh backup/restore rehearsal, then apply.

No existing rehearsal datadir/database is opened. Source writes are restricted to
the apply phase after matching a successful immutable preparation report.
"""
import argparse
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from io import StringIO
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
sys.path.insert(0, str(ROOT))
from scripts.run_mysql_rehearsal import BIN, digest, snapshot

TARGET = ("activities", "0001_initial")
SOURCE_IDENTITY = ("yippee_club_db", "yippee_app@localhost", "5491c807-5688-11f1-a0bf-c86e08e6aa63", 3306)
NEW_TABLES = {"activities", "activity_categories"}
RESTORE = "test_yippee_migration_fresh"
SUITE = "test_yippee_migration_suite"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalized(value):
    return json.loads(json.dumps(value, default=str))


def code_hashes():
    paths = [p for folder in ("accounts", "email_verification", "children", "categories", "activities", "config")
             for p in (ROOT / folder).rglob("*.py")]
    paths += [ROOT / "scripts/prepare_activity_deploy.py", ROOT / "scripts/run_mysql_rehearsal.py"]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def config():
    from django.conf import settings
    result = settings.DATABASES["default"]
    require((result["NAME"], int(result["PORT"]), result["USER"]) == ("yippee_club_db", 3306, "yippee_app"),
            "Development configuration differs from the reviewed target")
    require(result["HOST"] in ("127.0.0.1", "localhost"), "Development host must be local")
    return result


@contextmanager
def source():
    c = config()
    db = MySQLdb.connect(host=c["HOST"], port=int(c["PORT"]), user=c["USER"], passwd=c["PASSWORD"],
                         db=c["NAME"], charset="utf8mb4", connect_timeout=5)
    try:
        with db.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SELECT DATABASE(),CURRENT_USER(),@@server_uuid,@@port")
            require(cursor.fetchone() == SOURCE_IDENTITY, "Development server/database identity mismatch")
        yield db
    finally:
        db.rollback()
        db.close()


def state():
    with source() as db:
        return normalized(snapshot(db))


def extra_source_info():
    with source() as db, db.cursor() as cursor:
        cursor.execute("SELECT @@version,@@server_id,@@hostname")
        server = cursor.fetchone()
        cursor.execute("SELECT id,name FROM categories ORDER BY id")
        categories = cursor.fetchall()
        cursor.execute("SELECT COUNT(*),COALESCE(SUM(is_active AND is_staff AND is_superuser),0) FROM accounts_user")
        users = cursor.fetchone()
        for table, column in (("TRIGGERS", "TRIGGER_SCHEMA"), ("ROUTINES", "ROUTINE_SCHEMA"), ("EVENTS", "EVENT_SCHEMA")):
            cursor.execute(f"SELECT COUNT(*) FROM information_schema.{table} WHERE {column}=DATABASE()")
            require(cursor.fetchone()[0] == 0, "Stored objects require a separate backup plan")
        cursor.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND ENGINE <> 'InnoDB'")
        require(cursor.fetchone()[0] == 0, "Non-InnoDB tables require a separate backup plan")
        return normalized({"identity": SOURCE_IDENTITY, "server": server, "categories": categories,
                           "user_count": users[0], "active_superusers": users[1]})


def guard_source(execute, sql, params, many, context):
    connection = context["connection"]
    c = connection.settings_dict
    require((c["NAME"], int(c["PORT"]), c["USER"]) == ("yippee_club_db", 3306, "yippee_app"), "Django target rejected")
    with connection.connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE(),CURRENT_USER(),@@server_uuid,@@port")
        require(cursor.fetchone() == SOURCE_IDENTITY, "Django server identity rejected")
    return execute(sql, params, many, context)


def plan():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    with connection.execute_wrapper(guard_source):
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        all_pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        specific = executor.migration_plan([TARGET])
        require(all_pending == specific, "Unrelated migrations are pending")
        return [(m.app_label, m.name, backwards) for m, backwards in specific]


def validate_migration():
    from importlib import import_module
    from django.db.migrations import operations
    migration = import_module("activities.migrations.0001_initial").Migration
    require(migration.dependencies == [("categories", "0001_initial")], "Unexpected dependencies")
    require(len(migration.operations) == 8, "Unexpected migration operations")
    created = set()
    for op in migration.operations:
        require(isinstance(op, (operations.CreateModel, operations.AddField, operations.AddConstraint)), "Unexpected operation type")
        model = op.name if isinstance(op, operations.CreateModel) else op.model_name
        require(model.lower() in ("activity", "activitycategory"), "Existing model would be changed")
        if isinstance(op, operations.CreateModel):
            created.add(op.options["db_table"])
    require(created == NEW_TABLES, "Unexpected activity tables")


def assert_preserved(before, after):
    require(set(after["tables"]) == set(before["tables"]) | NEW_TABLES, "Unexpected table changes")
    require(set(map(tuple, after["migrations"])) == set(map(tuple, before["migrations"])) | {TARGET}, "Unexpected migration changes")
    for name, old in before["tables"].items():
        new = after["tables"][name]
        old_schema, new_schema = old["schema"], new["schema"]
        if name in ("django_migrations", "django_content_type", "auth_permission"):
            old_schema = re.sub(r" AUTO_INCREMENT=\d+", "", old_schema)
            new_schema = re.sub(r" AUTO_INCREMENT=\d+", "", new_schema)
        require(old["columns"] == new["columns"] and old_schema == new_schema, "Existing schema changed: " + name)
        if name in ("django_migrations", "django_content_type", "auth_permission"):
            require(set(old["row_hashes"]) <= set(new["row_hashes"]), "Existing metadata modified: " + name)
        else:
            require(old == new, "Existing data modified: " + name)
    expected_fks = set(map(tuple, before["foreign_keys"])) | {
        ("activity_categories", "activity_id", "activities", "id"),
        ("activity_categories", "category_id", "categories", "id"),
    }
    require(set(map(tuple, after["foreign_keys"])) == expected_fks, "Unexpected FK changes")
    require(all(after["tables"][t]["count"] == 0 for t in NEW_TABLES), "Unexpected activity data")


def protected_directory():
    directory = ROOT / ".mysql-rehearsal" / ("activity-deploy-" + uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    return directory


def save(directory, name, value):
    (directory / name).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def prepare():
    from django.conf import settings
    validate_migration()
    before = state()
    require((len(before["tables"]), len(before["migrations"])) == (20, 24), "Unexpected pre-activity DB state; STOP")
    require(not NEW_TABLES & set(before["tables"]), "Activity table already exists")
    require(plan() == [("activities", "0001_initial", False)], "Unexpected development migration plan")
    info = extra_source_info()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    directory = protected_directory()
    report = {"success": False, "before": before, "source": info, "code_hashes": code_hashes(),
              "development_written": False, "prior_rehearsal_accessed": False}
    print("ARTIFACTS=" + str(directory), flush=True)
    save(directory, "report.json", report)
    admin = process = None
    verified = False
    root_password, password = secrets.token_hex(32), secrets.token_hex(32)
    c = config()
    try:
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        client = directory / "source-client.cnf"
        client.write_text("[client]\n" + "\n".join(key + "=" + option(c[key.upper()]) for key in ("host", "port", "user", "password")) + "\n", encoding="utf-8")
        backup = directory / "yippee_club_db.sql"
        # Same read-only backup options as prepare_child_api_deploy/run_mysql_rehearsal.
        result = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(client), "--protocol=TCP",
            "--single-transaction", "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF",
            "--skip-add-drop-table", "--skip-add-locks", "--skip-disable-keys", "--hex-blob",
            "--default-character-set=utf8mb4", "--result-file=" + str(backup), c["NAME"]], capture_output=True)
        require(result.returncode == 0 and backup.stat().st_size > 0, "Read-only backup failed")
        report["backup"] = {"path": str(backup), "sha256": digest(backup.read_bytes()), "bytes": backup.stat().st_size}
        require(state() == before, "Source changed while backing up")
        print("Fresh read-only backup: PASS", flush=True)
        datadir = directory / "data"
        result = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
            "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (directory / "initialize.txt").write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, "Fresh isolated initialization failed")
        with (directory / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(directory / "server.log"),
                "--pid-file=" + str(directory / "server.pid")], stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            require(process.poll() is None, "Fresh isolated server exited")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        require(admin is not None, "Fresh isolated startup timed out")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            require(identity[:2] == (9133307, 33307) and Path(identity[2]).resolve() == datadir.resolve()
                    and identity[3] != SOURCE_IDENTITY[2], "Fresh isolation identity mismatch")
            verified = True
            report["isolated_identity"] = identity
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("SELECT @@GLOBAL.partial_revokes")
            require(cursor.fetchone()[0] == 0, "Unexpected isolated grant mode")
            for database in (RESTORE, SUITE):
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                scope = database.replace("_", r"\_")
                cursor.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,REFERENCES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        (directory / "root-client.cnf").write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + root_password + "\n", encoding="utf-8")
        target_client = directory / "target-client.cnf"
        target_client.write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=yippee_rehearsal\npassword=" + password + "\n", encoding="utf-8")
        with backup.open("rb") as payload:
            result = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(target_client), "--protocol=TCP",
                                     "--default-character-set=utf8mb4", RESTORE], stdin=payload, capture_output=True)
        require(result.returncode == 0, "Fresh independent restore failed")

        def isolated_state():
            db = MySQLdb.connect(host="127.0.0.1", port=33307, user="yippee_rehearsal", passwd=password,
                                 db=RESTORE, charset="utf8mb4", connect_timeout=5)
            try:
                return normalized(snapshot(db))
            finally:
                db.close()
        require(isolated_state() == before, "Backup restore differs in schema/row hashes/FKs/migration history")
        report["restore_verified"] = True
        print("Independent restore equals all source schemas/rows/FKs/history: PASS", flush=True)
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_DATABASE": RESTORE,
            "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": password,
            "YIPPEE_ACTIVITY_REHEARSAL_UUID": identity[3], "YIPPEE_ACTIVITY_REHEARSAL_DATADIR": str(datadir),
            "YIPPEE_ACTIVITY_REHEARSAL_FILES": str(directory / "test-uploads")}

        def manage(label, arguments):
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.activity_deploy_rehearsal"],
                env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            for secret in (root_password, password, c["PASSWORD"], settings.SECRET_KEY):
                if secret:
                    output = output.replace(secret, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TEST_JWT_REDACTED]", output)
            (directory / (label + ".txt")).write_text(output, encoding="utf-8")
            require(result.returncode == 0, "Isolated " + label + " failed; see protected log")
            print("Isolated " + label + ": PASS", flush=True)
            return output

        planned = manage("migrate-plan", ["migrate", "--plan"])
        require(re.findall(r"^([a-z_]+\.\d{4}[^\r\n]*)", planned, re.M) == ["activities.0001_initial"], "Unexpected restore migration plan")
        manage("migrate", ["migrate", "activities", "0001_initial", "--noinput"])
        upgraded = isolated_state()
        assert_preserved(before, upgraded)
        report["upgraded"] = upgraded
        manage("test", ["test", "--keepdb", "--noinput", "-v", "2"])
        manage("check", ["check", "--database", "default"])
        manage("makemigrations", ["makemigrations", "--check", "--dry-run"])
        require(isolated_state() == upgraded, "Regression tests changed the restored source database")
        require(state() == before and plan() == [("activities", "0001_initial", False)], "Development changed during preparation")
        require(code_hashes() == report["code_hashes"], "Code changed during preparation")
        report["success"] = True
        print("PREPARATION PASS; development database unchanged", flush=True)
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        save(directory, "report.json", report)
        print("REPORT=" + str(directory / "report.json"), flush=True)


def evidence(path):
    directory = Path(path).resolve()
    require(directory.parent == (ROOT / ".mysql-rehearsal").resolve() and directory.name.startswith("activity-deploy-"), "Evidence path rejected")
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    require(report["success"] and report["restore_verified"] and report["isolated_server_shutdown"], "Preparation did not complete")
    require(code_hashes() == report["code_hashes"], "Prepared code changed")
    backup = Path(report["backup"]["path"]).resolve()
    require(backup.parent == directory and digest(backup.read_bytes()) == report["backup"]["sha256"], "Backup changed")
    return directory, report


def apply(path):
    from django.core.management import call_command
    from django.db import connection
    directory, report = evidence(path)
    require(not (directory / "apply-started.json").exists(), "Apply was already attempted; inspect state instead of retrying")
    validate_migration()
    require(state() == report["before"], "Development differs from verified backup; STOP")
    require(plan() == [("activities", "0001_initial", False)], "Final apply plan changed")
    save(directory, "apply-started.json", {"target": TARGET, "identity": SOURCE_IDENTITY})
    print("Final identity, backup, source preservation and sole migration target: PASS", flush=True)
    output = StringIO()
    try:
        with connection.execute_wrapper(guard_source), redirect_stdout(output), redirect_stderr(output):
            call_command("migrate", "activities", "0001_initial", interactive=False, stdout=output, stderr=output)
    finally:
        (directory / "development-migrate.txt").write_text(output.getvalue(), encoding="utf-8")
    verify(path)


def verify(path):
    directory, report = evidence(path)
    actual = state()
    assert_preserved(report["before"], actual)
    expected = report["upgraded"]
    require(actual["foreign_keys"] == expected["foreign_keys"], "Final FK differs from rehearsal")
    for name, table in actual["tables"].items():
        require(table["columns"] == expected["tables"][name]["columns"] and table["schema"] == expected["tables"][name]["schema"], "Final schema differs from rehearsal: " + name)
        if name != "django_migrations":
            require(table == expected["tables"][name], "Final data differs from rehearsal: " + name)
    require(plan() == [], "Migrations still pending")
    save(directory, "verify-final.json", {"success": True, "source": extra_source_info(), "after": actual})
    print("FINAL PASS: tables=%s migrations=%s; all original rows/schemas/FKs preserved" % (len(actual["tables"]), len(actual["migrations"])), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inspect", "prepare", "apply", "verify"))
    parser.add_argument("--evidence")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    if args.phase == "inspect":
        validate_migration()
        actual = state()
        print(json.dumps({**extra_source_info(), "tables": {k: v["count"] for k, v in actual["tables"].items()},
                          "migrations": actual["migrations"], "pending": plan()}, ensure_ascii=True, indent=2))
    elif args.phase == "prepare":
        prepare()
    else:
        require(args.evidence, "--evidence is required")
        (apply if args.phase == "apply" else verify)(args.evidence)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Raw database/driver exception text can contain secrets or user data.
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"), flush=True)
        sys.exit(1)
