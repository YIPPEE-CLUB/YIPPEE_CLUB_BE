# v1.5 인증 API 구현 및 추가 migration 계획

> 최신 상태: [개발 DB 적용 완료 기록](AUTH_API_DEPLOYMENT.md).
> accounts.0003 적용 및 최종 검증을 완료했다. 현재 16개 테이블/22개 migration이다.
> 아래 미적용/배포 전제 설명은 최초 구현 당시의 준비 기록이며 현재 적용 결과는 최신 기록을 따른다.

## 구현 범위와 명세 원본

현재 API 구현 기준은 저장소의 [API_SPEC_v1.5.md](API_SPEC_v1.5.md)와
[openapi_v1.5.yaml](openapi_v1.5.yaml)이다. 원본과의 SHA256 일치 및 기존 API 비교 결과는
[명세 정합성 기록](API_SPEC_ALIGNMENT.md)에 정리했다.

구현 당시에는 저장소에 원본이 없어 외부 원본을 읽었고, 이후 내용 변경 없이 위 저장소 경로로
복사했다. 출처 파일명과 SHA256은 명세 정합성 기록에 보관한다.

0절의 이메일 가입 password/verification_token 필수 정책을 기존 표의 선택/nullable 표기보다
우선 적용한다. 아래 URL에는 후행 slash가 없다. JSON 응답과 공통 오류 구조는 기존 구현을 재사용한다.

| Method | URL | 성공 응답/상태 |
|---|---|---|
| POST | `/api/v1/auth/signup` | 201: user_id, access_token, refresh_token |
| POST | `/api/v1/auth/login` | 200: access_token, refresh_token, user |
| POST | `/api/v1/auth/token/refresh` | 200: access_token, refresh_token |
| POST | `/api/v1/auth/logout` | 200: message |
| GET | `/api/v1/users/me` | 200: id, email, phone, name |
| PATCH | `/api/v1/users/me` | 200: id, email, phone, name |
| PATCH | `/api/v1/users/me/password` | 200: message |
| POST | `/api/v1/auth/password/reset-request` | 200: message |
| POST | `/api/v1/auth/password/reset-confirm` | 200: message |

message는 `처리되었습니다.`다. 로그인/refresh의 잘못된 자격정보는 해당 상세 표에 맞게 400이며,
보호 API의 누락·무효 Access 토큰은 401이다. 가입 중복/소비된 증빙은 409, 인증 요청 제한은 429다.
프로필/비밀번호 변경은 JWTAuthentication과 기본 IsAuthenticated 설정을 그대로 사용한다.

기존 세 API(identifiers/check, verification/send, verification/confirm)는 수정하거나 제거하지 않았다.
가입은 기존 EmailVerification의 token_digest를 찾고, 이메일·목적·확인 완료·만료·미소비를 검사한다.
행 잠금 안에서 사용자 생성, consumed_at 갱신, Refresh 세션 생성을 함께 commit한다.
실패하면 사용자와 인증 증빙 소비가 함께 rollback된다. 이메일의 DB unique 제약도 유지한다.

로그인/가입은 UserManager와 Django password hash를 사용한다. 신규 비밀번호는 영문·숫자 포함
8자 이상과 기존 Django validators를 적용하며, 앞뒤 공백을 임의로 제거하지 않는다.
프로필 수정은 본인 request.user의 name/nickname만 허용하고 id/email/phone/권한/password 주입은 거부한다.

## 명세에서 미확정인 부분의 처리

- **agreements 내부 구조/필수 동의/버전**은 원문에 없다. 필수 JSON object 여부만 검사하고
  전달받은 객체를 그대로 보관한다. `{}`도 명세상 object이므로 허용한다. 법적 동의 요건을
  검증했다고 볼 수 없으며 실제 필수 키/버전 계약 확정 후 검증을 추가해야 한다.
- 로그인 `user` 내부 필드는 원문에서 object로만 되어 있다. 별도의 임의 필드 집합을 만들지 않고
  같은 문서의 내 프로필 응답(id/email/phone/name)을 재사용했다. 프론트엔드 합의가 필요하다.
- 프로필은 가입 시 입력받지 않으므로 name/nickname/phone의 초기값은 빈 문자열이다.
  PATCH의 nullable name/nickname은 빈 문자열로 지워 GET의 non-null 문자열 계약을 유지한다.
  nickname은 저장되지만 응답 필드에는 포함하지 않는다. phone은 이 API에서 수정할 수 없다.
- 로그아웃의 refresh_token 생략/null은 명세대로 허용한다. 폐기 대상 자격증명이 없으므로
  이 경우 성공 응답만 반환하며 다른 세션을 자동 폐기하지 않는다. 전달된 Refresh는 해당 세션만
  폐기하며 같은 요청은 멱등 처리한다. 전체 기기 로그아웃 계약은 구현/확정하지 않았다.
- Access 300초, Refresh 86,400초, reset 600초는 환경변수로 조정 가능한 구현 기본값이다.
  v1.5 최종 정책으로 주장하지 않는다. Refresh 갱신은 같은 Refresh를 반환하고 수명을 연장하지 않는다.
  기존 Refresh를 회전/재발급하는 정책은 추가하지 않았다.
- 로그아웃은 Refresh 재사용을 차단한다. 이미 발급된 Access는 만료까지 유지된다.
  비밀번호 변경/재설정은 Refresh 세션을 폐기하고 SimpleJWT CHECK_REVOKE_TOKEN으로 기존 Access도 거부한다.
  이 설정 도입 전 발급된 hash_password claim 없는 토큰도 재로그인이 필요하다.
- reset-token 전달은 이메일 본문을 사용한다. 응답에는 토큰을 넣지 않는다. 프론트엔드 링크 URL은
  명세에 없어 만들지 않았다. 실제 SMTP 전달은 환경 설정이 필요하며 테스트는 locmem을 사용한다.

## 변경 파일

- 수정: `accounts/models.py` (프로필/약관 필드와 RefreshSession), `config/settings.py`
  (JWT/reset 만료·비밀번호 변경 무효화), `config/urls.py`, `.env.example`.
- 신규: `accounts/serializers.py`, `services.py`, `views.py`, `urls.py`, `test_api.py`.
- 신규 migration: `accounts/migrations/0003_user_agreements_user_name_user_nickname_user_phone_and_more.py`.
- 신규 격리 테스트 실행기: `scripts/run_auth_api_tests.py`.
- 문서: 이 문서 및 기존 실제 DB 이관 기록의 현재 코드 배포 조건 안내.

기존 accounts 0001/0002와 이메일 인증 0001의 내용은 해시로 불변을 확인했다.
기존 이메일 인증 코드·UserManager·Admin·공통 오류 처리·속도 제한을 재사용한다.
Refresh 토큰은 HMAC만 DB에 저장하며 JWT 원문은 저장하지 않는다.

## 실제 개발 DB에 필요한 추가 migration — 미실행

**개발 DB에는 이 작업에서 연결하지 않았으며 DDL/데이터/마이그레이션을 적용하지 않았다.**
새 API 코드는 아래 migration을 승인·적용하기 전 기존 개발 DB에 배포/서비스하면 안 된다.
이전의 15개 테이블/21개 migration 완료 기록은 User 전환 단계의 기록이다.

0003의 의존성은 accounts.0002_bridge_admin_user 하나다. 예상 변경:

1. accounts_user에 agreements(JSON, 기본 {}), name/nickname/phone(TEXT, 기본 빈 문자열) 추가.
2. accounts_refreshsession 테이블 하나 생성: user FK, unique token_digest, expires_at, revoked_at, created_at.
3. Django가 모델 ContentType/permission과 migration 적용 기록을 추가한다. 기존 테이블 삭제나
   기존 User 이메일/비밀번호/PK 변경은 없다. 추가 컬럼은 기존 행에도 기본값을 적용한다.
4. 현재 개발 DB 상태가 유지됐다면 적용 후 16개 테이블/22개 migration이 예상된다.

승인 후 사용할 명령(이번 작업에서는 실행하지 않았다):

```powershell
.\.venv\Scripts\python.exe manage.py migrate accounts 0003_user_agreements_user_name_user_nickname_user_phone_and_more --settings=config.settings --plan
# 계획이 위 0003 하나인지 확인하고, 쓰기 중지/새 백업과 복원 검증 후 승인된 단계에서만:
.\.venv\Scripts\python.exe manage.py migrate accounts 0003_user_agreements_user_name_user_nickname_user_phone_and_more --settings=config.settings --noinput
.\.venv\Scripts\python.exe manage.py check --settings=config.settings --database default
.\.venv\Scripts\python.exe manage.py makemigrations --settings=config.settings --check --dry-run
```

기존 User 이관용 inspect/verify 스크립트는 당시의 15개 테이블/21개 migration을 검증하는
증거 도구다. 새 API migration 이후의 배포 검사기로 그대로 재사용하지 않는다.

## 테스트와 재현

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.user_model_rehearsal --keepdb --noinput
.\.venv\Scripts\python.exe manage.py test accounts.test_preparation accounts.tests config email_verification.tests.AuthUnitTests --settings=config.user_model_preview --noinput
```

첫 명령은 별도 격리 서버와 전용 테스트 스키마/계정 및 환경변수가 준비된 경우에만 실행한다.
현재 설정은 127.0.0.1:33307, server_id=9133307을 요구한다. 준비 조건은
[개발 안내](AUTH_API.md)를 따른다. 개발 환경에 종속된 로컬 서버 생성/DB 운영 도구는 배포 코드에 포함하지 않는다.
그 서버의 전용 test_yippee_migration_suite에서만 migration과 전체 테스트를 실행한다.
--keepdb를 사용하고 DROP 권한은 주지 않으며 기존 DB를 재사용/삭제하지 않는다.
이전 격리 증거와 테스트 datadir는 보존한다. 완료 후 새 인스턴스만 정상 종료한다.
실제 yippee_club_db와 기존 test_yippee_club_db, team3_db에는 연결하지 않는다.

검증 항목: 전체 이메일 인증→가입, 미인증/만료/다른 이메일/소비된 토큰 거부, 중복 이메일,
비밀번호 규칙·해시·공백 보존, 가입 실패 원자성, 로그인 성공/실패/비활성, JWT 인증/갱신,
무효·만료·미등록 토큰, 로그아웃 후 재사용 거부 및 세션 분리, 프로필 소유권/권한 주입 거부,
조회·수정·null 지우기, 비밀번호 변경 후 기존 토큰 거부, 재설정 메일/만료/재사용 거부,
메일 오류 비노출 및 호출 제한. 최종 실행 결과는 아래 기록을 따른다.

테스트 추가 중 세션 만료 테스트에 로컬 변수 참조 오류 1건을 발견해 수정했다.
해당 실패 실행의 증거도 보존했으며 수정 후 전체 테스트를 다시 실행했다.

최종 결과:

- 격리 MySQL 전체 **72개 중 70개 통과, 오프라인 전용 검사 2개 skip, 실패 0개**.
  신규 API 테스트 28개와 기존 이메일 인증/Admin/JWT/마이그레이션 테스트를 포함한다.
- 오프라인 검증 34개 통과. 권한·격리 안전 스크립트 테스트 19개 통과.
- 격리 설정의 `check --database default`: 문제 없음.
- 격리 설정의 `makemigrations --check --dry-run`: No changes detected.
- 최종 증거: `.mysql-rehearsal/auth-api-cad00793f0c4/`의 test.txt/check.txt/makemigrations.txt/report.json.
  report.json에서 success=true와 isolated_server_shutdown=true를 확인했다.

## 아직 구현하지 않은 API

- 소셜 로그인·실명 인증: 0절에서 1차 핵심 범위 제외, 외부 공급자 계약 없음.
- 휴대전화 변경: 1차 이메일 인증만 지원하며 SMS 검증 계약/공급자가 없음.
- 회원 탈퇴: 개인정보·관련 데이터 삭제/보존 범위와 세션 폐기 정책이 미확정이다.
  자동 hard-delete/soft-delete 정책을 임의로 선택하지 않았다.
- 프로필 사진 업로드/삭제: 원문도 업로드 방식 제안 상태이며 파일 유형·크기·저장소/삭제 정책 미확정이다.

위 경로에는 성공을 가장하는 임시 뷰를 등록하지 않았다.
