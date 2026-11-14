"""Back up source read-only, validate 0003 upgrade in the existing isolated server.

prepare never writes to development. verify-final is also read-only.
Actual deployment uses separately reviewed manage.py commands.
"""
import argparse
import configparser
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import uuid

import MySQLdb

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "0003_user_agreements_user_name_user_nickname_user_phone_and_more"
ISOLATED = ROOT / ".mysql-rehearsal/auth-api-cad00793f0c4"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "verify-before", "verify-final"))
    parser.add_argument("--evidence")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.conf import settings
    from scripts.run_mysql_rehearsal import BIN, digest, migration_hashes, snapshot

    config = settings.DATABASES["default"]
    require((config["NAME"], int(config["PORT"]), config["USER"]) == ("yippee_club_db", 3306, "yippee_app"), "Source configuration rejected")

    def source_snapshot():
        db = MySQLdb.connect(host=config["HOST"], port=int(config["PORT"]), user=config["USER"],
                             passwd=config["PASSWORD"], db=config["NAME"], charset="utf8mb4", connect_timeout=5)
        try:
            with db.cursor() as cursor:
                cursor.execute("SET SESSION TRANSACTION READ ONLY")
                cursor.execute("SELECT DATABASE(),CURRENT_USER(),@@server_uuid,@@port")
                identity = cursor.fetchone()
                require(identity == ("yippee_club_db", "yippee_app@localhost", "5491c807-5688-11f1-a0bf-c86e08e6aa63", 3306), "Source identity mismatch")
            return identity, json.loads(json.dumps(snapshot(db), default=str))
        finally:
            db.rollback()
            db.close()

    if args.phase != "prepare":
        directory = Path(args.evidence).resolve()
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        require(report["success"] and report["isolated_server_shutdown"], "Preparation incomplete")
        require(digest(Path(report["backup"]["path"]).read_bytes()) == report["backup"]["sha256"], "Backup changed")
        require(migration_hashes() == report["migration_hashes"], "Migration code changed")
        identity, actual = source_snapshot()
        if args.phase == "verify-before":
            require(actual == report["before"], "Source changed since backup; STOP")
        else:
            expected = report["upgraded"]
            require(actual["migrations"] == expected["migrations"], "Unexpected final migration set")
            require(actual["foreign_keys"] == expected["foreign_keys"], "Unexpected final FK set")
            require(actual["tables"].keys() == expected["tables"].keys(), "Unexpected final table set")
            for table, state in actual["tables"].items():
                require(state["columns"] == expected["tables"][table]["columns"], "Column mismatch: " + table)
                require(state["schema"] == expected["tables"][table]["schema"], "Schema mismatch: " + table)
                require(state["count"] == expected["tables"][table]["count"], "Count mismatch: " + table)
            for table, before in report["before"]["tables"].items():
                require(set(before["row_hashes"]) <= set(actual["tables"][table]["row_hashes"]), "Original data changed: " + table)
            require((len(actual["tables"]), len(actual["migrations"])) == (16, 22), "Wrong final counts")
        (directory / (args.phase + ".json")).write_text(json.dumps({"identity": identity, "state": actual}, indent=2), encoding="utf-8")
        print(json.dumps({"phase": args.phase, "status": "PASS", "identity": identity,
                          "tables": len(actual["tables"]), "migrations": len(actual["migrations"])}))
        return

    old_report = json.loads((ROOT / ".mysql-rehearsal/20261113-181637-5c83f13f/report.json").read_text())
    require(all(migration_hashes().get(path) == value for path, value in old_report["migration_hashes_before"].items()), "Existing migration changed")
    identity, before = source_snapshot()
    require((len(before["tables"]), len(before["migrations"])) == (15, 21), "Source no longer at pre-0003 state")
    require(before["tables"]["accounts_user"]["count"] == 0, "Unexpected user data; review preservation plan")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    directory = ROOT / ".mysql-rehearsal" / ("auth-deploy-" + uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    windows_user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", windows_user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    print("ARTIFACTS=" + str(directory), flush=True)
    report = {"source_identity": identity, "before": before, "migration_hashes": migration_hashes(), "success": False}
    parser_config = configparser.ConfigParser(interpolation=None)
    parser_config.read(ISOLATED / "root-client.cnf", encoding="utf-8")
    password = parser_config["client"]["password"]
    require((parser_config["client"]["host"], parser_config["client"]["port"]) == ("127.0.0.1", "33307"), "Isolated credential target rejected")
    previous = json.loads((ISOLATED / "report.json").read_text())
    require(previous["success"] and previous["isolated_server_shutdown"], "Previous isolated run incomplete")
    admin = None
    process = None
    verified = False
    try:
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

        source_client = directory / "source-client.cnf"
        source_client.write_text("[client]\n" + "\n".join(key + "=" + option(value) for key, value in (
            ("host", config["HOST"]), ("port", config["PORT"]), ("user", config["USER"]), ("password", config["PASSWORD"]))) + "\n", encoding="utf-8")
        backup = directory / "yippee_club_db.sql"
        result = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(source_client), "--protocol=TCP",
                                 "--single-transaction", "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF",
                                 "--skip-add-drop-table", "--skip-add-locks", "--skip-disable-keys", "--hex-blob",
                                 "--default-character-set=utf8mb4", "--result-file=" + str(backup), "yippee_club_db"], capture_output=True)
        require(result.returncode == 0, "Read-only backup failed")
        report["backup"] = {"path": str(backup), "sha256": digest(backup.read_bytes()), "bytes": backup.stat().st_size}
        print("New read-only backup: OK", flush=True)
        with (directory / "isolated-console.txt").open("wb") as console:
            process = subprocess.Popen([str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(ISOLATED / "data"), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(directory / "isolated-server.log"),
                "--pid-file=" + str(directory / "isolated.pid")], stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            require(process.poll() is None, "Existing isolated server failed to start")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd=password, charset="utf8mb4", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        require(admin is not None, "Isolated startup timeout")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            server = cursor.fetchone()
            require(server[:2] == (9133307, 33307) and Path(server[2]).resolve() == (ISOLATED / "data").resolve()
                    and server[3] == previous["server_identity"][3], "Wrong isolated server")
            verified = True
            report["isolated_identity"] = server
            cursor.execute("USE `test_yippee_migration_fresh`")
            cursor.execute("SHOW FULL TABLES")
            require(not cursor.fetchall(), "Existing isolated restore target is not empty; no overwrite allowed")
        with backup.open("rb") as payload:
            result = subprocess.run([str(BIN / "mysql.exe"), "--defaults-file=" + str(ISOLATED / "root-client.cnf"),
                                     "--protocol=TCP", "--default-character-set=utf8mb4", "test_yippee_migration_fresh"],
                                    stdin=payload, capture_output=True)
        require(result.returncode == 0, "Independent restore failed")

        def isolated_snapshot():
            db = MySQLdb.connect(host="127.0.0.1", port=33307, user="yippee_rehearsal", passwd=password,
                                 db="test_yippee_migration_fresh", charset="utf8mb4", connect_timeout=5)
            try:
                return json.loads(json.dumps(snapshot(db), default=str))
            finally:
                db.close()

        require(isolated_snapshot() == before, "Restored schema/rows/FK/history mismatch")
        print("Independent restore equals every source table/row hash/FK/migration: PASS", flush=True)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_DATABASE": "test_yippee_migration_fresh",
               "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": password}

        def manage(arguments):
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.user_model_rehearsal"],
                                     env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = result.stdout + result.stderr
            for secret in (password, config["PASSWORD"], settings.SECRET_KEY):
                if secret:
                    output = output.replace(secret, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TEST_JWT_REDACTED]", output)
            label = "http-smoke" if arguments[0] == "shell" else arguments[0] + ("-plan" if "--plan" in arguments else "")
            (directory / (label + ".txt")).write_text(output, encoding="utf-8")
            require(result.returncode == 0, "Isolated " + label + " failed; inspect preserved log")
            print("Isolated " + label + ": PASS", flush=True)
            return output

        plan = manage(["migrate", "accounts", MIGRATION, "--plan"])
        require(re.findall(r"^([a-z_]+\.\d{4}[^\r\n]*)", plan, re.M) == ["accounts." + MIGRATION], "Unexpected isolated migration plan")
        manage(["migrate", "accounts", MIGRATION, "--noinput"])
        report["upgraded"] = isolated_snapshot()
        require((len(report["upgraded"]["tables"]), len(report["upgraded"]["migrations"])) == (16, 22), "Wrong isolated upgrade counts")
        manage(["test", "--keepdb", "--noinput", "-v", "2"])
        manage(["shell", "-c", "from scripts.auth_http_smoke import run; run()"])
        require(source_snapshot()[1] == before, "Source changed during validation")
        require(migration_hashes() == report["migration_hashes"], "Migration code changed during validation")
        report["success"] = True
        print("Preparation PASS; development DB still unchanged", flush=True)
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        (directory / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Report: " + str(directory / "report.json"), flush=True)


if __name__ == "__main__":
    main()
