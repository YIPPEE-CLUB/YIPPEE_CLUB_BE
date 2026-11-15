"""Run the suite on a NEW isolated MySQL datadir; never reuse a test DB.

Uses the existing rehearsal SQL guard and fixed local server identity. No
development connection, source backup, existing datadir or credentials needed.
Artifacts are retained under the ignored .mysql-rehearsal directory.
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


def main():
    binaries = Path(os.environ.get("MYSQL_BIN_DIR", r"C:\Program Files\MySQL\MySQL Server 8.0\bin"))
    binary = binaries / "mysqld.exe"
    if not binary.is_file():
        raise RuntimeError("MySQL server binary missing; set MYSQL_BIN_DIR")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    run = ROOT / ".mysql-rehearsal" / ("cart-tests-" + uuid.uuid4().hex[:12])
    run.mkdir(parents=True, exist_ok=False)
    identity = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r",
                    identity + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    print("ARTIFACTS=" + str(run), flush=True)
    datadir = run / "data"
    report = {"success": False, "development_database_accessed": False,
              "existing_test_database_reused": False}
    process = admin = None
    verified = False
    password = secrets.token_hex(32)
    hidden = subprocess.CREATE_NO_WINDOW
    try:
        initialized = subprocess.run([str(binary), "--no-defaults", "--initialize-insecure",
            "--basedir=" + str(binaries.parent), "--datadir=" + str(datadir)],
            capture_output=True, creationflags=hidden)
        (run / "initialize.txt").write_bytes(initialized.stdout + initialized.stderr)
        if initialized.returncode:
            raise RuntimeError("Fresh MySQL initialization failed; see initialize.txt")
        with (run / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(binary), "--no-defaults", "--basedir=" + str(binaries.parent),
                "--datadir=" + str(datadir), "--port=33307", "--bind-address=127.0.0.1",
                "--server-id=9133307", "--mysqlx=OFF", "--skip-log-bin",
                "--log-error=" + str(run / "server.log"), "--pid-file=" + str(run / "server.pid")],
                stdout=console, stderr=console, creationflags=hidden)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Fresh MySQL exited; see server.log")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd="", connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        if admin is None:
            raise RuntimeError("Fresh MySQL startup timeout")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            server_identity = cursor.fetchone()
            if (server_identity[:2] != (9133307, 33307)
                    or Path(server_identity[2]).resolve() != datadir.resolve()):
                raise RuntimeError("Fresh server identity rejected; no DDL allowed")
            verified = True
            report["server_identity"] = server_identity
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY %s", (password,))
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE 'test_yippee%'")
            if cursor.fetchall():
                raise RuntimeError("Fresh instance unexpectedly contains test schemas")
            cursor.execute("CREATE DATABASE test_yippee_migration_fresh CHARACTER SET utf8mb4")
            # These two exact scopes exist only inside the verified new instance.
            for scope in (r"test\_yippee\_migration\_fresh", r"test\_yippee\_migration\_suite"):
                cursor.execute("GRANT ALL PRIVILEGES ON `" + scope + "`.* TO 'yippee_rehearsal'@'localhost'")
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8",
            "YIPPEE_REHEARSAL_DATABASE": "test_yippee_migration_fresh",
            "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": password}
        commands = (["test", "--noinput", "-v", "2"], ["check", "--database", "default"],
                    ["makemigrations", "--check", "--dry-run"])
        report["commands"] = []
        for arguments in commands:
            result = subprocess.run([sys.executable, "manage.py", *arguments,
                "--settings=config.user_model_rehearsal"], cwd=ROOT, env=environment,
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = (result.stdout + result.stderr).replace(password, "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TEST_JWT_REDACTED]", output)
            (run / (arguments[0] + ".txt")).write_text(output, encoding="utf-8")
            print(output, flush=True)
            report["commands"].append({"arguments": arguments, "exit_code": result.returncode})
            if result.returncode:
                raise RuntimeError("Isolated " + arguments[0] + " failed")
        report["success"] = True
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        (run / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Report: " + str(run / "report.json"), flush=True)


if __name__ == "__main__":
    main()
