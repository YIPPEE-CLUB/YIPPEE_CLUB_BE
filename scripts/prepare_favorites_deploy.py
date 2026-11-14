"""Inspection and isolated rehearsal only. There is NO development apply phase."""
import argparse
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
from scripts.run_mysql_rehearsal import BIN, digest, snapshot
from scripts.check_favorite_source import capture

TARGET = ("favorites", "0001_initial")
RESTORE, HTTP, SUITE = "test_yippee_migration_fresh", "test_yippee_migration_legacy", "test_yippee_migration_suite"


def source_plan():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    with connection.execute_wrapper(guard_source):
        loader = MigrationExecutor(connection)
        loader.loader.check_consistent_history(connection)
        return [(m.app_label, m.name, backwards) for m, backwards in
                loader.migration_plan(loader.loader.graph.leaf_nodes())]


def review_migration():
    from importlib import import_module
    from django.db import models
    from django.db.migrations.operations import CreateModel
    migration = import_module("favorites.migrations.0001_initial").Migration
    require(len(migration.operations) == 1 and isinstance(migration.operations[0], CreateModel), "Unexpected favorite migration operation")
    op = migration.operations[0]
    require(op.name == "Favorite" and op.options["db_table"] == "favorites", "Unexpected favorite table")
    fields = dict(op.fields)
    require(set(fields) == {"id", "user", "activity"}, "Unexpected favorite fields")
    for name, model in (("user", "accounts.user"), ("activity", "activities.activity")):
        field = fields[name]
        require(isinstance(field, models.ForeignKey) and field.remote_field.model.lower() == model and
                field.remote_field.on_delete is models.CASCADE, "Unexpected favorite FK")
    constraints = op.options["constraints"]
    require(len(constraints) == 1 and isinstance(constraints[0], models.UniqueConstraint) and
            constraints[0].fields == ("user", "activity"), "Unexpected favorite UNIQUE")
    require(set(map(tuple, migration.dependencies)) == {("activities", "0001_initial"), ("accounts", "__first__")}, "Unexpected dependencies")


def fingerprints():
    paths = [p for folder in ("accounts", "email_verification", "children", "categories", "activities", "favorites", "config")
             for p in (ROOT / folder).rglob("*.py")]
    paths += [ROOT / "scripts" / name for name in ("prepare_favorites_deploy.py", "favorites_http_smoke.py",
        "check_favorite_source.py", "prepare_activity_deploy.py", "run_mysql_rehearsal.py")]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def inventory(root):
    return {str(p.relative_to(root)): {"bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
            for p in sorted(root.rglob("*")) if p.is_file()}


def preserved(before, upgraded):
    require(set(upgraded["tables"]) == set(before["tables"]) | {"favorites"}, "Unexpected upgrade table set")
    require(set(map(tuple, upgraded["migrations"])) == set(map(tuple, before["migrations"])) | {TARGET}, "Unexpected migration history")
    additions = {"django_migrations": 1, "django_content_type": 1, "auth_permission": 4}
    for name, old in before["tables"].items():
        new = upgraded["tables"][name]
        if name in additions:
            require(old["columns"] == new["columns"] and re.sub(r" AUTO_INCREMENT=\d+", "", old["schema"]) ==
                    re.sub(r" AUTO_INCREMENT=\d+", "", new["schema"]), "Existing metadata schema changed: " + name)
            require(set(old["row_hashes"]) <= set(new["row_hashes"]) and new["count"] == old["count"] + additions[name], "Existing metadata rows changed: " + name)
        else:
            require(new == old, "Existing business data/schema changed: " + name)
    fks = set(map(tuple, before["foreign_keys"])) | {("favorites", "user_id", "accounts_user", "id"),
        ("favorites", "activity_id", "activities", "id")}
    require(set(map(tuple, upgraded["foreign_keys"])) == fks and upgraded["tables"]["favorites"]["count"] == 0, "Favorite FK/count mismatch")


def inspect_source():
    review_migration()
    before = normalized(capture())
    state = before["database"]
    require((len(state["tables"]), len(state["migrations"])) == (22, 25), "Unexpected development DB state")
    rows = before["activity_api"]["results"]
    require(sorted(row["id"] for row in rows) == [1, 2, 3, 4] and all(row["price"] == 0 for row in rows), "Source activities differ")
    require(before["identity"]["categories"] == [[1, "신체운동·건강"], [2, "자연탐구"]] and len(before["private_files"]) == 20, "Source categories/files differ")
    require(source_plan() == [("favorites", "0001_initial", False)], "Unexpected source migration plan")
    return before


def prepare(before):
    from django.conf import settings
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    run = ROOT / ".mysql-rehearsal" / ("favorites-deploy-" + uuid.uuid4().hex[:12])
    run.mkdir(exist_ok=False)
    user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    print("ARTIFACTS=" + str(run), flush=True)
    report = {"success": False, "before": before, "code_hashes": fingerprints(), "development_written": False,
              "prior_rehearsal_modified": False, "source_plan": [["favorites", "0001_initial", False]]}
    process = admin = None
    verified = False
    root_password, password = secrets.token_hex(32), secrets.token_hex(32)
    c = config()
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
        require(result.returncode == 0 and backup.stat().st_size > 0, "Read-only backup failed")
        report["backup"] = {"path": str(backup), "bytes": backup.stat().st_size, "sha256": digest(backup.read_bytes())}
        require(normalized(capture()) == before, "Source changed during backup")
        copied_files = run / "restored-uploads"
        shutil.copytree(ROOT / "private_uploads", copied_files)
        require(inventory(copied_files) == before["private_files"], "Private file copy mismatch")
        print("Fresh read-only backup and 20 independent file copies: PASS", flush=True)
        datadir = run / "data"
        result = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
            "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (run / "initialize.txt").write_bytes(result.stdout + result.stderr)
        require(result.returncode == 0, "Fresh MySQL initialization failed")
        with (run / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(run / "server.log"), "--pid-file=" + str(run / "server.pid")],
                stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            require(process.poll() is None, "Fresh MySQL server exited")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        require(admin is not None, "Fresh MySQL startup timed out")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            require(identity[:2] == (9133307, 33307) and Path(identity[2]).resolve() == datadir.resolve() and
                    identity[3] != SOURCE_IDENTITY[2], "Fresh isolated server identity mismatch")
            verified = True
            report["isolated_identity"] = identity
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("SELECT @@GLOBAL.partial_revokes")
            require(cursor.fetchone()[0] == 0, "Unexpected grant mode")
            for database in (RESTORE, HTTP, SUITE):
                cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                scope = database.replace("_", r"\_")
                cursor.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,REFERENCES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        (run / "root-client.cnf").write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + root_password + "\n", encoding="utf-8")
        target_client = run / "target-client.cnf"
        target_client.write_text("[client]\nhost=127.0.0.1\nport=33307\nuser=yippee_rehearsal\npassword=" + password + "\n", encoding="utf-8")

        def isolated_state(database):
            require(database in (RESTORE, HTTP), "Unknown snapshot target")
            db = MySQLdb.connect(host="127.0.0.1", port=33307, user="yippee_rehearsal", passwd=password,
                                 db=database, charset="utf8mb4", connect_timeout=5)
            try:
                return normalized(snapshot(db))
            finally:
                db.close()

        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_PORT": "33307",
            "YIPPEE_REHEARSAL_PASSWORD": password, "YIPPEE_FAVORITES_REHEARSAL_UUID": identity[3],
            "YIPPEE_FAVORITES_REHEARSAL_DATADIR": str(datadir), "YIPPEE_FAVORITES_REHEARSAL_FILES": str(copied_files)}
        def manage(database, label, arguments):
            require(database in (RESTORE, HTTP), "Unknown Django target")
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.favorites_deploy_rehearsal"],
                env={**environment, "YIPPEE_REHEARSAL_DATABASE": database}, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            for secret in (password, root_password, c["PASSWORD"], settings.SECRET_KEY):
                if secret:
                    output = output.replace(secret, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[JWT_REDACTED]", output)
            (run / (label + ".txt")).write_text(output, encoding="utf-8")
            require(result.returncode == 0, "Isolated " + label + " failed; see protected log")
            print("Isolated " + label + ": PASS", flush=True)
            return output

        report["restores"] = {}
        for database, prefix in ((RESTORE, "preservation"), (HTTP, "http-copy")):
            with backup.open("rb") as payload:
                result = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(target_client), "--protocol=TCP",
                    "--default-character-set=utf8mb4", database], stdin=payload, capture_output=True)
            require(result.returncode == 0 and isolated_state(database) == before["database"], "Independent backup restore mismatch")
            print(prefix + " full restore matches schema/rows/FK/history: PASS", flush=True)
            planned = manage(database, prefix + "-plan", ["migrate", "--plan"])
            require(re.findall(r"^([a-z_]+\.\d{4}[^\r\n]*)", planned, re.M) == ["favorites.0001_initial"], "Unexpected isolated plan")
            manage(database, prefix + "-sql", ["sqlmigrate", "favorites", "0001_initial"])
            manage(database, prefix + "-migrate", ["migrate", "favorites", "0001_initial", "--noinput"])
            upgraded = isolated_state(database)
            preserved(before["database"], upgraded)
            report["restores"][database] = {"restore_exact": True, "upgraded": upgraded}
        stable = isolated_state(RESTORE)
        manage(RESTORE, "test", ["test", "--keepdb", "--noinput", "-v", "2"])
        manage(RESTORE, "check", ["check", "--database", "default"])
        manage(RESTORE, "makemigrations", ["makemigrations", "--check", "--dry-run"])
        manage(HTTP, "http", ["shell", "-c", "from scripts.favorites_http_smoke import run; run()"])
        require(isolated_state(RESTORE) == stable, "Regression/HTTP checks changed the preservation copy")
        require(inventory(copied_files) == before["private_files"], "Copied private files changed")
        report["after"] = normalized(capture())
        require(report["after"] == before and source_plan() == [("favorites", "0001_initial", False)], "Development changed during rehearsal")
        require(fingerprints() == report["code_hashes"], "Code changed during rehearsal")
        report["success"] = True
        print("PREPARATION PASS: no development DDL, DML, account or favorite creation", flush=True)
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        (run / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("REPORT=" + str(run / "report.json"), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("inspect", "prepare"))
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    before = inspect_source()
    if args.phase == "inspect":
        print(json.dumps({"source": before["identity"], "tables": len(before["database"]["tables"]),
            "migrations": len(before["database"]["migrations"]), "activities": 4, "files": 20,
            "pending": source_plan()}, indent=2, ensure_ascii=True))
    else:
        prepare(before)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"), flush=True)
        sys.exit(1)
