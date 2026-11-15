"""Inspect, back up/restore/rehearse, then apply exactly the two approved migrations.

No retries, automatic repairs, existing test DB reuse or business-data writes.
All sensitive evidence stays in a fresh ignored, access-restricted directory.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from io import StringIO
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import uuid

import MySQLdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_activity_deploy import config, guard_source, normalized, require, SOURCE_IDENTITY
from scripts.check_favorite_source import capture
from scripts.prepare_favorites_deploy import inventory
from scripts.run_mysql_rehearsal import BIN, digest, snapshot

TARGETS = [("cart", "0001_initial"), ("purchases", "0001_initial")]
NEW_TABLES = {"cart_items", "purchase_entitlements"}
RESTORE = "test_yippee_migration_fresh"
SUITE = "test_yippee_migration_suite"


def fingerprints():
    paths = [p for app in ("accounts", "activities", "cart", "categories", "children", "config",
                           "email_verification", "favorites", "purchases", "scripts")
             for p in (ROOT / app).rglob("*.py")]
    paths += [ROOT / ".env", ROOT / "requirements.txt", ROOT / "manage.py"]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def plan():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    with connection.execute_wrapper(guard_source):
        executor = MigrationExecutor(connection)
        executor.loader.check_consistent_history(connection)
        require(not executor.loader.detect_conflicts(), "Migration graph conflicts")
        return [(m.app_label, m.name, backwards) for m, backwards in
                executor.migration_plan(executor.loader.graph.leaf_nodes())]


def review():
    from django.core.management import call_command
    from django.db import connection, models
    from django.db.migrations.operations import CreateModel
    statements = []
    for app, name in TARGETS:
        migration = import_module(f"{app}.migrations.{name}").Migration
        require(set(map(tuple, migration.dependencies)) == {
            ("activities", "0001_initial"), ("accounts", "__first__")}, "Unexpected migration dependencies")
        require(len(migration.operations) == 1 and isinstance(migration.operations[0], CreateModel),
                "Unexpected migration operation")
        op = migration.operations[0]
        table = "cart_items" if app == "cart" else "purchase_entitlements"
        require(op.options["db_table"] == table, "Unexpected migration table")
        fields = dict(op.fields)
        expected = {"id", "user", "activity"} | (set() if app == "cart" else {"status", "granted_at", "revoked_at"})
        require(set(fields) == expected, "Unexpected migration fields")
        for field_name, model in (("user", "accounts.user"), ("activity", "activities.activity")):
            field = fields[field_name]
            require(isinstance(field, models.ForeignKey) and field.remote_field.model.lower() == model
                    and field.remote_field.on_delete is (models.CASCADE if app == "cart" else models.PROTECT),
                    "Unexpected migration FK")
        constraints = op.options["constraints"]
        require(len(constraints) == (1 if app == "cart" else 2)
                and isinstance(constraints[0], models.UniqueConstraint)
                and constraints[0].fields == ("user", "activity"), "Unexpected UNIQUE")
        if app == "purchases":
            expected_check = (models.Q(status="active", revoked_at__isnull=True)
                              | models.Q(status="revoked", revoked_at__isnull=False))
            require(isinstance(constraints[1], models.CheckConstraint)
                    and constraints[1].condition == expected_check, "Unexpected entitlement CHECK")
        output = StringIO()
        with connection.execute_wrapper(guard_source):
            call_command("sqlmigrate", app, name, stdout=output)
        sql = re.sub(r"(?m)^--[^\n]*\n?", "", output.getvalue())
        for statement in sql.split(";"):
            statement = " ".join(statement.split())
            if not statement:
                continue
            require(statement.startswith((f"CREATE TABLE `{table}` (", f"ALTER TABLE `{table}` ADD CONSTRAINT ")),
                    "Unexpected migration SQL")
            statements.append(statement)
    require(len(statements) == 6, "Expected two CREATE TABLE and four FK statements")
    return statements


def inspect():
    from django.conf import settings
    require(not settings.CART_PURCHASE_ENTITLEMENTS_VERIFIED, "Purchase verification flag must remain False")
    require(subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() == "dev",
            "Expected dev branch")
    review()
    before = normalized(capture())
    require((len(before["database"]["tables"]), len(before["database"]["migrations"])) == (23, 26),
            "Source table/migration count differs; STOP")
    require(plan() == [(app, name, False) for app, name in TARGETS], "Unexpected migration plan")
    require(not NEW_TABLES.intersection(before["database"]["tables"]), "New tables already exist")
    require(int(before["identity"]["user_count"]) == int(before["identity"]["active_superusers"]) == 0,
            "Account state differs from prior report")
    previous = json.loads((ROOT / ".mysql-rehearsal/favorites-apply-7dfeec326257/report.json").read_text(encoding="utf-8"))
    require(previous["success"], "Prior deployment report was unsuccessful")
    for key in ("database", "identity", "private_files", "sample_files", "activity_api"):
        require(before[key] == previous["after"][key], "Source differs from prior deployment: " + key)
    require(all(before["migration_hashes"].get(p) == sha for p, sha in previous["after"]["migration_hashes"].items()),
            "An existing migration changed")
    require(sorted(row["id"] for row in before["activity_api"]["results"]) == [1, 2, 3, 4]
            and all(row["price"] == 0 for row in before["activity_api"]["results"]), "Source activities differ")
    return before


def preserved(before, after):
    require(set(after["tables"]) == set(before["tables"]) | NEW_TABLES, "Unexpected table set")
    require(set(map(tuple, after["migrations"])) == set(map(tuple, before["migrations"])) | set(TARGETS),
            "Unexpected migration history")
    additions = {"django_migrations": 2, "django_content_type": 2, "auth_permission": 8}
    for name, old in before["tables"].items():
        new = after["tables"][name]
        if name in additions:
            require(old["columns"] == new["columns"] and re.sub(r" AUTO_INCREMENT=\d+", "", old["schema"])
                    == re.sub(r" AUTO_INCREMENT=\d+", "", new["schema"]), "Metadata schema changed: " + name)
            require(set(old["row_hashes"]) <= set(new["row_hashes"])
                    and new["count"] == old["count"] + additions[name], "Metadata rows differ: " + name)
        else:
            require(new == old, "Business schema/data changed: " + name)
    fks = set(map(tuple, before["foreign_keys"])) | {
        (table, column, target, "id") for table in NEW_TABLES
        for column, target in (("user_id", "accounts_user"), ("activity_id", "activities"))}
    require(set(map(tuple, after["foreign_keys"])) == fks, "FK set differs")
    require(all(after["tables"][t]["count"] == 0 for t in NEW_TABLES), "New business rows unexpectedly exist")


def constraints(db):
    result = {}
    with db.cursor() as cursor:
        for table, unique in (("cart_items", "unique_user_activity_cart"),
                              ("purchase_entitlements", "unique_user_activity_entitlement")):
            cursor.execute("SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME=%s AND INDEX_NAME=%s AND NON_UNIQUE=0 ORDER BY SEQ_IN_INDEX", (table, unique))
            columns = [row[0] for row in cursor.fetchall()]
            require(columns == ["user_id", "activity_id"], "Missing or unexpected UNIQUE")
            result[table] = {"unique": unique, "columns": columns}
        cursor.execute("SELECT cc.CONSTRAINT_NAME,cc.CHECK_CLAUSE,tc.ENFORCED FROM information_schema.CHECK_CONSTRAINTS cc "
            "JOIN information_schema.TABLE_CONSTRAINTS tc ON cc.CONSTRAINT_SCHEMA=tc.CONSTRAINT_SCHEMA "
            "AND cc.CONSTRAINT_NAME=tc.CONSTRAINT_NAME WHERE tc.TABLE_SCHEMA=DATABASE() "
            "AND tc.TABLE_NAME='purchase_entitlements'")
        checks = cursor.fetchall()
        require(len(checks) == 1 and checks[0][0] == "entitlement_status_revoked_at" and checks[0][2] == "YES",
                "Missing or unenforced entitlement CHECK")
        result["checks"] = checks
    return normalized(result)


def protected_directory():
    run = ROOT / ".mysql-rehearsal" / ("cart-deploy-" + uuid.uuid4().hex[:12])
    run.mkdir(exist_ok=False)
    user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    return run


def prepare(before):
    from django.conf import settings
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    run = protected_directory()
    report = {"success": False, "before": before, "code_hashes": fingerprints(),
              "development_written": False, "existing_test_database_reused": False, "sql": review()}
    print("ARTIFACTS=" + str(run), flush=True)
    (run / "git-status-before.txt").write_text(subprocess.check_output(["git", "status", "--short"], text=True), encoding="utf-8")
    process = admin = None
    verified = False
    password, root_password = secrets.token_hex(32), secrets.token_hex(32)
    c = config()

    def save():
        (run / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    save()
    try:
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        client = run / "source-client.cnf"
        client.write_text("[client]\n" + "\n".join(k + "=" + option(c[k.upper()]) for k in ("host", "port", "user", "password")) + "\n", encoding="utf-8")
        backup = run / "yippee_club_db.sql"
        result = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(client), "--protocol=TCP",
            "--single-transaction", "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF",
            "--skip-add-drop-table", "--skip-add-locks", "--skip-disable-keys", "--hex-blob",
            "--default-character-set=utf8mb4", "--result-file=" + str(backup), c["NAME"]], capture_output=True)
        require(result.returncode == 0 and backup.stat().st_size > 0, "Backup failed; no development apply allowed")
        report["backup"] = {"path": str(backup), "bytes": backup.stat().st_size, "sha256": digest(backup.read_bytes())}
        require(normalized(capture()) == before, "Source changed during backup")
        copied_files = run / "restored-uploads"
        shutil.copytree(ROOT / "private_uploads", copied_files)
        require(inventory(copied_files) == before["private_files"], "Copied file hashes differ")
        print("Fresh backup and independent private-file copies: PASS", flush=True)
        save()
        datadir = run / "data"
        result = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
            "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (run / "initialize.txt").write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, "New isolated MySQL initialization failed")
        with (run / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(run / "server.log"), "--pid-file=" + str(run / "server.pid")],
                stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
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
        require(admin is not None, "Fresh isolated startup timeout")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            require(identity[:2] == (9133307, 33307) and Path(identity[2]).resolve() == datadir.resolve()
                    and identity[3] != SOURCE_IDENTITY[2], "Isolated server identity mismatch")
            verified = True
            report["isolated_identity"] = identity
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE 'test_yippee%'")
            require(not cursor.fetchall(), "Fresh instance unexpectedly has test schemas")
            cursor.execute(f"CREATE DATABASE `{RESTORE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute("SELECT @@GLOBAL.partial_revokes")
            require(cursor.fetchone()[0] == 0, "Unexpected grant mode")
            for database in (RESTORE, SUITE):
                scope = database.replace("_", r"\_")
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        (run / "root-client.cnf").write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + root_password + "\n", encoding="utf-8")
        target_client = run / "target-client.cnf"
        target_client.write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=yippee_rehearsal\npassword=" + password + "\n", encoding="utf-8")
        with backup.open("rb") as payload:
            result = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(target_client), "--protocol=TCP",
                "--default-character-set=utf8mb4", RESTORE], stdin=payload, capture_output=True)
        require(result.returncode == 0, "Backup restore failed")

        def isolated_state():
            db = MySQLdb.connect(host="127.0.0.1", port=33307, user="yippee_rehearsal", passwd=password,
                                 db=RESTORE, charset="utf8mb4", connect_timeout=5)
            try:
                return normalized(snapshot(db)), constraints(db) if report.get("migrated") else None
            finally:
                db.close()

        require(isolated_state()[0] == before["database"], "Restore schema/rows/FKs/history differ from backup source")
        report["restore_exact"] = True
        print("Full restore matches all source schemas/rows/FKs/history: PASS", flush=True)
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_DATABASE": RESTORE,
            "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": password,
            "YIPPEE_CART_REHEARSAL_UUID": identity[3], "YIPPEE_CART_REHEARSAL_DATADIR": str(datadir),
            "YIPPEE_CART_REHEARSAL_FILES": str(copied_files)}

        def manage(label, arguments):
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.cart_deploy_rehearsal"],
                cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            for secret in (password, root_password, c["PASSWORD"], settings.SECRET_KEY):
                if secret:
                    output = output.replace(secret, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT_REDACTED]", output)
            (run / (label + ".txt")).write_text(output, encoding="utf-8")
            require(result.returncode == 0, "Isolated " + label + " failed; see protected log")
            print("Isolated " + label + ": PASS", flush=True)
            return output

        planned = manage("plan", ["migrate", "--plan"])
        require(re.findall(r"^([a-z_]+\.\d{4}[^\r\n]*)", planned, re.M)
                == [app + "." + name for app, name in TARGETS], "Unexpected restored migration plan")
        for app, name in TARGETS:
            manage(app + "-sql", ["sqlmigrate", app, name])
            manage(app + "-migrate", ["migrate", app, name, "--noinput"])
        report["migrated"] = True
        upgraded, indexes = isolated_state()
        preserved(before["database"], upgraded)
        report.update(upgraded=upgraded, constraints=indexes)
        save()
        # No --keepdb: SUITE does not exist before this command and is removed afterwards.
        output = manage("test", ["test", "--noinput", "-v", "2"])
        require("Ran 151 tests" in output and "OK (skipped=2)" in output, "Regression counts differ from baseline")
        manage("check", ["check", "--database", "default"])
        manage("makemigrations", ["makemigrations", "--check", "--dry-run"])
        require(isolated_state() == (upgraded, indexes), "Tests/checks changed restored preservation DB")
        require(inventory(copied_files) == before["private_files"], "Restored private files changed")
        require(normalized(capture()) == before and fingerprints() == report["code_hashes"], "Source/code changed during rehearsal")
        require(plan() == [(app, name, False) for app, name in TARGETS], "Source plan changed during rehearsal")
        report["success"] = True
        print("PREPARATION PASS: development DB untouched; exact two-migration rehearsal verified", flush=True)
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        save()
        print("REPORT=" + str(run / "report.json"), flush=True)
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inspect", "prepare"))
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    before = inspect()
    print(json.dumps({"identity": before["identity"], "tables": 23, "migrations": 26,
                      "pending": plan(), "purchase_verification": False}, ensure_ascii=True, indent=2), flush=True)
    if args.phase == "prepare":
        prepare(before)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"), flush=True)
        sys.exit(1)
