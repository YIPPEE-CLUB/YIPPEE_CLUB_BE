"""Run locally in an elevated Windows PowerShell after approving the setup SQL.

Root authentication is handled by mysql.exe's own console password prompt.
Secrets are never placed in command arguments or SQL files.
"""
from pathlib import Path
import os
import re
import secrets
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
MYSQL = Path(r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe")
DATABASE = "yippee_club_db"
USER = "yippee_app"


def admin_sql(sql, *, port=3306):
    # mysql.exe reads its password directly from the Windows console, even
    # though SQL input and command output use pipes. Batch mode avoids history.
    child_env = os.environ.copy()
    child_env.pop("MYSQL_PWD", None)
    process = subprocess.Popen(
        [str(MYSQL), "--no-defaults", "--protocol=TCP", "--host=127.0.0.1",
         f"--port={int(port)}", "--user=root", "--password", "--batch",
         "--skip-column-names", "--raw", "--default-character-set=utf8mb4"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=child_env,
    )
    errors = bytearray()

    def read_errors():
        while True:
            value = process.stderr.read(1)
            if not value:
                break
            errors.extend(value)
            if errors.endswith(b"Enter password:"):
                print("MySQL root 비밀번호(로컬 CLI 입력): ", end="", flush=True)

    reader = threading.Thread(target=read_errors, daemon=True)
    reader.start()
    try:
        process.stdin.write(sql.encode("utf-8"))
        process.stdin.close()
        output = process.stdout.read()
        process.wait()
        reader.join()
    except BaseException:
        process.terminate()
        process.wait()
        reader.join()
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    print()
    if process.returncode:
        # Never echo raw SQL errors: they can contain password-bearing SQL.
        codes = re.findall(rb"ERROR\s+(\d+)", bytes(errors))
        safe_codes = ", ".join(code.decode("ascii") for code in codes) or "unknown"
        raise RuntimeError(f"MySQL 작업 실패. 오류 코드: {safe_codes}. 중단합니다.")
    return output.decode("utf-8").strip()


def write_credentials(password):
    path = ROOT / ".env"
    content = path.read_text(encoding="utf-8")
    updates = {
        "MYSQL_DATABASE": DATABASE,
        "MYSQL_USER": USER,
        "MYSQL_PASSWORD": password,
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
    }
    lines = []
    seen = set()
    for line in content.splitlines():
        match = re.match(r"^\s*(?:export\s+)?(MYSQL_\w+)\s*=", line)
        name = match.group(1) if match else None
        if name in updates:
            if name not in seen:
                lines.append(f"{name}={updates[name]}")
                seen.add(name)
        else:
            lines.append(line)
    lines.extend(f"{name}={value}" for name, value in updates.items() if name not in seen)
    # Only the already-ignored .env contains the generated credential.
    # Write before DDL so it remains recoverable if CREATE succeeds but GRANT fails.
    with path.open("w", encoding="utf-8", newline="\n") as target:
        target.write("\n".join(lines) + "\n")


def main():
    os.chdir(ROOT)
    if os.name != "nt" or not sys.stdin.isatty():
        raise RuntimeError("Run in a local Windows PowerShell console, without redirection.")
    if not MYSQL.is_file() or not (ROOT / ".env").is_file():
        raise RuntimeError("mysql.exe or .env is missing.")
    subprocess.run(["git", "check-ignore", "--quiet", ".env"], check=True)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"], capture_output=True
    )
    if tracked.returncode == 0:
        raise RuntimeError(".env is tracked by Git. Stopped.")

    print("Read-only preflight. Enter the root password in the local CLI prompt.")
    result = admin_sql(
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_app';\n"
        "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA "
        "WHERE SCHEMA_NAME='yippee_club_db';\n"
    ).splitlines()
    if result != ["0", "utf8mb4"]:
        raise RuntimeError(
            "Preflight stopped: an application account exists, or the target DB "
            "is missing/not utf8mb4. No credentials or database objects were changed."
        )

    password = secrets.token_hex(32)
    write_credentials(password)
    print("Local .env updated. Authenticate again to apply the approved CREATE/GRANT.")
    admin_sql(
        f"CREATE USER '{USER}'@'localhost' IDENTIFIED BY '{password}';\n"
        f"GRANT ALL PRIVILEGES ON `{DATABASE}`.* TO '{USER}'@'localhost';\n"
    )
    print("Application user created; privileges granted only on yippee_club_db.")

    # Eliminate inherited settings that could override the intended .env target.
    for name in ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_HOST",
                 "MYSQL_PORT", "DJANGO_SETTINGS_MODULE"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection

    target = settings.DATABASES["default"]
    if (target["ENGINE"] != "django.db.backends.mysql" or
            target["NAME"] != DATABASE or target["USER"] != USER or
            target["HOST"] != "127.0.0.1" or int(target["PORT"]) != 3306):
        raise RuntimeError("Unexpected Django database target. Stopped.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT DATABASE(), CURRENT_USER(), 1")
        row = cursor.fetchone()
    if row != (DATABASE, f"{USER}@localhost", 1):
        raise RuntimeError("Database query identity check failed. Stopped.")
    connection.close()
    print("Django connection and SELECT query: OK (yippee_club_db).")

    for arguments in (["migrate", "--noinput"], ["check"], ["test"]):
        result = subprocess.run(
            [sys.executable, "manage.py", *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        output = result.stdout + result.stderr
        for secret in (password, settings.SECRET_KEY):
            if secret:
                output = output.replace(secret, "[REDACTED]")
        print(output, end="")
        if result.returncode:
            raise RuntimeError(f"manage.py {arguments[0]} failed. Stopped.")
    print("SETUP COMPLETE. No team3_db objects were queried or changed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. No automatic retry. Check local state before continuing.")
        sys.exit(1)
    except Exception as error:
        # Report only known safe messages or error types, never arbitrary secrets.
        if isinstance(error, RuntimeError):
            print(f"STOPPED: {error}")
        else:
            print(f"STOPPED: {type(error).__name__}; sensitive details suppressed.")
        print("If .env was updated, keep it: it contains the generated recovery credential.")
        sys.exit(1)
