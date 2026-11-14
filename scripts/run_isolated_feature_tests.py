"""Reuse an existing dedicated MySQL instance; never connect to development."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-dir", required=True)
    args = parser.parse_args()
    os.chdir(ROOT)
    instance = Path(args.instance_dir).resolve()
    allowed_root = (ROOT / ".mysql-rehearsal").resolve()
    if not instance.is_relative_to(allowed_root) or not (instance / "data").is_dir():
        raise RuntimeError("Existing isolated instance path rejected")
    previous = json.loads((instance / "report.json").read_text(encoding="utf-8"))
    if not previous["success"] or not previous["isolated_server_shutdown"]:
        raise RuntimeError("Previous isolated instance did not finish cleanly")
    expected = previous["server_identity"]
    credentials = configparser.ConfigParser(interpolation=None)
    credentials.read(instance / "root-client.cnf", encoding="utf-8")
    client = credentials["client"]
    if (client["host"], client["port"], client["user"]) != ("127.0.0.1", "33307", "root"):
        raise RuntimeError("Isolated credential target rejected")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 33307))
    binaries = Path(os.environ.get("MYSQL_BIN_DIR", str(Path(os.environ["ProgramFiles"]) / "MySQL/MySQL Server 8.0/bin")))
    server_binary = binaries / "mysqld.exe"
    if not server_binary.is_file():
        raise RuntimeError("MySQL server binary not found; set MYSQL_BIN_DIR")
    output_dir = allowed_root / ("child-tests-" + uuid.uuid4().hex[:12])
    output_dir.mkdir(exist_ok=False)
    windows_user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(output_dir), "/inheritance:r", "/grant:r",
                    windows_user + ":(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    print("ARTIFACTS=" + str(output_dir), flush=True)
    process = None
    admin = None
    verified = False
    result_report = {"success": False, "development_database_accessed": False}
    try:
        with (output_dir / "console.txt").open("wb") as console:
            process = subprocess.Popen([str(server_binary), "--no-defaults", "--basedir=" + str(binaries.parent),
                "--datadir=" + str(instance / "data"), "--port=33307", "--bind-address=127.0.0.1", "--server-id=9133307",
                "--mysqlx=OFF", "--skip-log-bin", "--log-error=" + str(output_dir / "server.log"),
                "--pid-file=" + str(output_dir / "server.pid")], stdout=console, stderr=console,
                creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Isolated server exited")
            try:
                admin = MySQLdb.connect(host="127.0.0.1", port=33307, user="root", passwd=client["password"], connect_timeout=2)
                break
            except MySQLdb.OperationalError as error:
                if error.args[0] not in (2002, 2003):
                    raise
                time.sleep(0.5)
        if admin is None:
            raise RuntimeError("Isolated startup timeout")
        with admin.cursor() as cursor:
            cursor.execute("SELECT @@server_id,@@port,@@datadir,@@server_uuid")
            identity = cursor.fetchone()
            if (identity[:2] != (9133307, 33307) or identity[3] != expected[3]
                    or Path(identity[2]).resolve() != (instance / "data").resolve()):
                raise RuntimeError("Server identity mismatch; no test DDL allowed")
        verified = True
        result_report["server_identity"] = identity
        environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "YIPPEE_REHEARSAL_DATABASE": "test_yippee_migration_fresh",
                       "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": client["password"]}
        commands = (["test", "--keepdb", "--noinput", "-v", "2"], ["check", "--database", "default"],
                    ["makemigrations", "--check", "--dry-run"])
        for arguments in commands:
            result = subprocess.run([sys.executable, "manage.py", *arguments, "--settings=config.user_model_rehearsal"],
                                    env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = (result.stdout + result.stderr).replace(client["password"], "[REDACTED]")
            output = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[TEST_JWT_REDACTED]", output)
            (output_dir / (arguments[0] + ".txt")).write_text(output, encoding="utf-8")
            print(output, flush=True)
            if result.returncode:
                raise RuntimeError("Isolated " + arguments[0] + " failed; no further commands")
        result_report["success"] = True
    finally:
        if admin is not None:
            if verified:
                admin.shutdown()
                result_report["isolated_server_shutdown"] = True
            admin.close()
        if process is not None:
            process.wait(timeout=20)
        (output_dir / "report.json").write_text(json.dumps(result_report, indent=2), encoding="utf-8")
        print("Report: " + str(output_dir / "report.json"), flush=True)


if __name__ == "__main__":
    main()
