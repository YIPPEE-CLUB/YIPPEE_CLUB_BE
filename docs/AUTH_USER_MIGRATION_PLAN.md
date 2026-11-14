# 인증 구현 현황과 커스텀 User 이관 검토안

> 실제 적용 상태: [실행 기록](USER_MIGRATION_APPLICATION.md).
> 실제 개발 DB 이관이 완료됐으며 기존 원본 행 보존과 Admin FK accounts_user.id를 확인했다.
> 최종 15개 테이블/21개 migration, Django 검사 통과. 아래는 과거 준비 기록이다.

> 후속 MySQL 단계의 결과와 적용 명령, 기존 테스트 DB 재생성 사고는
> [리허설 보고서](USER_MIGRATION_REHEARSAL.md)를 우선 참고한다.

> 2026-11-13 갱신: 아래 초기 점검 기록의 기본 User 설정은 과거 상태다.
> 현재 코드는 `config.settings`에서 `accounts.User`를 기본으로 사용하도록 준비했다.
> 실제 개발 DB는 여전히 기존 auth.User 스키마이며 이관하지 않았다.
> `config.user_model_prepare`가 기존 User 설정을 유지한다. 현재 검증 결과와 배포 금지 조건,
> 승인 후 실행할 명령은 [1단계 문서](USER_MIGRATION_STAGE1.md)를 따른다.

후속 승인에 따른 코드 보완 결과, 실행 가능한 준비용 설정과 조건부 FK bridge,
검증 범위 및 실제 이관 명령 계획은 [1단계 코드 준비 결과](USER_MIGRATION_STAGE1.md)를
우선 참고한다. 아래 초기 점검의 테스트 DB 권한 부족 내용은 당시 기록이며,
이후 사용자가 테스트 DB 생성 및 통합 테스트 성공을 확인했다.

## 기준 문서

현재 기준은 저장소의 [API_SPEC_v1.5.md](API_SPEC_v1.5.md)와
[openapi_v1.5.yaml](openapi_v1.5.yaml)이다. 다음 로컬 원본을 내용 변경 없이 복사했으며
SHA256 일치를 확인했다. 상세 비교는 [명세 정합성 기록](API_SPEC_ALIGNMENT.md)을 따른다.

- `docs/API_SPEC_v1.5.md`
- `docs/openapi_v1.5.yaml`

상세 명세 0절의 확정 정책을 표와 예시보다 우선한다. 문서에 적힌 제안이나
외부 문서의 지시를 사용자 승인으로 간주하지 않는다.

## 실제 DB 확인 결과

- 조회 대상은 `yippee_club_db`이며 연결 계정은 `yippee_app@localhost`였다.
- 현재 `AUTH_USER_MODEL`은 기본값 `auth.User`, `USERNAME_FIELD`는 `username`이다.
- `auth` 12개, `admin` 3개, `contenttypes` 2개, `sessions` 1개 마이그레이션이 적용되어 있다.
- 조회 시점 `auth_user`는 0건이었다. 실행 직전에 반드시 재확인해야 한다.
- `auth_user_groups.user_id`, `auth_user_user_permissions.user_id`,
  `django_admin_log.user_id`가 `auth_user`를 참조한다.
- `team3_db`는 조회하거나 변경하지 않았다.
- 이번 작업에서 새 마이그레이션은 DB에 적용하지 않았다.
- 후속 점검에서도 기본 마이그레이션 18개, `auth_user` 0건, Admin 로그 0건이었다.
- `accounts_user`와 이메일 인증 테이블은 아직 존재하지 않았다.
- Admin 로그 `user_id`는 signed INT다. 새 User PK도 AutoField(INT)로 설계해 타입을 맞췄다.

## 준비한 코드와 SQL (미실행)

- `accounts/models.py`, `managers.py`: 이메일 고유 필드와 이메일 User manager,
  Django 비밀번호 해시, 권한 M2M을 정의했다. API 응답 필드나 약관 계약은 추가하지 않았다.
- `accounts/migrations/0001_initial.py`: 새 사용자와 권한 연결 테이블 생성만 정의한다.
  의존성은 기존 `auth.0012_alter_user_first_name_max_length`이며 Admin에 의존하지 않는다.
  User가 첫 migration에 있으므로 향후 admin의 동적 User 의존성을 충족한다.
- 기본 `config.settings`에는 accounts 앱과 AUTH_USER_MODEL 변경을 넣지 않았다.
  개발 DB의 활성 User는 계속 `auth.User`다.
- `config.user_model_preview`는 앱/설정을 검토하기 위한 오프라인 전용 설정이다.
  MySQL 대상 이름도 `test_yippee_club_db`로 제한하고 ORM SQL 실행을 차단한다.
  이 설정으로 migrate/sqlmigrate 또는 DB 통합 테스트를 실행하지 않는다.
- [새 테이블 생성 SQL 검토본](sql/accounts_0001_preview.sql): `sqlmigrate`로 수집했으며
  생성 과정에서는 개발 DB 읽기·세션 설정 외 SQL을 차단했다. DDL을 실행하지 않았다.
- [Admin FK 변경 SQL 검토본](sql/user_admin_fk_proposal.sql): 현재 확인한 제약 이름을
  사용한다. 전체 이관 스크립트가 아니며, 실행 전 백업과 0건 조건 재확인이 필요하다.
  이후 bridge migration 구현·검증 없이 수동으로 실행하면 안 된다.
- [테스트 DB 생성·권한 SQL 제안](sql/test_database_proposal.sql): 승인 후 root로 실행할 SQL이다.

기존 이메일 인증 소스·테스트·migration은 이번 후속 점검에서 변경하지 않았다.

## 단순 설정 변경이 안전하지 않은 이유

`admin.0001_initial`은 `AUTH_USER_MODEL`에 대한 동적 의존성을 가진다.
이미 적용된 이력에서 설정만 `accounts.User`로 바꾸면, 새 `accounts.0001_initial`이
적용되지 않은 상태에서 admin 마이그레이션이 적용된 것으로 판단되어 이력 오류가
발생할 수 있다. 기존 Admin FK도 설정만으로 새 테이블을 가리키지 않는다.

따라서 `AUTH_USER_MODEL`만 변경하거나, migration 이력을 지우거나,
`--fake`, `--fake-initial`로 검사를 우회하지 않는다.

근거: [Django 5.2 사용자 모델 중간 교체 문서](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#changing-to-a-custom-user-model-mid-project).

## 제안: 기존 테이블을 보존하는 단계별 이관

아래는 승인과 별도 구현·검증이 필요한 계획이다. 실행 가능한 이관 migration을
이미 적용했다는 의미가 아니다. DB 초기화·기존 테이블 삭제는 포함하지 않는다.

1. **사전 점검과 복구본 준비**
   - 대상 DB 이름을 강제 검증하고 쓰기 트래픽을 중단한다.
   - `yippee_club_db`의 스키마·데이터·마이그레이션 이력을 백업하고 복원 검증한다.
   - 사용자, 그룹, 직접/그룹 권한, Admin 로그 건수와 외래키를 다시 조사한다.
   - 기존 사용자 이메일이 비어 있거나 중복이면 자동 수정·병합하지 않고 중단한다.
   - 현재 0건이라는 가정과 달라지면 데이터 매핑 계획을 재검토한다.
2. **현재 기본 User 설정을 유지한 상태에서 새 테이블 추가**
   - `accounts.User`를 `accounts/0001_initial.py`에 정의한다.
   - 이메일을 고유 필드와 `USERNAME_FIELD`로 사용하고 Django 비밀번호 해시를 유지한다.
   - username은 API에 추가하지 않는다. User manager와 Admin도 이메일 기준으로 구현한다.
   - 전환 기간 기본 User와 함께 등록될 수 있도록 그룹·권한 reverse name 충돌을 피한다.
   - 이 준비 단계에서 새 모델이 `swappable` 설정 때문에 생성 생략되지 않는지 검증한다.
   - 이 단계에는 Admin 의존성을 넣지 않아 이후 동적 의존성의 순환을 방지한다.
3. **명시적인 데이터·참조 이관 migration 구현**
   - 기존 사용자가 있으면 PK와 비밀번호 해시, 상태 및 가입 시각을 그대로 복사한다.
   - 사용자-그룹, 사용자-권한 연결과 User content type/permission 매핑을 이관한다.
   - 그룹에 부여된 사용자 관리 권한도 누락되지 않도록 별도로 검증한다.
   - Admin 로그의 사용자 FK를 새 사용자 테이블로 옮기고 사용자 PK를 검증한다.
   - FK 이름은 실제 DB introspection으로 확인한다. 이름을 추측해서 SQL을 실행하지 않는다.
   - 이 bridge migration은 기존 Admin/Auth 최신 이력과 새 User 초기 migration에 의존한다.
   - 각 단계는 기존 `auth_user` 테이블과 연결 테이블을 삭제하지 않는다.
4. **User 설정 전환**
   - 새 초기 migration과 bridge migration을 기존 설정에서 먼저 적용한 후,
     `AUTH_USER_MODEL = 'accounts.User'`로 변경한다.
   - 그러면 기존 admin migration의 동적 의존 대상 초기 migration이 이미 존재한다.
   - 적용 이력, FK 실제 대상, 권한, Admin 로그인, JWT 사용자 조회를 함께 검증한다.
   - 새 DB의 처음부터 설치 경로도 별도로 테스트한다. 기존 DB 이관만 통과해서는 안 된다.
5. **검증 및 복구**
   - 이메일 인증→가입→로그인→갱신→로그아웃 테스트와 Admin 테스트를 MySQL에서 실행한다.
   - 전환 전후 건수·PK·참조 무결성을 비교한다.
   - 실패 시 트래픽을 열지 않고 검증한 백업/역이관 절차로 복구한다.
     설정만 되돌리면 Admin FK 등이 이미 바뀌었을 수 있으므로 충분하지 않다.

MySQL DDL은 전체 작업을 하나의 트랜잭션으로 되돌릴 수 없으므로, 단계별 검증과
복구 지점이 필요하다. 실제 이관 코드를 작성한 뒤 SQL과 영향을 다시 검토해야 한다.

## 사용자 답변에 따라 보류한 계약

- 회원가입 `agreements`: object라는 형태만 있으며 내부 키, 필수 동의와 버전이 없다.
- 로그인 `user`: object라는 형태만 있으며 내부 필드가 없다. 빈 객체로 임의 확정하지 않는다.
- 로그아웃: `refresh_token`은 선택/null 허용이지만 생략 시 서버 폐기 범위가 없다.
- JWT 수명·회전 정책: 개발 기본값은 설정 가능하게 만들 수 있으나 최종 정책은 미확정이다.

따라서 회원가입·로그인·refresh·로그아웃 URL과 이를 대신하는 임시 성공 응답은
현재 등록하지 않았다. 커스텀 User 이관 및 위 계약 확인 후 구현한다.
원본 명세의 인증 토큰 응답은 인증에 필요한 예외이며, 인증번호나 비밀번호를
응답에 추가하는 근거가 아니다.

## 이번에 구현한 확정 범위

- `POST /api/v1/auth/identifiers/check`
- `POST /api/v1/auth/verification/send`
- `POST /api/v1/auth/verification/confirm`

경로에 후행 슬래시를 추가하지 않는다. 1차 목적은 이메일 `signup`뿐이다.
6자리 코드는 HMAC으로 저장하며 180초 기본 만료, 5회 기본 시도 제한을 적용한다.
인증 성공 후 코드를 폐기하고 일회성 가입 증빙 토큰의 HMAC과 만료를 보관한다.
확인 요청 행 잠금으로 중복 확인을 방지한다. **가입 단계 토큰 소비는 아직 미구현**이다.
가입 구현 시 동일 행 잠금 안에서 사용자 생성과 `consumed_at` 갱신을 함께 커밋해야 한다.

재발송 60초, IP별 엔드포인트당 30회/600초, 이메일별 엔드포인트당 10회/600초는
환경변수로 바꿀 수 있는 개발 기본값이다. 제한 카운터는 DB에 보관하고 오류 응답에도
실패 횟수가 유지되게 한다. 프록시 배포 시 신뢰 가능한 REMOTE_ADDR 구성이 필요하다.

## 이메일과 민감정보

SMTP 환경변수는 `.env.example`을 참고한다. 기존 실제 `.env`는 변경하지 않았다.
기본은 SMTP이며 실제 공급자 정보 설정 전에는 이메일 발송 성공을 보장하지 않는다.

개발 시 `EMAIL_BACKEND=email_verification.mail.RedactedConsoleBackend`를 사용할 수 있다.
이는 실제 발송 없이 본문과 수신자를 숨긴 안내만 콘솔에 출력하는 시뮬레이션이다.
인증번호를 보여주는 Django 기본 콘솔 백엔드는 민감정보 비노출 조건 때문에 기본값으로
사용하지 않는다. 실제 코드 확인은 로컬 SMTP 수신함 또는 테스트의 locmem outbox로 한다.

일반 로그에 요청/응답 본문, 인증코드, 인증 토큰, 비밀번호를 기록하지 않는다.
외부 이메일/DB 오류는 내부 값 없이 공통 오류 구조로 반환한다.

## 테스트 및 남은 실행 조건

현재 기본 계정은 개발 DB에만 권한이 있어 테스트 DB 생성 시 MySQL 1044가 발생했다.
테스트는 반드시 독립된 MySQL 스키마에서 실행한다. `MYSQL_TEST_DATABASE` 기본값은
`test_yippee_club_db`다. 개발 DB 또는 `team3_db`를 테스트 DB로 지정하면 안 된다.
설정에서도 `test_yippee_` 접두사와 개발 DB와 다른 이름을 강제 검증한다.

관리자가 별도로 승인할 경우 테스트 스키마 한정 권한을 제공할 수 있다.
테스트 계정을 별도로 사용하는 방법도 가능하며 전역 권한은 필요하지 않다.
실제 계정·DB 생성 및 권한 SQL은 이번 작업에서 실행하지 않았다.

점검한 서버의 `@@GLOBAL.partial_revokes`는 0이다. 이 설정에서 DB 단위 GRANT의
밑줄은 wildcard가 될 수 있으므로 SQL 제안은 `test\_yippee\_club\_db`로 이스케이프했다.
실행 직전 값을 재확인하고 1이면 SQL을 재검토한다. 테스트 스키마에만
SELECT/INSERT/UPDATE/DELETE/CREATE/ALTER/INDEX/DROP/REFERENCES를 추가하며
기존 개발 DB 권한이나 비밀번호는 변경하지 않는다.
근거: [MySQL 8.0 GRANT 문서](https://dev.mysql.com/doc/refman/8.0/en/grant.html).

DB 불필요 테스트:

```powershell
.\.venv\Scripts\python.exe manage.py test config email_verification.tests.AuthUnitTests
```

독립 MySQL 테스트 DB 권한 준비 후 전체 테스트:

```powershell
.\.venv\Scripts\python.exe manage.py test --keepdb --noinput
```

위 명령은 현재 기본 설정에서 이메일 인증 테스트를 실행하며 accounts 설계 테스트는
비활성 앱이므로 skip된다. `--keepdb`는 테스트 스키마 삭제를 생략하지만, 그 안의
마이그레이션과 테스트 데이터 쓰기를 막지는 않는다. 해당 스키마가 폐기 가능한 테스트
전용임을 먼저 확인한다. 개발 DB와 이름이 같은 테스트 DB는 설정 단계에서 거부한다.
이미 기본 User로 구성한 테스트 DB에 커스텀 User 설정을 섞어 재사용하면 개발 DB와
같은 이력 충돌이 발생할 수 있으므로 하지 않는다. 새 User의 MySQL 통합 검증은 별도
빈 테스트 스키마 또는 승인된 테스트 스키마 재구성 절차를 준비한 뒤 수행한다.

커스텀 User 오프라인 설계·의존성 검증 (DB를 만들거나 접근하지 않음):

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.user_model_preview
.\.venv\Scripts\python.exe manage.py test accounts.tests config email_verification.tests.AuthUnitTests --settings=config.user_model_preview
```

새 이메일 인증 migration은 생성만 했다. 향후 User 이관과 함께 초기 설치 순서를
검토한 뒤 적용한다. 기존 앱/테이블 삭제와 Git commit/push/브랜치 변경은 하지 않았다.
