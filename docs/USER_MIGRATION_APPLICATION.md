# 실제 개발 DB User 이관 실행 기록 — 완료

> 후속 인증 API용 accounts.0003도 개발 DB에 적용 완료됐다. 현재 16개 테이블/22개 migration이다.
> 최신 결과는 [인증 API 개발 DB 적용 기록](AUTH_API_DEPLOYMENT.md)을 따른다.
> 아래 15개 테이블/21개 migration 완료 기록은 기존 User 전환 단계의 결과다.

2026-11-13 KST. 사용자가 쓰기 클라이언트·자동 실행의 중지 및 이관 종료까지 유지 가능함을
명시적으로 확인한 뒤 승인된 절차를 실행했다. **최종 이관 완료: 15개 테이블, 21개 migration,
Admin FK accounts_user.id.** 인덱스 구조 동등성 확인 후 남은 이메일 인증 migration을 적용했다.
회원가입·로그인 API 개발을 시작할 수 있는 DB 상태다. 서비스 프로세스를 자동 재시작하지는 않았다.
아래 0002 중단 내용은 당시의 기록이며, 재개·최종 결과는 문서 하단을 따른다.

## 실제 대상과 백업

- DB: `yippee_club_db`, 포트 3306, 계정 `yippee_app@localhost`.
- UUID: `5491c807-5688-11f1-a0bf-c86e08e6aa63`.
- 초기 상태: 10개 테이블, 18개 migration. 사용자/Admin 로그/사용자 M2M/관련 그룹 권한 모두 0건.
- 새 백업 및 독립 인스턴스 복원 검증을 기존 `scripts/run_mysql_rehearsal.py`로 수행했다.
  독립 서버의 복원·리허설은 성공했으며 정상 종료했다. 원본 DB는 이 단계에서 변경되지 않았다.
- 증거 디렉터리: `.mysql-rehearsal/20261113-181637-5c83f13f/`.
- 백업: 위 디렉터리의 `yippee_club_db.sql`.
- SHA256: `bf8dbfc1c4140de8476c841e1c9aa6a0db6f992aa0cda6cfdfd704ff43567e7b`.
- 기존 migration 파일 해시는 백업/리허설의 실행 전후 일치했다.

## 순서별 실제 실행 결과

아래는 저장소 루트에서 실행한 명령이다. 표의 `python`은 `.\.venv\Scripts\python.exe`다.
모든 migration 계획은 사람이 내용을 확인한 후 다음 명령을 실행했다.

| 명령 | 종료 코드 | 실제 결과 |
|---|---:|---|
| `python scripts/inspect_user_migration.py --stage initial` | 0 | 10 tables / 18 migrations, 기존 FK |
| `python scripts/run_mysql_rehearsal.py` | 0 | 새 백업, 독립 복원 및 리허설 성공 |
| `python .mysql-rehearsal/20261113-181637-5c83f13f/verify_actual.py initial` | 0 | 서버 식별자, 백업과 현재 상태, 원본 행, FK/스키마 일치 |
| `python manage.py migrate accounts 0001 --settings=config.user_model_prepare --plan` | 0 | accounts.0001_initial 하나 |
| `python manage.py migrate accounts 0001 --settings=config.user_model_prepare --noinput` | 0 | 0001 적용 성공 |
| `python scripts/inspect_user_migration.py --stage prepared` | 0 | 13 tables / 19 migrations |
| `python .mysql-rehearsal/20261113-181637-5c83f13f/verify_actual.py prepared` | 0 | 원본 행 보존, 리허설 스키마/컬럼/FK/건수 일치 |
| `python manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --plan` | 0 | accounts.0002_bridge_admin_user 하나 |
| `python manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --noinput` | 0 | 0002 적용 성공 |
| `python scripts/inspect_user_migration.py --stage bridged` | 0 | 13 tables / 20 migrations, accounts_user FK |
| `python .mysql-rehearsal/20261113-181637-5c83f13f/verify_actual.py bridged` | 1 | Admin 인덱스 이름의 리허설 대비 차이로 중단 |

검증용 `verify_actual.py`는 Git 제외 증거 디렉터리에만 추가했다. DB를 읽기 전용으로 조회해
리허설의 단계별 스냅샷과 비교하고 원본 행 보존을 검사한다. 프로젝트 기능/설정/migration 코드는 수정하지 않았다.

## 중단 사유 및 읽기 전용 진단

추가 스키마 비교기가 다음 차이를 발견했다. **두 인덱스 모두 동일한 `user_id` 컬럼의 KEY**다.

```text
리허설: KEY django_admin_log_user_id_c564eba6_fk_auth_user_id (user_id)
실제:   KEY django_admin_log_user_id_fk_accounts_user (user_id)
```

실제 FK 제약조건 이름은 리허설과 동일하게
`django_admin_log_user_id_fk_accounts_user`이며 `accounts_user.id`를 참조한다.
관찰된 스키마 차이는 위 KEY 이름 한 곳이다. 자동 생성 인덱스와 dump로 복원된 명시적
인덱스의 취급 차이는 원인 후보이며, 이번 작업에서는 확정하거나 비교 예외를 추가하지 않았다.

실패 후 후속 DDL을 실행하지 않았다. 읽기 전용 진단에서 다음을 확인했다.

- UUID/포트/DB/계정은 실행 전과 동일하다.
- 13개 테이블, 20개 migration이며 accounts 0001과 0002가 정상 기록되어 있다.
- FK 전체와 migration 목록은 리허설의 0002 직후 상태와 일치한다.
- 초기 10개 테이블에 있던 모든 원본 행의 해시가 현재 데이터 안에 존재한다.
- `accounts_user` 및 두 M2M 테이블이 생성되었으며 사용자 데이터는 0건이다.
- `auth_user` 및 기존 M2M, `django_admin_log`를 삭제하지 않았다.
- 원본 `auth_permission` 24건과 ContentType 6건은 보존되었고, 각각 28건/7건으로 추가되었다.
- 상세 스냅샷: 증거 디렉터리의 `actual_bridged_diagnostic.json`.

## 이전 중단 시 보류된 단계 (이후 재개 완료)

기본 설정의 나머지 migrate, final 검사 및 실제 DB의 최종 Django 검사는 실행하지 않았다.
`email_verification.0001_initial`은 아직 미적용이며 이메일 인증 테이블 두 개는 없다.
따라서 API 구현/서비스 쓰기 재개가 가능한 최종 상태로 보고하지 않는다.

인덱스 구조와 제약조건의 동등성을 추가 검토하고, 관찰된 이름 차이를 처리할 검증 기준을
확정한 뒤 중단 지점부터 이어갈 수 있다. 재개 시 이미 적용된 0001로 migrate하여 되돌리면
안 된다. 다음 실제 DDL 후보는 기본 설정의 계획에서 이메일 인증 migration 하나만 확인한 뒤
적용하는 단계이며, 이번 작업에서는 실행하지 않았다.

DB 삭제/초기화/fake/역적용/기존 migration 수정/설정 복귀/테스트 사용자 생성/Git push는 하지 않았다.
`team3_db`와 기존 `test_yippee_club_db`에는 접근하지 않았다.

## 인덱스 동등성 근거 및 한정 예외

기존 격리 리허설 DB와 실제 DB에서 아래 모든 속성이 일치함을 확인했다.
원본 증거는 `.mysql-rehearsal/20261113-181637-5c83f13f/index_equivalence.json`이다.

| 속성 | 양쪽의 실제 값 |
|---|---|
| 컬럼/순서 | user_id / SEQ_IN_INDEX=1 |
| NON_UNIQUE / INDEX_TYPE | 1 / BTREE |
| COLLATION / SUB_PART | A / NULL |
| IS_VISIBLE / EXPRESSION | YES / NULL |
| PACKED / NULLABLE | NULL / 빈 문자열(NOT NULL 컬럼) |
| COMMENT / INDEX_COMMENT | 모두 빈 문자열 |
| CARDINALITY | 0 (증거 수집 시점, 재개 검사 시점 및 최종 검사 시점) |
| FK 대상 | 같은 DB의 accounts_user.id, PRIMARY 키 |
| MATCH_OPTION / UPDATE_RULE / DELETE_RULE | NONE / NO ACTION / NO ACTION |

이름을 제외한 인덱스 구조 및 FK 규칙이 같으므로 확인된 두 이름의 차이는 이 이관의
구조 검증에서 허용했다. DB의 인덱스 이름은 바꾸지 않았다.

보호된 `verify_actual.py`와 ACL은 추가 접근/수정 시도 없이 보존했다.
대신 새 `scripts/verify_user_migration.py`를 작성했다. 기존 스냅샷 비교 로직을 유지하며
index_equivalence.json의 실제 양쪽 속성이 일치하는지 확인하고, 현재 DB 속성도 다시 비교한다.
이름 예외는 `django_admin_log` 테이블의 아래 KEY 정의 한 곳에서만 적용한다.

```text
KEY django_admin_log_user_id_c564eba6_fk_auth_user_id (user_id)
↔ KEY django_admin_log_user_id_fk_accounts_user (user_id)
```

FK 제약조건 이름, 다른 테이블/인덱스/컬럼/제약조건, migration 목록, 행 건수는 그대로 비교한다.
기존 검증기의 리허설 smoke-test에 따른 AUTO_INCREMENT 카운터 처리도 유지했으며,
새로운 일반 스키마 무시 규칙은 추가하지 않았다. 초기 원본 행의 해시도 전부 보존됐는지 검사한다.
이 새 스크립트는 개발 DB에만 읽기 전용으로 연결하고 다른 DB에 연결하지 않는다.

## 중단 지점부터 재개한 실제 명령과 결과

쓰기 중지 유지에 대한 사용자의 명시적 확인을 계속 적용했고, 로컬 관련 Windows
앱 프로세스가 없는 상태에서 진행했다. 기존 전체 리허설/백업은 반복하지 않았다.
아래 명령은 한 단계씩 성공 결과를 확인한 뒤 실행했으며 모두 종료 코드 0이다.
`python`은 `.\.venv\Scripts\python.exe`다.

| 명령 | 실제 결과 |
|---|---|
| `python scripts/verify_user_migration.py --stage bridged` | PASS: 13 tables / 20 migrations, 전체 스키마·FK·원본 행 보존 및 인덱스 속성 확인 |
| `python manage.py migrate --settings=config.settings --plan` | email_verification.0001_initial 하나, 두 모델 생성 |
| `python manage.py migrate --settings=config.settings --noinput` | email_verification.0001_initial 적용 OK |
| `python scripts/inspect_user_migration.py --stage final` | PASS: 15 tables / 21 migrations, Admin FK accounts_user.id |
| `python scripts/verify_user_migration.py --stage final` | PASS: 전체 테이블·컬럼·제약조건·FK·migration 목록·건수 일치, 원본 행 해시 보존 |
| `python manage.py check --settings=config.settings --database default` | System check identified no issues (0 silenced) |
| `python manage.py makemigrations --settings=config.settings --check --dry-run` | No changes detected |
| `python manage.py showmigrations --settings=config.settings` | 21개 migration 모두 [X] |

추가로 쓰기 없는 Django shell 검사에서 `get_user_model() == accounts.User`, 이메일 식별자,
Admin LogEntry의 User 참조, SimpleJWT 인증 모델/토큰 발급 serializer 식별자,
기존 이메일 인증 뷰의 User 모델 선택이 모두 일치함을 확인했다.
개발 DB에 테스트 사용자를 만들거나 실제 API 요청/전체 테스트를 실행하지 않았다.

## 최종 실제 상태와 증거

- DB/계정/UUID/포트는 초기 대상과 동일하다.
- 테이블 **15개**, migration **21개**. accounts 0001/0002를 재적용/역적용하지 않았다.
- `accounts_user`, accounts M2M 두 테이블, 이메일 인증 테이블 두 개가 존재한다.
- Admin FK는 `django_admin_log.user_id → accounts_user.id`이며 INT 타입이 일치한다.
- 기존 `auth_user` 및 기존 M2M 테이블, Admin 로그 테이블은 보존했다.
- 초기 10개 테이블의 모든 원본 행 해시가 최종 상태에 존재한다.
- auth_permission 36건, ContentType 9건이며 사용자/로그/사용자 M2M/이메일 인증 데이터는 0건이다.
- 기존 migration 파일 해시와 백업 해시가 원본 증거와 일치한다.
- 새 검증 결과: `.mysql-rehearsal/application-validation/bridged.json`, `final.json`.
  기존 증거 폴더와 백업은 수정하지 않았다.
- 검증 스크립트와 이관 문서만 추가/갱신했다. 기능 구현·권한 변경·DB 초기화·fake·Git push는 하지 않았다.
- 이번 재개 작업에서는 `team3_db`, 기존 `test_yippee_club_db`, 리허설 DB에 연결하지 않았다.

DB 전환의 차단 요인은 해소됐다. **회원가입·로그인 API 구현 착수가 가능하다.**
실제 SMTP 전송 및 미구현 회원가입·로그인 HTTP API 성공을 검증한 것으로 해석하지 않는다.
