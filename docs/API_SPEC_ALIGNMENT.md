# v1.5 명세 원본 및 기존 인증 API 비교

앞으로 API 구현의 기준 파일은 저장소의 다음 두 파일이다.

- [API_SPEC_v1.5.md](API_SPEC_v1.5.md)
- [openapi_v1.5.yaml](openapi_v1.5.yaml)

Markdown 0절의 확정 정책을 뒤의 예시/제안 및 OpenAPI의 이전 선택/nullable 표기보다 우선한다.
원본에 남아 있는 미확정 사항을 이 복사 작업에서 확정하거나 수정하지 않았다.

## 출처 및 바이트 일치 검증

Downloads에는 Markdown 후보가 두 개 있었다. URL 인코딩된 파일명 사본은 2026-11-06 수정본,
한글 파일명 원본은 2026-11-11 수정본이었다. 기존 인증 구현에서 참조했던 더 최근의 한글 파일명
원본을 선택했다. OpenAPI YAML 후보는 하나였다. 대상 경로에는 기존 파일이 없었으며,
텍스트 재저장 없이 파일 복사했다. Downloads 원본은 수정/삭제하지 않았다.

| 저장소 경로 | Downloads 원본 파일명 | 크기(bytes) | SHA256 (원본=복사본) |
|---|---|---:|---|
| docs/API_SPEC_v1.5.md | YIPPEE_CLUB_API_팀공유용_최종명세서_v1.5.md | 157396 | `2913f1932bfa125682f65f7e9c03f1bce1ea824236c3b0c5fa9e0824c9eb6c8a` |
| docs/openapi_v1.5.yaml | YIPPEE_CLUB_OpenAPI_v1.5.yaml | 213665 | `db121ab91d171d92138c11e3bc2bdd2f014a5f034c77075bd59f47e322fd21e6` |

## 기존 구현과 비교

DB 연결을 차단한 설정으로 URL resolver와 실제 serializer 필드를 확인하고,
복사된 OpenAPI 및 기존 view/service의 성공 응답 구성을 정적으로 비교했다.
아래 12개 구현된 operation의 URL/HTTP method/요청 필드/성공 응답 필드가 일치했다.
이 작업에서 실제 HTTP 호출이나 DB 통합 테스트를 다시 실행하지 않았다.

| Method | URL (/api/v1 기준) | 요청 body | 성공 응답 |
|---|---|---|---|
| POST | /auth/identifiers/check | identifier | registered, identifier_type |
| POST | /auth/verification/send | identifier, purpose | verification_id, expires_in_seconds |
| POST | /auth/verification/confirm | verification_id, code | verification_token, verified |
| POST | /auth/signup | identifier, verification_token, password, agreements | user_id, access_token, refresh_token |
| POST | /auth/login | email, password | access_token, refresh_token, user |
| POST | /auth/token/refresh | refresh_token | access_token, refresh_token |
| POST | /auth/logout | refresh_token (선택/null 허용) | message |
| POST | /auth/password/reset-request | email | message |
| POST | /auth/password/reset-confirm | reset_token, new_password | message |
| GET | /users/me | 없음 | id, email, phone, name |
| PATCH | /users/me | name, nickname (선택/null 허용) | id, email, phone, name |
| PATCH | /users/me/password | current_password, new_password | message |

검토가 필요한 원문/구현의 정책 사항은 다음과 같다. 이번 작업에서는 API 코드를 변경하지 않았다.

- 가입 password는 YAML/상세 표에서 선택·nullable이지만 Markdown 0절과 API 06의 확정 설명에서
  필수다. 현재 코드는 확정 설명대로 필수/non-null로 처리한다.
- 로그인 user는 원문에 내부 필드 정의가 없다. 현재 코드는 내 프로필의 id/email/phone/name을 재사용한다.
- agreements 내부 키/필수 동의/버전은 원문에 없다. 현재 코드는 필수 object 검사와 원문 저장만 한다.
- 로그아웃 토큰 생략/null의 폐기 범위는 원문에 없다. 현재 코드는 제공된 토큰만 폐기한다.
- PATCH 프로필의 null은 빈 문자열로 지우며 GET의 non-null 문자열 응답을 유지한다.
- JWT 수명/회전 등 미확정 정책의 구현 기본값과 미구현 API 목록은
  [인증 API 구현 기록](AUTH_API_IMPLEMENTATION.md)을 따른다.

미구현 경로가 포함된 99개 전체 API를 모두 구현/검증했다는 의미는 아니다.
DB/migration/모델/API 코드/원본 명세 두 파일의 내용은 이 문서화 작업에서 변경하지 않았다.
