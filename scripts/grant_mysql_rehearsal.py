"""승인된 리허설 권한만 부여하고 두 DB의 실제 접속을 확인한다."""
import configparser
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys

if __package__:
    from .rehearsal_target import DATABASES, PORT, admin_sql
else:
    from rehearsal_target import DATABASES, PORT, admin_sql
ACCOUNT = "yippee_rehearsal"
PRIVILEGE_ORDER = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "INDEX", "REFERENCES")
PRIVILEGES = frozenset(PRIVILEGE_ORDER)


def database_scope(database):
    """partial_revokes=0 전용: 식별자 안의 밑줄마다 역슬래시 한 개."""
    if database not in DATABASES:
        raise ValueError("승인되지 않은 리허설 DB 이름입니다.")
    return database.replace("_", r"\_")


SCOPES = frozenset(database_scope(name) for name in DATABASES)
GRANT_PATTERN = re.compile(
    r"GRANT (?P<privileges>[A-Z]+(?: [A-Z]+)*(?:,\s*[A-Z]+(?: [A-Z]+)*)*) "
    r"ON (?P<scope>\*\.\*|`[^`]+`\.\*) TO `yippee_rehearsal`@`localhost`"
)


def build_grant_sql():
    # 백틱은 DB 패턴만 감싸고, .*는 식별자 바깥에 둔다.
    # SQL은 CLI 인수가 아닌 stdin으로 전달되므로 셸 이스케이프는 더하지 않는다.
    privileges = ", ".join(PRIVILEGE_ORDER)
    return "".join(
        f"GRANT {privileges} ON `{database_scope(name)}`.* "
        f"TO '{ACCOUNT}'@'localhost';\n" for name in DATABASES
    )


def validate_grants(lines, complete=False):
    if not lines:
        raise RuntimeError("SHOW GRANTS 결과가 비어 있습니다. 중단합니다.")
    actual = {}
    for line in lines:
        # MySQLdb 문자열과 mysql --batch --raw 출력을 그대로 해석한다.
        # Python repr/JSON 표시의 이중 이스케이프는 실제 서버 값이 아니다.
        # 역슬래시를 줄이는 보정을 하면 다른 DB 패턴을 승인할 수 있으므로 금지한다.
        match = GRANT_PATTERN.fullmatch(line.strip())
        if not match:
            raise RuntimeError("예상하지 않은 전역·역할·객체 권한이 있습니다. 변경 없이 중단합니다.")
        values = [value.strip() for value in match["privileges"].split(",")]
        permissions = set(values)
        if len(permissions) != len(values):
            raise RuntimeError("중복된 권한 표기가 있습니다. 중단합니다.")
        if match["scope"] == "*.*" and permissions == {"USAGE"}:
            continue
        scope = match["scope"]
        if scope == "*.*" or scope[1:-3] not in SCOPES or not permissions <= PRIVILEGES:
            raise RuntimeError("승인 범위를 벗어난 기존 권한이 있습니다. 자동 회수하지 않고 중단합니다.")
        actual.setdefault(scope[1:-3], set()).update(permissions)
    if complete and (set(actual) != SCOPES or any(value != PRIVILEGES for value in actual.values())):
        raise RuntimeError("권한 적용 후 확인 결과가 승인된 범위와 다릅니다. 추가 작업을 중단합니다.")


def read_credential():
    path = Path(input("생성 시 보관한 rehearsal-client.cnf의 전체 경로: ").strip().strip('"')).resolve(strict=True)
    if not path.is_file():
        raise RuntimeError("자격정보 파일이 없습니다.")
    command = r"""
$ErrorActionPreference='Stop'
$acl=Get-Acl -LiteralPath $env:YIPPEE_REHEARSAL_CREDENTIAL
@($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
    @{Sid=$_.IdentityReference.Value; Allow=[int]$_.AccessControlType; Rights=[int]$_.FileSystemRights}
}) | ConvertTo-Json
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "YIPPEE_REHEARSAL_CREDENTIAL": str(path)},
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError("자격정보 파일의 접근 권한을 확인할 수 없습니다.")
    rules = json.loads(result.stdout)
    if not (isinstance(rules, list) and len(rules) == 2 and
            {rule["Sid"] for rule in rules} == {"S-1-5-32-544", "S-1-5-18"} and
            all(rule["Allow"] == 0 and rule["Rights"] == 2032127 for rule in rules)):
        raise RuntimeError("자격정보 파일이 관리자·SYSTEM 전용이 아닙니다. 읽지 않고 중단합니다.")
    parser = configparser.ConfigParser(interpolation=None)
    with path.open(encoding="utf-8") as source:
        parser.read_file(source)
    client = parser["client"]
    if (client.get("user") != ACCOUNT or client.get("host") != "127.0.0.1" or
            client.get("port") != str(PORT) or not client.get("password")):
        raise RuntimeError("리허설 전용 자격정보의 설정이 예상과 다릅니다.")
    return client["password"]


def main():
    if os.name != "nt" or not sys.stdin.isatty() or not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("입력 리디렉션 없이 로컬 관리자 PowerShell에서 실행하세요.")
    # 비밀 파일을 읽고 유효성을 확인하되 비밀번호는 출력·변경하지 않는다.
    password = read_credential()
    print("root로 DB·계정·문자셋·빈 테이블·기존 권한을 확인합니다.")
    lines = admin_sql(
        "SELECT @@GLOBAL.partial_revokes;\n"
        "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='test_yippee_migration_legacy';\n"
        "SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='test_yippee_migration_fresh';\n"
        "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('test_yippee_migration_legacy','test_yippee_migration_fresh');\n"
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_rehearsal';\n"
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_rehearsal' AND Host='localhost' AND account_locked='N';\n"
        "SHOW GRANTS FOR 'yippee_rehearsal'@'localhost';\n"
    ).splitlines()
    if lines[:6] != ["0", "utf8mb4", "utf8mb4", "0", "1", "1"] or not lines[6:]:
        raise RuntimeError("DB·계정·문자셋·빈 테이블·partial_revokes 사전 조건이 다릅니다. 변경 없이 중단합니다.")
    validate_grants(lines[6:])
    print("사전 조건 확인 성공. 기존 SHOW GRANTS:")
    for line in lines[6:]:
        print(line)

    # 비밀번호 오류를 GRANT 전에 확인한다. DB 없는 로그인은 USAGE로 가능하다.
    import MySQLdb
    login = MySQLdb.connect(host="127.0.0.1", port=PORT, user=ACCOUNT, passwd=password,
                           charset="utf8mb4", connect_timeout=5)
    try:
        with login.cursor() as cursor:
            cursor.execute("SELECT CURRENT_USER()")
            if cursor.fetchone()[0] != ACCOUNT + "@localhost":
                raise RuntimeError("전용 계정 인증 결과가 예상과 다릅니다.")
    finally:
        login.close()

    print("승인된 GRANT 적용을 위해 root로 다시 인증합니다.")
    grants = admin_sql(
        build_grant_sql() + "SHOW GRANTS FOR 'yippee_rehearsal'@'localhost';\n"
    ).splitlines()
    validate_grants(grants, complete=True)
    print("권한 적용 후 SHOW GRANTS 검증 성공:")
    for line in grants:
        print(line)
    for database in DATABASES:
        db = MySQLdb.connect(host="127.0.0.1", port=PORT, user=ACCOUNT, passwd=password,
                             db=database, charset="utf8mb4", connect_timeout=5)
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT DATABASE(), CURRENT_USER(), 1")
                if cursor.fetchone() != (database, ACCOUNT + "@localhost", 1):
                    raise RuntimeError("실제 접속 대상 또는 쿼리 결과가 예상과 다릅니다.")
                cursor.execute("SHOW FULL TABLES")
                if cursor.fetchall():
                    raise RuntimeError("리허설 DB에 테이블이 생겼습니다. 추가 작업 없이 중단합니다.")
                cursor.execute("SHOW GRANTS FOR CURRENT_USER")
                validate_grants([row[0] for row in cursor.fetchall()], complete=True)
            print(f"실제 접속·쿼리·빈 테이블 확인 성공: {database}")
        finally:
            db.close()
    print("완료: 두 DB의 승인된 권한만 확인했습니다. 비밀번호 변경·백업·복원·마이그레이션은 하지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자 중단. 자동 재실행하지 않습니다.")
        sys.exit(1)
    except Exception as error:
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print("처리 중 오류가 발생했습니다. 비밀번호 보호를 위해 상세 출력은 생략합니다.")
        print("일부 권한이 적용됐을 수 있습니다. 자동 재시도·회수·삭제 없이 결과를 보고하세요.")
        sys.exit(1)
