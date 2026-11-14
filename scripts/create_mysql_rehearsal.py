"""승인된 리허설 DB 두 개와 계정만 생성한다. 권한 부여나 이관은 하지 않는다."""
import ctypes
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

if __package__:
    from .rehearsal_target import DATABASES, PORT, admin_sql
else:
    from rehearsal_target import DATABASES, PORT, admin_sql
ACCOUNT = "yippee_rehearsal"


def protected_directory():
    directory = Path(os.environ["LOCALAPPDATA"]) / ("YippeeRehearsal_" + uuid.uuid4().hex)
    directory.mkdir(exist_ok=False)
    result = subprocess.run(
        ["icacls.exe", str(directory), "/inheritance:r", "/grant:r",
         "*S-1-5-32-544:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("임시 폴더 접근 제한 실패. 비밀번호를 생성하지 않고 중단합니다.")
    # 실제 ACL을 검증하기 전에는 비밀 파일을 쓰지 않는다.
    command = r"""
$ErrorActionPreference='Stop'
$acl=Get-Acl -LiteralPath $env:YIPPEE_REHEARSAL_SECRET_DIR
$rules=@($acl.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object {
    @{Sid=$_.IdentityReference.Value; Rights=[int]$_.FileSystemRights; Allow=[int]$_.AccessControlType; Inherited=$_.IsInherited; Inheritance=[int]$_.InheritanceFlags}
})
@{Protected=$acl.AreAccessRulesProtected; Rules=$rules} | ConvertTo-Json -Depth 4
"""
    checked = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "YIPPEE_REHEARSAL_SECRET_DIR": str(directory)},
        capture_output=True, text=True,
    )
    if checked.returncode:
        raise RuntimeError("폴더 ACL 확인 실패. 중단합니다.")
    acl = json.loads(checked.stdout)
    rules = acl["Rules"]
    if not (acl["Protected"] and len(rules) == 2 and
            {rule["Sid"] for rule in rules} == {"S-1-5-32-544", "S-1-5-18"} and
            all(rule["Rights"] == 2032127 and rule["Allow"] == 0 and
                not rule["Inherited"] and rule["Inheritance"] == 3 for rule in rules)):
        raise RuntimeError("폴더 ACL이 예상과 다릅니다. 중단합니다.")
    return directory


def main():
    if os.name != "nt" or not sys.stdin.isatty():
        raise RuntimeError("입력 리디렉션 없이 로컬 관리자 PowerShell에서 실행하세요.")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("관리자 PowerShell이 필요합니다.")
    print("root로 신규 DB 두 개와 계정의 부재를 먼저 확인합니다.")
    preflight = admin_sql(
        "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='test_yippee_migration_legacy';\n"
        "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='test_yippee_migration_fresh';\n"
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_rehearsal';\n"
    ).splitlines()
    if preflight != ["0", "0", "0"]:
        raise RuntimeError("대상 DB 또는 계정이 이미 존재하거나 조회 결과가 다릅니다. 변경 없이 중단합니다.")

    directory = protected_directory()
    password = secrets.token_hex(32)
    credential = directory / "rehearsal-client.cnf"
    with credential.open("x", encoding="utf-8", newline="\n") as target:
        target.write(
            f"[client]\nhost=127.0.0.1\nport={PORT}\nuser=yippee_rehearsal\n"
            f"password={password}\ndefault-character-set=utf8mb4\n"
        )
        target.flush()
        os.fsync(target.fileno())
    print("비밀번호를 관리자·SYSTEM 전용 폴더에 저장했습니다. 값은 출력하지 않습니다.")
    print(f"자격정보 파일 경로: {credential}")
    print("생성을 위해 root로 다시 인증합니다. 권한 부여는 하지 않습니다.")
    # IF NOT EXISTS를 쓰지 않는다. 사전 확인 이후 다른 작업이 생성했어도
    # 오류로 중단하며, 덮어쓰기·비밀번호 변경·자동 재시도는 하지 않는다.
    result = admin_sql(
        "CREATE DATABASE `test_yippee_migration_legacy` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        "CREATE DATABASE `test_yippee_migration_fresh` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
        f"CREATE USER 'yippee_rehearsal'@'localhost' IDENTIFIED BY '{password}';\n"
        "SELECT SCHEMA_NAME,DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA "
        "WHERE SCHEMA_NAME IN ('test_yippee_migration_legacy','test_yippee_migration_fresh') ORDER BY SCHEMA_NAME;\n"
        "SELECT COUNT(*) FROM mysql.user WHERE User='yippee_rehearsal' AND Host='localhost';\n"
    ).splitlines()
    expected = [f"{name}\tutf8mb4" for name in sorted(DATABASES)] + ["1"]
    if result != expected:
        raise RuntimeError("생성 후 확인 결과가 예상과 다릅니다. 추가 작업 없이 중단합니다.")
    for name in DATABASES:
        print(f"DB 생성 확인: {name} / utf8mb4")
    print("계정 생성 확인: yippee_rehearsal@localhost")
    print("완료: 권한 부여·백업·복원·마이그레이션은 실행하지 않았습니다.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n사용자 중단. 자동 재시도나 삭제를 하지 않습니다.")
        sys.exit(1)
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else "처리 중 오류가 발생했습니다. 비밀정보 보호를 위해 상세 출력은 생략합니다.")
        print("부분 생성 가능성이 있으므로 자동 재실행하지 마세요. 표시된 자격정보 파일은 보존하세요.")
        sys.exit(1)
