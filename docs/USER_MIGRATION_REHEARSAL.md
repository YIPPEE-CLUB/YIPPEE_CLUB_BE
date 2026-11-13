# 커스텀 User MySQL 리허설 및 실제 적용 절차

> 실제 적용 최신 상태: [실행 기록](USER_MIGRATION_APPLICATION.md).
> 인덱스 구조 동등성 검증 후 실제 개발 DB의 이관을 완료했다.
> 최종 15개 테이블/21개 migration, Admin FK accounts_user.id이며 기존 원본 행 보존을 확인했다.
> Django check 및 migration 차이 검사도 통과했다. 아래 내용은 이전 리허설 기록이다.

2026-11-13 KST. 실제 `yippee_club_db` 전환은 실행하지 않았다.
아래의 **기존 테스트 DB 관련 사고**를 포함해 읽어야 한다. 격리 리허설 통과를
모든 안전 조건 충족이나 개발 DB 적용 완료로 해석하지 않는다.

## 변경 파일

- `config/user_model_rehearsal.py`, `config/user_model_rehearsal_prepare.py`: 격리 인스턴스 전용 설정과 legacy User 재정의.
- `scripts/rehearsal_target.py`: 수동 생성·권한 도구의 DB명/포트/서버 식별자 공유 및 검증.
- `scripts/create_mysql_rehearsal.py`, `scripts/grant_mysql_rehearsal.py`: DB명을 `test_yippee_migration_legacy`, `test_yippee_migration_fresh`로 통일하고 포트를 33307로 제한.
- `scripts/setup_mysql_dev.py`: 공통 CLI 전송 함수에 명시적 port 인자 추가. 기존 기본값은 3306.
- `scripts/run_mysql_rehearsal.py`: 읽기 전용 백업, 별도 mysqld 초기화/실행, 복원 비교, 단계별 이관, 신규 설치, 기존 사용자 거부 및 전체 테스트 자동화.
- `scripts/rehearsal_checks.py`, `accounts/test_integration.py`: 실제 MySQL을 사용하는 Admin/JWT/이메일 인증 검증.
- `scripts/inspect_user_migration.py`: 실제 적용 단계별 읽기 전용 검증 명령.
- `config/offline_mysql/`, 두 preview 설정, `accounts/tests.py`: 모든 오프라인 연결 차단 및 회귀 검증.
- `scripts/tests/test_grant_mysql_rehearsal.py`, `scripts/tests/test_rehearsal_safety.py`: 변경된 SQL 대상 및 잘못된 서버/DB 거부 검사.
- `.gitignore`: 데이터 디렉터리·백업·자격정보가 있는 `.mysql-rehearsal/` 제외.
- 이 문서와 기존 이관 문서의 최신 결과 연결.

기존 migration 파일은 수정하지 않았으며 실행 전후 SHA256을 비교했다.

## 격리와 재현 방법

로컬 MySQL 8.0.46 실행 파일을 사용했다. 기존 Windows 서비스는 재시작하거나
설정을 변경하지 않았다. 별도 mysqld를 `127.0.0.1:33307`, `server_id=9133307`,
새 UUID와 새 데이터 디렉터리로 실행했다. `--no-defaults`, `--mysqlx=OFF`,
`--skip-log-bin`을 사용하며 서버의 실제 datadir/UUID/port/server_id를 확인한 후에만
리허설 DDL을 허용한다. 실행 완료 후 해당 인스턴스만 정상 종료하며 파일/DB는 삭제하지 않는다.

리허설 스키마는 네 개다. 실행마다 새 인스턴스를 사용하므로 기존 스키마를 재사용하지 않는다.

| DB | 용도 |
|---|---|
| `test_yippee_migration_legacy` | 개발 DB 백업 복원 및 단계별 User 전환 |
| `test_yippee_migration_fresh` | custom User로 신규 설치 |
| `test_yippee_migration_reject` | 기존 사용자가 있을 때 bridge 거부 |
| `test_yippee_migration_suite` | Django 전체 테스트 전용 |

전용 계정에는 해당 네 스키마의 SELECT/INSERT/UPDATE/DELETE/CREATE/ALTER/INDEX/REFERENCES만
부여했다. DROP 권한은 부여하지 않는다. 테스트는 `--keepdb`로 실행한다.
준비 설정/bridge의 허용 범위를 넓히거나 기존 migration을 변경하지 않았다.
리허설 설정은 `.env`의 개발 DB 자격정보를 상속하지 않고 별도의 명시적 환경변수를 요구한다.

```powershell
# 개발 DB에는 읽기 전용 백업/조회만 수행. 별도 로컬 인스턴스에서만 복원/이관.
.\.venv\Scripts\python.exe scripts/run_mysql_rehearsal.py
```

수동 생성/권한 스크립트는 이미 실행된 runner에 이어서 실행하는 도구가 아니다.
별도로 준비된 동일 식별자의 격리 인스턴스에서만 사용하는 대안이며, 3306 서버에는 적용되지 않는다.

## 백업과 복원 검증

개발 DB의 10개 테이블을 `mysqldump`로 백업했다. 소스 쪽 옵션은
`--single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF`이고,
복원용 옵션은 `--skip-add-drop-table --skip-add-locks --skip-disable-keys --hex-blob`이다.
`--databases`를 사용하지 않아 개발 DB 이름으로 생성/전환하는 SQL을 만들지 않는다.
조회 가능한 저장 프로시저/이벤트/트리거/뷰가 없다는 사전 조건도 검사했다.
이 조건이 달라지면 백업 범위를 재검토하고 중단한다.

개발 DB 백업을 legacy/reject 두 격리 스키마에 복원했다. 모든 테이블의 전체 행 해시,
건수, 컬럼 타입/기본값/문자셋/collation, 인덱스·제약조건·FK, migration 이력이 일치했다.
MySQL이 복원 후 중복 출력하는 `CHARACTER SET` 표기는 정규화하지만 실제 컬럼 메타데이터는
별도로 정확히 비교한다. 내용이 다른 스키마를 허용하는 예외는 추가하지 않았다.

백업·보고서·로그·데이터 디렉터리·자격정보는 Git 제외 디렉터리에 보존한다.
Windows ACL은 실행 사용자와 SYSTEM만 허용한다. 파일 경로/크기/SHA256은 report.json에 기록한다.
최종 증거 디렉터리: `.mysql-rehearsal/20261113-175143-99b18dfc/`.
최종 백업 크기는 12,215 bytes이며 SHA256은
`3f78b322263caf1dcbc028470e4bd34641c53e841a0bbee1d46f36cadb56e361`이다.
원본 백업은 개발 DB에 복원하지 않았다.

## 이관 결과

| 단계 | 테이블 수 | migration 수 | Admin user FK |
|---|---:|---:|---|
| 복원 직후 | 10 | 18 | `auth_user.id` |
| legacy 설정에서 accounts 0001 | 13 | 19 | `auth_user.id` |
| legacy 설정에서 accounts 0002 | 13 | 20 | `accounts_user.id` |
| custom User 전환 후 전체 migrate | 15 | 21 | `accounts_user.id` |
| custom User로 신규 설치 | 12 | 21 | `accounts_user.id` |

기존 전환 경로는 `auth_user` 및 기존 사용자 M2M 테이블을 그대로 보존한다.
신규 설치에는 이전 User 테이블 3개가 없으므로 최종 테이블 수가 다르다.
legacy 경로의 permission은 24→28→36, ContentType은 6→7→9로 추가되며,
기존 모든 행의 해시가 최종 데이터 안에 그대로 존재함을 검증한다.
Admin user_id와 accounts_user.id는 모두 signed INT다.

legacy 설정으로 0001/0002를 적용한 후 custom User 설정으로 전체 migrate,
`check --database default`, `makemigrations --check --dry-run`이 통과했다.
별도의 reject 복원 DB에만 테스트 사용자를 추가했을 때 0002는 예상한 오류로 중단했으며,
중단 전후 스키마·행·FK·migration 이력이 동일했다. 우회 적용하지 않았다.

Admin 이메일 로그인/사용자 생성/비밀번호 변경/로그 기록, JWT 실제 발급·서명 검증·refresh·
ORM 사용자 조회·비활성 사용자 거부, 기존 이메일 식별자 조회·가입 중복 거부·인증 메일 생성·
코드 확인·중복 확인 거부를 두 이관 경로에서 실제 MySQL로 검증했다.
검증 데이터는 트랜잭션 rollback으로 남기지 않는다. 메일은 locmem backend를 사용했으므로
실제 SMTP 전송 검증은 아니다. 회원가입/로그인 HTTP API는 아직 구현 대상인 상태다.

최종 Django 전체 테스트는 44개 중 42개 통과, 오프라인 전용 검사 2개 skip이다.
실제 이관 두 경로의 smoke 검사와 MySQL 데이터 보존 검사는 별도로 통과했다.
전체 실행 로그와 최종 백업 해시는 같은 디렉터리의 로그/report.json을 따른다.
권한·안전 스크립트 테스트는 19개 통과했다. 두 오프라인 설정은 각각 35개 중 34개 통과,
격리 DB 통합 테스트 1개 skip이다. skip된 TestCase는 `databases=set()`으로 DB 준비에 참여하지 않는다.

## 실패와 수정

1. 첫 복원 시 덤프가 복원용 `LOCK TABLES`를 포함해 최소 권한 계정으로 복원이 실패했다.
   빈 대상 스키마에 맞는 `--skip-add-locks --skip-disable-keys`를 추가했다. 권한을 확대하지 않았다.
2. 복원 후 중복 `CHARACTER SET` 출력 때문에 문자열 스키마 비교가 실패했다.
   실제 컬럼 메타데이터를 비교하고 해당 출력 차이만 정규화하도록 수정했다.
3. 각 실패 시 해당 인스턴스를 종료하고 증거를 남겼다. 실패 DB를 수정해 이어서 진행하거나
   migration을 fake 처리하지 않고, 수정 후 새로운 격리 인스턴스에서 처음부터 검증했다.

## 기존 테스트 DB 관련 사고 및 한계

추가한 통합 TestCase를 오프라인 테스트 검색에 포함했을 때, skip 표지만으로는 Django의
DB 준비를 막지 못했다. 기존 SQL wrapper는 default 연결만 보호했고 테스트 생성용
`__no_db__` 연결을 보호하지 못했다. `--noinput` 실행이 기존 `test_yippee_club_db`에
CREATE/DROP/재생성을 시도했고 오류로 종료했다. 이후 읽기 전용 조회에서 해당 스키마의
테이블이 없음을 확인했다. 작업 전 해당 테스트 DB의 백업/스냅샷을 수집하지 않았으므로
이전 데이터의 보존이나 손실 범위를 입증할 수 없다. 기존 테스트 DB를 자동 재생성하거나
데이터를 복구한 것으로 보고하지 않는다. 복구에는 작업 전 별도 백업 유무 확인이 필요하다.

이는 작업 중 발생한 안전 조건 위반이다. 개발 DB 백업이나 격리 리허설 성공으로 상쇄되지 않는다.
이후 두 오프라인 설정에 `config.offline_mysql` backend를 추가해 default/`__no_db__`/
새 스레드의 **연결 생성 자체를 거부**하고, 통합 TestCase가 오프라인 DB 준비에 참여하지
않도록 고쳤다. 회귀 테스트에서 MySQL connect가 호출되지 않음을 확인했다.
해당 기존 테스트 DB에는 추가 변경을 하지 않았다.

`yippee_club_db`는 전후 전체 행 해시/컬럼/스키마/FK/이력이 일치하고,
최종 읽기 전용 검사에서 10개 테이블/18개 migration 상태다. `team3_db`에는 접근하지 않았다.

## 실제 개발 DB 적용 명령 — 승인 전 실행 금지

작업 디렉터리는 저장소 루트다. 서버 식별자는 조회한 개발 DB UUID
`5491c807-5688-11f1-a0bf-c86e08e6aa63`, 포트 3306이다. 환경변수와 `.env`가 의도한
host/DB/계정인지 먼저 확인한다. 코드 기본 User 설정은 이미 custom User이므로,
모든 서비스/worker의 쓰기를 중단하고 유지보수 상태에서 아래 순서로 진행해야 한다.

1. 승인 직전 읽기 전용 initial 검사. 현재 상태와 달라지면 중단한다.
2. 쓰기/DDL 중단 상태에서 새 백업을 만들고 독립 인스턴스로 복원 검증한다.
   이번 백업만으로 미래 시점의 상태를 보장하지 않는다. 위 runner가 백업·복원 전체 명령이다.
3. 승인 후 아래 명령을 **한 줄씩**, 종료 코드 0과 계획/검증 내용을 확인하며 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts/inspect_user_migration.py --stage initial

.\.venv\Scripts\python.exe manage.py migrate accounts 0001 --settings=config.user_model_prepare --plan
# 계획: accounts.0001_initial 하나. 다른 항목이면 중단.
.\.venv\Scripts\python.exe manage.py migrate accounts 0001 --settings=config.user_model_prepare --noinput
.\.venv\Scripts\python.exe scripts/inspect_user_migration.py --stage prepared

.\.venv\Scripts\python.exe manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --plan
# 계획: accounts.0002_bridge_admin_user 하나.
.\.venv\Scripts\python.exe manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --noinput
.\.venv\Scripts\python.exe scripts/inspect_user_migration.py --stage bridged

# 여기서만 custom User 기본 설정을 서비스에 사용할 준비가 됨. 아직 쓰기는 재개하지 않음.
.\.venv\Scripts\python.exe manage.py check --settings=config.settings --database default
.\.venv\Scripts\python.exe manage.py showmigrations --settings=config.settings
.\.venv\Scripts\python.exe manage.py migrate --settings=config.settings --plan
# 계획: email_verification.0001_initial 하나. accounts/admin 역적용 등이 있으면 중단.
.\.venv\Scripts\python.exe manage.py migrate --settings=config.settings --noinput
.\.venv\Scripts\python.exe scripts/inspect_user_migration.py --stage final
.\.venv\Scripts\python.exe manage.py check --settings=config.settings --database default
.\.venv\Scripts\python.exe manage.py makemigrations --settings=config.settings --check --dry-run
```

읽기 전용 stage 검사기는 DB명/실제 포트/테이블 수/migration 수와 accounts 이력,
빈 사용자·로그·M2M, legacy User 그룹 권한, 실제 Admin FK 및 키 타입을 검증한다.
적용 직후 final 검사는 서비스 쓰기 재개 전에 실행한다.
서비스 재개 전 백업과 현재 스키마/데이터의 차이도 검토한다.

실제 DB에서 테스트를 실행하지 않는다. 전체 테스트는 별도 리허설 인스턴스의 전용 suite DB에서만
수행한다. 개발 DB에서 검증 사용자를 생성하는 작업은 이 승인 범위에 포함하지 않는다.

## 실제 적용 위험과 중단 조건

- 사용자가 한 명이라도 생기거나 기존 Admin 로그/M2M/관련 그룹 권한이 생기면 빈 DB bridge 적용 금지.
- MySQL DDL은 전체 과정이 트랜잭션으로 rollback되지 않는다. 0002는 역적용 불가다.
  실패 시 쓰기를 재개하지 않고 현재 물리 FK와 migration 기록을 읽기 전용으로 조사한다.
  설정만 되돌리거나 fake/역적용으로 우회하지 않는다. 복구는 별도 승인된 계획이 필요하다.
- 0001 전에 custom User로 migrate하면 기존 Admin 이력 의존성이 깨진다.
- 기본 설정과 legacy 설정을 사용하는 프로세스를 동시에 서비스하지 않는다.
- 기존 테스트 DB 데이터 보존을 보장할 수 없는 사고는 별도로 해결해야 한다. 이번 백업은 개발 DB 백업이다.
- DB 구조/사용자 데이터/저장 객체/외부 FK가 리허설 시점과 달라지면 계획을 재검토한다.
- 생성한 백업/자격정보 파일은 민감정보다. ACL을 유지하고 저장소에 추가하지 않는다.
