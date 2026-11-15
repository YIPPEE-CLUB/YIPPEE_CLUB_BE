"""Read-only development backup and NEW isolated active-child rehearsal.

There is deliberately NO development apply operation. Concurrent development
writes have not been confirmed stopped; the user has deferred actual apply.
"""
from contextlib import redirect_stdout
from importlib import import_module
from io import StringIO
import hashlib
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
from scripts.prepare_activity_deploy import config, source, normalized, guard_source, require, SOURCE_IDENTITY
from scripts.deploy_cart_db import plan, fingerprints
from scripts.check_favorite_source import capture
from scripts.prepare_favorites_deploy import inventory
from scripts.run_mysql_rehearsal import BIN, snapshot, digest

TARGET = ("accounts", "0004_user_active_child")
RESTORE = "test_yippee_migration_fresh"
SUITE = "test_yippee_migration_suite"


def review():
    from django.core.management import call_command
    from django.db import connection, models
    from django.db.migrations.operations import AddField
    from children.models import Child
    migration = import_module("accounts.migrations.0004_user_active_child").Migration
    require(set(migration.dependencies) == {
        ("accounts", "0003_user_agreements_user_name_user_nickname_user_phone_and_more"),
        ("children", "0001_initial")}, "Unexpected migration dependencies")
    require(len(migration.operations) == 1 and isinstance(migration.operations[0], AddField), "Unexpected operations")
    op = migration.operations[0]
    field = op.field
    require(op.model_name == "user" and op.name == "active_child" and isinstance(field, models.ForeignKey)
            and field.null and field.blank and not field.editable and field.remote_field.on_delete is models.SET_NULL
            and field.remote_field.model == "children.child" and Child._meta.db_table == "children", "Unexpected field/FK")
    output = StringIO()
    with connection.execute_wrapper(guard_source):
        call_command("sqlmigrate", *TARGET, stdout=output)
    sql = re.sub(r"(?m)^--[^\n]*\n?", "", output.getvalue())
    statements = [" ".join(s.split()) for s in sql.split(";") if s.strip()]
    require(len(statements) == 1 and statements[0].startswith(
        "ALTER TABLE `accounts_user` ADD COLUMN `active_child_id` bigint NULL")
        and re.search(r"FOREIGN KEY \(`active_child_id`\) REFERENCES `children`\s*\(`id`\)", statements[0]),
        "Unexpected migration SQL")
    return statements


def inspect():
    from django.conf import settings
    require(not settings.CART_PURCHASE_ENTITLEMENTS_VERIFIED, "Purchase verification must remain False")
    require(subprocess.check_output(["git", "branch", "--show-current"], text=True).strip() == "dev", "Expected dev")
    before = normalized(capture())
    previous = json.loads((ROOT / ".mysql-rehearsal/cart-deploy-1f7fdfc90b4f/apply-report.json").read_text(encoding="utf-8"))["after"]
    for key in ("database", "identity", "private_files", "sample_files", "activity_api"):
        require(before[key] == previous[key], "Source differs from previous state: " + key)
    require((len(before["database"]["tables"]), len(before["database"]["migrations"])) == (25, 28), "Unexpected counts")
    require(plan() == [(*TARGET, False)], "Only accounts.0004 may be pending")
    require(all(before["migration_hashes"].get(p) == sha for p, sha in previous["migration_hashes"].items()),
            "An existing migration changed")
    tested = json.loads((ROOT / ".mysql-rehearsal/cart-tests-d382bebcb5dd/active-child-source-hashes.json").read_text(encoding="utf-8"))
    actual = {p.replace("\\", "/"): sha for p, sha in fingerprints().items()}
    require(all(actual.get(p) == sha for p, sha in tested.items()), "Tested source changed")
    return before


def upgrade_snapshot(db, before):
    state = normalized(snapshot(db))
    old_columns = [row[0] for row in before["tables"]["accounts_user"]["columns"]]
    with db.cursor() as cursor:
        cursor.execute("SELECT " + ",".join("`" + n + "`" for n in old_columns) + " FROM accounts_user")
        rows = sorted(json.dumps(row, default=str, ensure_ascii=True) for row in cursor.fetchall())
        projected = digest("\n".join(rows).encode())
        cursor.execute("SELECT COUNT(*) FROM accounts_user WHERE active_child_id IS NOT NULL")
        require(cursor.fetchone()[0] == 0, "Existing users were assigned an active child")
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                       "AND TABLE_NAME='accounts_user' ORDER BY INDEX_NAME,SEQ_IN_INDEX")
        require("active_child_id" in [row[0] for row in cursor.fetchall()], "Active-child index missing")
    return state, projected


def preserved(before, after, projected):
    require(set(before["tables"]) == set(after["tables"]), "Table set changed")
    require(set(map(tuple, after["migrations"])) == set(map(tuple, before["migrations"])) | {TARGET}, "History differs")
    require(set(map(tuple, after["foreign_keys"])) == set(map(tuple, before["foreign_keys"])) | {
        ("accounts_user", "active_child_id", "children", "id")}, "Unexpected FK changes")
    for name, old in before["tables"].items():
        new = after["tables"][name]
        if name == "django_migrations":
            require(old["columns"] == new["columns"] and
                re.sub(r" AUTO_INCREMENT=\d+", "", old["schema"]) == re.sub(r" AUTO_INCREMENT=\d+", "", new["schema"])
                and new["count"] == old["count"] + 1 and set(old["row_hashes"]) <= set(new["row_hashes"]), "Migration metadata changed")
        elif name == "accounts_user":
            require([row for row in new["columns"] if row[0] != "active_child_id"] == old["columns"], "Old User columns changed")
            require(len(new["columns"]) == len(old["columns"]) + 1 and new["count"] == old["count"]
                    and projected == old["rows_sha256"], "Old User data changed")
            stripped = "\n".join(line for line in new["schema"].splitlines() if "active_child_id" not in line)
            require(re.sub(r",\n\)", "\n)", stripped) == old["schema"], "Old User PK/index/schema changed")
        else:
            require(old == new, "Other service data/schema changed: " + name)


def main():
    os.chdir(ROOT)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings
    before = inspect()
    sql = review()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    run = ROOT / ".mysql-rehearsal" / ("active-child-deploy-" + uuid.uuid4().hex[:12])
    run.mkdir(exist_ok=False)
    windows_user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r", windows_user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    report = {"preparation_success": False, "development_applied": False, "before": before,
              "apply_deferred_by_user": True, "concurrent_writes_stopped_confirmed": False,
              "code_hashes": fingerprints(), "sql": sql, "old_test_database_reused": False}
    print("ARTIFACTS=" + str(run), flush=True)
    (run / "git-status.txt").write_text(subprocess.check_output(["git", "status", "--short"], text=True), encoding="utf-8")
    password, root_password = secrets.token_hex(32), secrets.token_hex(32)
    c = config()
    admin = process = None
    verified = False

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
        require(result.returncode == 0 and backup.stat().st_size > 0, "Source backup failed")
        report["backup"] = {"path": str(backup), "bytes": backup.stat().st_size, "sha256": digest(backup.read_bytes())}
        require(normalized(capture()) == before, "Source changed during backup")
        files = run / "restored-uploads"
        shutil.copytree(ROOT / "private_uploads", files)
        require(inventory(files) == before["private_files"], "Copied file hashes differ")
        print("Fresh read-only backup and file copies: PASS", flush=True)
        save()
        datadir = run / "data"
        result = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
            "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (run / "initialize.txt").write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, "New isolated initialization failed")
        with (run / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(run / "server.log"), "--pid-file=" + str(run / "server.pid")],
                stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            require(process.poll() is None, "Isolated server exited")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        require(admin is not None, "Isolated server startup timed out")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            require(identity[:2] == (9133307, 33307) and Path(identity[2]).resolve() == datadir.resolve()
                    and identity[3] != SOURCE_IDENTITY[2], "Isolated server identity rejected")
            verified = True
            report["isolated_identity"] = identity
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE 'test_yippee%'")
            require(not cursor.fetchall(), "Fresh instance already has test schemas")
            cursor.execute("SELECT @@GLOBAL.partial_revokes")
            require(cursor.fetchone()[0] == 0, "Unexpected grant mode")
            cursor.execute(f"CREATE DATABASE `{RESTORE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            for name in (RESTORE, SUITE):
                scope = name.replace("_", r"\_")
                cursor.execute(f"GRANT ALL PRIVILEGES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        target = run / "target-client.cnf"
        target.write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=yippee_rehearsal\npassword=" + password + "\n", encoding="utf-8")
        (run / "root-client.cnf").write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + root_password + "\n", encoding="utf-8")
        # RESTORE was just created on a newly initialized, identified instance.
        with backup.open("rb") as payload:
            result = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(target), "--protocol=TCP",
                "--default-character-set=utf8mb4", RESTORE], stdin=payload, capture_output=True)
        require(result.returncode == 0, "Isolated restore failed")

        def state(upgraded=False):
            db = MySQLdb.connect(host="127.0.0.1", port=33307, user="yippee_rehearsal", passwd=password,
                                 db=RESTORE, charset="utf8mb4", connect_timeout=5)
            try:
                return upgrade_snapshot(db, before["database"]) if upgraded else normalized(snapshot(db))
            finally:
                db.close()

        require(state() == before["database"], "Backup restore differs in table/columns/index/FK/rows/history")
        report["restore_exact"] = True
        print("Full independent restore matches source schema/rows/index/FK/history: PASS", flush=True)
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_DATABASE": RESTORE,
            "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": password,
            "YIPPEE_ACTIVE_CHILD_REHEARSAL_UUID": identity[3], "YIPPEE_ACTIVE_CHILD_REHEARSAL_DATADIR": str(datadir),
            "YIPPEE_ACTIVE_CHILD_REHEARSAL_FILES": str(files)}

        def manage(label, args):
            result = subprocess.run([sys.executable, "manage.py", *args, "--settings=config.active_child_deploy_rehearsal"],
                env=environment, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
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
        require(re.findall(r"^([a-z_]+\.\d{4}[^\r\n]*)", planned, re.M) == ["accounts.0004_user_active_child"], "Unexpected restore plan")
        manage("sql", ["sqlmigrate", *TARGET])
        manage("migrate", ["migrate", *TARGET, "--noinput"])
        upgraded, projected = state(True)
        preserved(before["database"], upgraded, projected)
        report.update(upgraded=upgraded, old_user_rows_sha256=projected, migration_rehearsal_success=True)
        save()
        output = manage("test", ["test", "--noinput", "-v", "2"])
        require("Ran 169 tests" in output and "OK (skipped=2)" in output, "Unexpected test baseline")
        manage("check", ["check", "--database", "default"])
        manage("makemigrations", ["makemigrations", "--check", "--dry-run"])
        require(state(True) == (upgraded, projected), "Regression changed preservation copy")
        require(inventory(files) == before["private_files"], "Isolated copied files changed")
        report["after"] = normalized(capture())
        require(report["after"] == before and plan() == [(*TARGET, False)], "Source changed during rehearsal")
        require(fingerprints() == report["code_hashes"], "Source code/environment changed")
        report["preparation_success"] = True
        print("PREPARATION PASS; DEVELOPMENT APPLY DEFERRED: concurrent writer stop unconfirmed", flush=True)
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


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"), flush=True)
        sys.exit(1)
