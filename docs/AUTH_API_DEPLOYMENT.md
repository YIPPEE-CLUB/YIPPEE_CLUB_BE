# 인증 API 개발 DB 적용 완료

2026-11-13 KST. 승인된 accounts.0003 하나를 실제 `yippee_club_db`에 적용했다.
최종 **16개 테이블, 22개 migration**, Admin FK `accounts_user.id`를 확인했다.
현재 인증 API 코드를 개발 DB에서 실행할 수 있고 다음 API 개발을 시작할 수 있다.
서비스 시작/자동 재시작은 실행하지 않았다. 정책 미확정 항목은 문서 하단에 구분한다.

## 사전 검토 및 범위

- Git 상태는 기존 README/.gitignore 변경과 다수 미추적 프로젝트 파일이 있는 상태였다.
  기존 사용자 변경을 되돌리거나 commit/push하지 않았다.
- `docs/API_SPEC_ALIGNMENT.md`와 원본 v1.5 계약, 모델/신규 migration을 확인했다.
- 기존 적용 migration 파일은 이전 증거의 SHA256과 일치했다. 원본 명세 파일도 변경하지 않았다.
- source UUID: `5491c807-5688-11f1-a0bf-c86e08e6aa63`, 포트 3306,
  DB `yippee_club_db`, 계정 `yippee_app@localhost`를 실행 전후 확인했다.
- 기존 사용자의 쓰기 중지 유지 확인을 반영하고 관련 Windows 앱 프로세스가 없음을 확인했다.
  현재 앱 계정에 보이는 개발 DB 세션은 점검 연결뿐이었다. 이 계정으로 다른 계정의 전체
  세션을 새로 검증했다고 주장하지 않는다. 백업 이후 적용 직전까지 전체 상태가 동일함을 비교했다.
- 초기 15개 테이블/21개 migration, User/Admin 로그/사용자 M2M 0건을 확인했다.
- 계획은 accounts.0003 하나뿐이었다. 기존 User 이관 0001/0002는 반복하지 않았다.

## 새 백업과 기존 격리 인스턴스의 복원/업그레이드

증거 디렉터리: `.mysql-rehearsal/auth-deploy-28a6a2939cc2/`.
백업 `yippee_club_db.sql`은 17,702 bytes이며 SHA256은 다음과 같다.

```text
cb103dd2d6619fe30bb3a5fed45084ac86e4aa48c3f9b6f843abbe3a389fb1eb
```

`--single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF`
등 기존 검증 옵션으로 읽기 전용 백업을 생성했다. DROP/CREATE DATABASE/USE 개발 DB를
포함하는 덤프를 생성하지 않았다. 자격정보/백업은 실행 사용자와 SYSTEM만 접근하는
Git 제외 디렉터리에 보관하며 비밀번호를 로그/CLI 인자로 출력하지 않았다.

기존 격리 MySQL(`.mysql-rehearsal/auth-api-cad00793f0c4/data`)을 재사용했다.
실제 server_id=9133307, 포트 33307, 기존 UUID/datadir를 검사하고 빈
`test_yippee_migration_fresh`에만 복원했다. 기존 테스트 스키마를 비우거나 덮어쓰지 않았다.
복원 직후 모든 테이블/컬럼/제약조건/FK/전체 행 해시/migration 이력이 source 백업과 일치했다.

복원 DB에서 0003 계획 하나를 확인하고 적용하여 16개 테이블/22개 migration 업그레이드를
검증했다. 이후 같은 격리 인스턴스의 전용 suite DB에서 전체 테스트를 수행했다.
source DB에 테스트 사용자/더미 데이터를 만들거나 API 요청을 실행하지 않았다.
검증 완료 후 해당 격리 서버만 정상 종료했다. datadir/백업/기존 증거는 보존했다.

## 통합 테스트와 실제 HTTP 검증

- 전체 Django 테스트: **72개 중 70개 성공, 0개 실패, 2개 skip**.
  skip은 실제 SQL을 금지하는 오프라인 설정 전용 검사다.
- 실제 TCP/WSGI HTTP 테스트: **20개 성공, 0개 실패**.
  복원 후 0003을 적용한 격리 DB만 사용했다.
- HTTP 흐름: 미인증 가입 거부 → 이메일 코드 발송/확인 → 가입 → 중복 가입 거부,
  무인증 프로필 거부, 프로필 조회/수정, 권한 필드 주입 거부, 로그인 실패/성공,
  Refresh → 로그아웃 → 폐기 Refresh 거부, 비밀번호 변경 후 이전 Access 거부,
  재설정 메일/확인/토큰 재사용 거부/새 비밀번호 로그인.
- 메일은 locmem backend이므로 실제 SMTP 전달 성공을 검증한 것은 아니다.
- 로그: 위 증거 디렉터리의 `test.txt`, `http-smoke.txt`, `migrate-plan.txt`, `migrate.txt`.

## 실제 개발 DB 실행 명령 및 결과

아래 `python`은 `.\.venv\Scripts\python.exe`다. 단계별 종료 코드와 결과를 확인하고 진행했으며
모두 종료 코드 0이다. 실제 migration은 0003 적용 명령 한 번뿐이다.

| 명령 | 결과 |
|---|---|
| `python manage.py migrate accounts 0003_user_agreements_user_name_user_nickname_user_phone_and_more --settings=config.settings --plan` | 0003 하나: User 필드 4개 추가, RefreshSession 생성 |
| `python scripts/prepare_auth_api_deploy.py prepare` | 새 백업/복원/격리 업그레이드/통합 및 TCP HTTP 테스트 PASS |
| `python scripts/prepare_auth_api_deploy.py verify-before --evidence .mysql-rehearsal/auth-deploy-28a6a2939cc2` | 백업 이후 source 상태 불변, 대상 식별자 PASS |
| `python manage.py migrate accounts 0003_user_agreements_user_name_user_nickname_user_phone_and_more --settings=config.settings --plan` | 적용 직전 계획 동일 |
| `python manage.py migrate accounts 0003_user_agreements_user_name_user_nickname_user_phone_and_more --settings=config.settings --noinput` | Applying accounts.0003... OK |
| `python scripts/prepare_auth_api_deploy.py verify-final --evidence .mysql-rehearsal/auth-deploy-28a6a2939cc2` | 전체 스키마/FK/migration/원본 행 보존 PASS, 16 tables / 22 migrations |
| `python manage.py check --settings=config.settings --database default` | System check identified no issues (0 silenced) |
| `python manage.py makemigrations --settings=config.settings --check --dry-run` | No changes detected |
| `python manage.py showmigrations --settings=config.settings` | 22개 모두 [X] |

## 추가된 스키마와 데이터 보존

- 적용 migration: `accounts.0003_user_agreements_user_name_user_nickname_user_phone_and_more`.
- accounts_user: agreements(JSON), name/nickname/phone(TEXT) 추가.
- 새 테이블: accounts_refreshsession. user FK → accounts_user.id,
  unique token_digest, expires_at/revoked_at/created_at.
- 기존 Admin FK와 나머지 기존 FK는 유지됐다. 개발 DB 최종 스키마/컬럼/FK/행 건수는
  같은 백업의 격리 업그레이드 결과와 정확히 일치한다.
- 기존 15개 테이블의 원본 행 해시가 전부 보존됐다.
- auth_permission은 40건, ContentType은 10건, migration 기록은 22건이다.
- accounts_user/auth_user/Admin 로그/사용자 M2M/RefreshSession/이메일 인증/속도 제한 데이터는 모두 0건이다.
- 백업 파일 해시와 모든 migration 파일 해시는 준비 시점과 최종 검사 시점이 일치한다.
- 이번 작업에서 API 코드·모델·기존/신규 migration 내용은 수정하지 않았다.
  운영 검증 도구 `scripts/prepare_auth_api_deploy.py`, `scripts/auth_http_smoke.py`와 문서만 추가/갱신했다.
- `team3_db` 및 기존 `test_yippee_club_db`에는 접근하지 않았다. DB 삭제/초기화/fake/Git push는 하지 않았다.

## 구현 완료 및 남은 정책

기존 이메일 인증 3개, 가입/로그인/Refresh/로그아웃, 프로필 GET/PATCH,
비밀번호 변경/재설정 요청/확인의 **12개 operation**을 사용할 수 있다.
정확한 URL/요청/응답은 [정합성 기록](API_SPEC_ALIGNMENT.md)을 따른다.

다음 사항은 API/DB 구현 실패가 아니라 v1.5 원문에 남은 정책 공백이다.

- agreements 필수 내부 키·버전·실제 동의 정책: 현재 object 검사와 원문 저장만 한다.
- 로그인 user 내부 계약: 현재 명세의 내 프로필 필드를 재사용한다.
- 토큰 생략 로그아웃의 전체 세션 폐기 범위: 현재 전달된 토큰만 폐기한다.
- JWT/재설정 만료·회전 최종 정책, 실 SMTP 설정/프론트엔드 재설정 링크.
- 소셜/실명/휴대전화 인증, 탈퇴 삭제·보존 정책, 프로필 사진 저장/삭제 정책은 별도 구현 대상이다.

기본값/한계의 상세 내용은 [구현 기록](AUTH_API_IMPLEMENTATION.md)을 따른다.
**인증 API의 개발 DB 적용은 완료됐으며 다음 API 개발을 진행할 수 있다.**
