# 커스텀 User 이관 1단계: 코드 준비 및 검증

> 실제 적용 상태는 [실행 기록](USER_MIGRATION_APPLICATION.md)을 따른다.
> 실제 개발 DB 이관과 최종 검증이 완료됐다(15개 테이블/21개 migration). 아래는 과거 준비 기록이다.

> 후속 단계: [MySQL 리허설 결과와 실제 적용 명령](USER_MIGRATION_REHEARSAL.md).
> 격리 MySQL 백업·복원 및 이관을 검증했고, 리허설 DB명/설정 불일치를 수정했다.
> 후속 오프라인 검사 중 기존 테스트 DB 재생성 시도가 발생했으며 보존을 보장할 수 없다.
> 해당 문서의 사고 설명과 최신 결과가 아래 과거 기록보다 우선한다.
> 실제 개발 DB 전환은 여전히 미실행이다.

이 문서는 승인된 코드 준비 결과와 **별도 승인 후** 실행할 절차를 구분한다.
개발 DB 및 기존 테스트 DB에 새 migration을 적용하지 않았다.
2026-11-13 코드 준비에서 기본 `config.settings`에 accounts 앱과
`AUTH_USER_MODEL = 'accounts.User'`를 추가했다. **현재 개발 DB는 준비되지 않았으므로
이 코드를 서비스에 배포하거나 기본 설정으로 migrate/runserver를 실행하지 않는다.**
설정 활성화 코드는 준비됐지만 실제 DB 전환은 완료되지 않았다.

## 준비한 설정

- `config.user_model_prepare`: 기본 설정의 accounts 앱을 유지하고 `auth.User`로 명시적으로 재정의한다.
  대상 DB를 `yippee_club_db`로 제한한다. 실제 migrate에는 별도 승인이 필요하다.
- `config.user_model_prepare_preview`: 준비용 설정에 SQL 차단을 더한 오프라인 검증용이다.
- `config.user_model_preview`: 기존 커스텀 User 오프라인 검토용이다. 이 설정은
  DB 이름이 테스트 DB여도 SQL이 차단되므로 실제 이관이나 통합 테스트에 사용하지 않는다.

## 최초 migration 및 bridge

`accounts.0001_initial`은 수정하지 않았다. 의존성은 `auth.0012`이며, Admin에
의존하지 않는다. 기본 User가 활성화된 준비 상태에서도 accounts 모델이 자동으로
swapped 처리되지 않아 새 테이블을 정상 생성할 수 있다.

설정 전환 후 의존성은 다음과 같다. 순환 의존성은 없다.

```text
auth.0012 → accounts.0001 → admin.0001 → admin.0003 → accounts.0002
```

이미 Admin 이력이 존재하는 DB에서는 먼저 기본 User 설정으로 accounts.0001을
정상 적용해야 한다. 그러지 않고 설정부터 바꾸면 이력 일관성 오류가 발생한다.
오프라인 테스트에서 기존 이력의 일관성과, 전환을 먼저 했을 때의 충돌을 검증한다.

`accounts.0002_bridge_admin_user`는 현재 확인된 **빈 사용자 DB**만 대상으로 한다.

- MySQL과 허용된 DB 이름(`yippee_club_db` 또는 `test_yippee_` 접두사)을 검사한다.
- 실제 Admin FK의 개수·컬럼·대상을 introspection으로 확인한다.
- 이미 `accounts_user.id`를 참조하면 DDL 없이 종료한다. 신규 설치 경로도 이 경우다.
- 기존 FK가 `auth_user.id`라면 구/신 User, Admin 로그와 사용자 M2M 연결이 모두
  0건인지, 기존 auth.User 관리 권한이 그룹에 할당되지 않았는지 확인한다.
- Admin user_id와 새 User id의 실제 MySQL 컬럼 타입이 같은지 확인한다.
- 모든 검사 후 하나의 ALTER TABLE 문으로 **FK만** 교체한다.
- FK 교체 후 실제 연결 대상을 다시 확인한다.
- 기존 테이블이나 데이터, 권한·ContentType 레코드를 삭제하지 않는다.
- 기존 사용자가 생겼으면 자동 복사·병합하지 않고 별도 데이터 이관 검토를 요구한다.

`0002`는 자동 역적용을 허용하지 않는다. 새 User가 생긴 뒤 원래 FK로 무조건
되돌리면 무결성이 깨질 수 있으므로 역이관은 별도 승인·검증 대상으로 남긴다.
`migrate accounts zero`나 `migrate accounts 0001`로 복구하려고 하면 안 된다.
MySQL DDL은 전체 migration 트랜잭션으로 되돌려지지 않으므로 실패 시 즉시 중단한다.

`docs/sql/accounts_0001_preview.sql`와 `user_admin_fk_proposal.sql`은 과거 SQL 검토본이다.
실제 적용은 Django migration을 통해서만 진행한다. 검토본을 직접 실행한 뒤
`--fake`로 이력을 맞추지 않는다. RunPython의 동적 FK SQL은 sqlmigrate 출력만으로
검증할 수 없으므로 실제 DB introspection과 별도 MySQL 리허설이 필요하다.

## 이메일 기반 Admin

`accounts/admin.py`는 활성 User가 `accounts.User`일 때만 커스텀 User를 등록한다.
준비 상태에서는 기존 Django UserAdmin을 유지하고 새 User는 등록하지 않는다.

생성 폼은 email/password1/password2를 사용하며 Django 비밀번호 검증과 해시를
적용한다. 수정 폼은 비밀번호 해시를 읽기 전용으로 표시하고, 변경은 Django의
전용 비밀번호 변경 뷰를 사용한다. username/first_name/last_name 의존성을 제거했다.
이는 Admin 기능이며 회원가입 API나 미확정 약관·로그인 응답 계약을 확정하지 않는다.

## 실행한 검사와 한계

실행한 테스트는 SimpleTestCase와 모의 DB 객체를 사용한다. 개발·기존 테스트 DB에
테이블이나 migration 이력을 만들거나 수정하지 않는다.

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py check --settings=config.user_model_prepare
.\.venv\Scripts\python.exe manage.py check --settings=config.user_model_preview
.\.venv\Scripts\python.exe manage.py test accounts config email_verification.tests.AuthUnitTests --settings=config.user_model_prepare_preview --noinput
.\.venv\Scripts\python.exe manage.py test accounts config email_verification.tests.AuthUnitTests --settings=config.user_model_preview --noinput
```

신규 설치의 FK 무변경, 빈 기존 DB의 연결 변경, 데이터 존재·FK 불일치·키 타입
불일치·그룹 권한 존재 시 중단, 실패 후 자동 DDL 재실행 금지, Admin 등록·폼·해시,
기본/전환 상태 migration graph와 이력 조건을 검증한다.

2026-11-13 검증 결과:

- 위 두 SQL 차단 설정의 오프라인 테스트 각각 33개 통과(총 66회).
- `python -m unittest discover -s scripts/tests -v`: 16개 통과.
- MigrationAutodetector와 MigrationLoader(None)로 모델과 기존 migration의 차이가 없음을 확인했다.
  SQL이 필요한 makemigrations 대신 DB 연결 없는 검증을 사용했다.
- JWT 서명/검증, 활성 User 모델 조회(ORM 모의 처리), 비활성 사용자 거부,
  토큰 발급 serializer의 이메일 식별자, 이메일 인증의 활성 모델 조회를 검증했다.
- 실제 MySQL DDL 리허설, MySQL 기반 전체 API/Admin 통합 테스트, 백업 복원은 미검증이다.
  모의 검증 통과를 실제 MySQL 이관 성공으로 보고하지 않는다.

읽기 전용 트랜잭션으로 개발 DB를 조회했다. 대상은 `yippee_club_db`, 연결 계정은
`yippee_app@localhost`였다. 기존 auth/admin/contenttypes/sessions migration 18개만
적용되어 있었고 accounts/email_verification 이력과 테이블은 없었다.
`auth_user`, `django_admin_log`, 기존 사용자 M2M 두 테이블 및 auth.User 관련 그룹 권한은
모두 0건이었다. Admin FK는 여전히 `auth_user.id`다. 이는 조회 시점의 상태이며
승인된 실행 직전에 다시 확인해야 한다. `team3_db`는 조회하거나 변경하지 않았다.

## 독립 MySQL 리허설 계획 (환경 준비 후)

아래 두 시나리오는 기존 `test_yippee_club_db`를 재사용하지 않고 별도 빈 스키마 또는
별도 MySQL 인스턴스에서 실행해야 한다. 새 권한/환경이 필요한 경우 먼저 검토한다.

1. 기본 설정으로 auth/admin만 구성한 빈 DB에서 준비용 계정 migration 0001/0002를
   적용하고 설정을 전환한다. 기존 테이블과 권한·ContentType이 남아 있는지 비교한다.
2. 처음부터 accounts.User를 활성화한 빈 DB에서 전체 migration을 적용한다.
   Admin FK가 처음부터 새 User를 참조하고 bridge가 무변경 종료하는지 확인한다.
3. 각 환경에서 Admin 생성·로그인·비밀번호 변경과 기존 이메일 인증 API 전체 테스트를
   수행한다. 기존 데이터가 있는 거부 시나리오도 폐기 가능한 리허설 DB에서 검증한다.

현재 리허설 도구의 제한: `scripts/create_mysql_rehearsal.py`와 권한 도구는
`yippee_migration_rehearsal`을 대상으로 하지만 준비 설정은 `yippee_club_db`만,
bridge는 `yippee_club_db` 또는 `test_yippee_` 접두사만 허용한다. 따라서 이 도구로
생성한 DB에서 준비 설정/bridge를 그대로 실행할 수 없다. 실제 리허설 전 별도 설정과
허용 대상의 정합성을 검토해야 한다. 이번 작업에서는 DB나 계정 생성, GRANT를 실행하지 않았다.
대안은 별도 MySQL 인스턴스에서 `yippee_club_db`라는 이름을 사용하고 연결 대상을
명시적으로 분리하는 것이다. 개발 서버와 같은 인스턴스에서는 이 대안을 사용하지 않는다.

## 실제 개발 DB 이관 명령 순서 — 현재 실행 금지

전제: 별도 MySQL 리허설 성공, DB 백업 및 복원 검증, 이관 승인, 쓰기 트래픽 중단,
사용자/Admin 로그/연결·관련 그룹 권한 0건 재확인, 개발 DB 이름 검증.
아래 명령은 계획이며 이번 단계에서 실행하지 않았다.

승인 검토할 백업 명령 예시(실제 mysql 도구 경로와 안전한 출력 경로를 먼저 지정):

```powershell
mysqldump --host=127.0.0.1 --port=3306 --user=<백업계정> --password --single-transaction --routines --triggers --events --databases yippee_club_db --result-file=<백업파일.sql>
```

비밀번호는 명령 인자로 넣지 않는다. 백업 파일의 해시/보관 위치를 기록하고, 별도
인스턴스에서 복원 및 스키마·건수·migration 이력을 확인해야 한다. 백업 파일 존재만으로
복원 검증을 대신하지 않는다. 이번 작업에서 백업이나 복원 명령은 실행하지 않았다.

```powershell
# 1. 활성 User를 바꾸지 않고 accounts.0001만 적용
.\.venv\Scripts\python.exe manage.py migrate accounts 0001 --settings=config.user_model_prepare --plan
.\.venv\Scripts\python.exe manage.py migrate accounts 0001 --settings=config.user_model_prepare --noinput

# 2. 빈 DB 조건을 검사하고 Admin FK만 전환
.\.venv\Scripts\python.exe manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --plan
.\.venv\Scripts\python.exe manage.py migrate accounts 0002_bridge_admin_user --settings=config.user_model_prepare --noinput
```

이후 단계별 검증이 통과했을 때만 준비된 기본 설정 코드를 배포한다. 이미 파일에
accounts 앱과 `AUTH_USER_MODEL = 'accounts.User'`가 있으므로 추가 편집은 필요 없다.
코드가 두 User 상태를 동시에 서비스하지 않도록 이 시점까지 유지보수 상태를 유지한다.
두 accounts migration 적용 기록과 실제 Admin FK가 `accounts_user.id`인지 먼저 검증한다.
그다음 승인된 단계에서:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py showmigrations
.\.venv\Scripts\python.exe manage.py migrate --plan
# 계획이 accounts 신규 적용 이력과 이메일 인증 테이블 추가만 포함하는지 검토 후:
.\.venv\Scripts\python.exe manage.py migrate --noinput
```

예상 영향: 새 accounts 사용자·M2M 테이블 3개 추가, Admin FK 교체,
정상 Django migration 기록 추가, 새 모델의 ContentType/permission 추가,
개발 DB에서 아직 미적용인 이메일 인증 테이블 2개 추가. 기존 행의 삭제·임의 수정은 없다.
이메일 인증 코드·API 및 SECRET_KEY는 유지한다. `team3_db`는 대상으로 삼지 않는다.

새 설정으로 기존 테스트 DB를 곧바로 `--keepdb` 재사용하면 같은 migration 이력 충돌이
난다. 별도 승인한 보존형 전환 또는 새로운 테스트 스키마 준비 후에만 전체 테스트를
실행한다. 이번 단계에서는 기존 테스트 DB에 migration이나 테스트를 실행하지 않았다.
