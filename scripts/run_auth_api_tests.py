"""Run auth tests in a NEW isolated MySQL instance; never connect to development.

No existing database is reused or deleted. All artifacts/datadir are preserved.
"""
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


def main():
    os.chdir(ROOT)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    directory = ROOT / ".mysql-rehearsal" / ("auth-api-" + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True, exist_ok=False)
    identity = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r",
                    identity + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    print("ARTIFACTS=" + str(directory), flush=True)
    datadir = directory / "data"
    password = secrets.token_hex(32)
    admin = None
    process = None
    verified = False
    report = {"development_database_accessed": False, "success": False}
    try:
        result = subprocess.run([str(BIN / "mysqld.exe"), "--no-defaults", "--initialize-insecure",
                                 "--basedir=" + str(BIN.parent), "--datadir=" + str(datadir)],
                                capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        (directory / "initialize.txt").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError("New isolated MySQL initialization failed")
        with (directory / "console.txt").open("wb") as console:
            process = subprocess.Popen([
                str(BIN / "mysqld.exe"), "--no-defaults", "--basedir=" + str(BIN.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1",
                "--server-id=9133307", "--mysqlx=OFF", "--skip-log-bin",
                "--log-error=" + str(directory / "server.log"),
                "--pid-file=" + str(directory / "mysqld.pid"),
            ], stdout=console, stderr=console, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Isolated server exited")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=PORT, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        if admin is None:
            raise RuntimeError("Server startup timeout")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            report["server_identity"] = cursor.fetchone()
            if report["server_identity"][:2] != (9133307, PORT) or Path(report["server_identity"][2]).resolve() != datadir.resolve():
                raise RuntimeError("Wrong server identity; no DDL allowed")
            verified = True
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (password,))
            (directory / "root-client.cnf").write_text(
                "[client]\nhost=127.0.0.1\nport=33307\nuser=root\npassword=" + password + "\n", encoding="utf-8")
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            for name in ("test_yippee_migration_fresh", "test_yippee_migration_suite"):
                cursor.execute("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("Refusing existing schema")
                cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                scope = name.replace("_", r"\_")
                cursor.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX,REFERENCES ON `{scope}`.* TO 'yippee_rehearsal'@'localhost'")
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_PORT": str(PORT),
                       "YIPPEE_REHEARSAL_DATABASE": "test_yippee_migration_fresh", "YIPPEE_REHEARSAL_PASSWORD": password}
        for arguments in (["test", "--keepdb", "--noinput", "-v", "2"], ["check", "--database", "default"],
                          ["makemigrations", "--check", "--dry-run"]):
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.user_model_rehearsal"],
                                    env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = (result.stdout + result.stderr).replace(password, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TEST_JWT_REDACTED]", output)
            (directory / (arguments[0] + ".txt")).write_text(output, encoding="utf-8")
            print(output, flush=True)
            if result.returncode:
                raise RuntimeError("Isolated " + arguments[0] + " failed; no further commands")
        report["success"] = True
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
