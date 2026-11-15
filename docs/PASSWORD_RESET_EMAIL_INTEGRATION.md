# 비밀번호 재설정 이메일 버튼 연동

## 서버 설정 및 기존 계약

`PASSWORD_RESET_FRONTEND_URL`에 승인된 프론트엔드 재설정 페이지의 **고정 HTTPS URL**을 설정한다. 실제 주소가 확정되기 전에는 비워 둔다. `.env.example`의 예시 키만 추가했으며 로컬 `.env`와 Gmail 비밀정보는 변경하지 않았다.

URL에는 사용자명·비밀번호, query, fragment, 공백·제어문자·역슬래시를 넣지 않는다. URL이 없거나 유효하지 않으면 등록 여부에 관계없이 요청은 기존 오류 형식의 `500 INTERNAL_SERVER_ERROR`로 실패하며 메일을 보내지 않는다. 설정이 정상일 때 미가입 이메일 요청은 기존처럼 `200`이고 메일은 보내지 않는다.

요청의 Host·Origin·redirect_url·next 값은 링크 생성에 사용하지 않는다. `redirect_url` 등 추가 필드는 기존 StrictSerializer가 거부한다. 신뢰 대상은 배포 담당자가 설정한 URL 하나이며, 프론트 페이지도 임의 외부 주소로 리다이렉트하지 않아야 한다.

- 요청: `POST /api/v1/auth/password/reset-request`, JSON `{ "email": "사용자 이메일" }`
- 성공: `200`, `{ "message": "처리되었습니다." }`
- 이메일: HTML 버튼 **비밀번호 재설정하기**와 텍스트 대체 본문을 함께 발송한다. 비밀번호는 포함하지 않는다.
- 링크 형식: `https://승인된-프론트-주소/재설정-경로#reset_token=<URL 인코딩된 기존 토큰>`
- 확인: `POST /api/v1/auth/password/reset-confirm`, JSON `{ "reset_token": "추출한 토큰", "new_password": "사용자가 입력한 새 비밀번호" }`
- 성공: `200`, `{ "message": "처리되었습니다." }`

서명 토큰 생성·검증과 `PASSWORD_RESET_TIMEOUT` 만료 정책, 비밀번호 정책, 변경 후 토큰 재사용 거부 및 기존 refresh 세션 폐기는 그대로 유지한다. 이메일은 설정된 만료 초 수와 본인이 요청하지 않았다면 무시하라는 안내를 포함한다. 버튼 클릭(GET) 자체는 토큰을 소비하거나 비밀번호를 변경하지 않는다. 별도 migration은 없다.

## 프론트엔드 구현

1. 재설정 페이지를 인증 없이 열 수 있게 하고, 앱 초기화 시 `new URLSearchParams(window.location.hash.slice(1)).get('reset_token')`으로 토큰을 추출한다. `URLSearchParams`가 URL 디코딩하므로 다시 디코딩하지 않는다.
2. 토큰이 없거나 여러 개면 입력 폼 대신 안전한 오류 안내를 표시한다. 토큰은 메모리에만 보관하고 즉시 `history.replaceState(null, '', window.location.pathname)`으로 주소창 fragment를 제거한다. 새로고침으로 메모리가 사라지면 이메일 링크를 다시 열도록 안내한다.
3. 새 비밀번호와 확인 입력을 받고 일치 여부를 검사한 뒤 위 확인 API를 HTTPS JSON POST로 호출한다. 비밀번호·토큰·응답 JWT를 콘솔, 분석 이벤트, 오류 수집 도구에 기록하지 않는다.
4. 성공 시 메모리의 토큰과 비밀번호를 지우고 로그인 페이지로 안내한다. 기존 refresh 세션은 무효화되므로 다시 로그인한다. 만료·잘못된 토큰·재사용 오류는 새 요청 안내로 처리하고 자동 요청·재발송하지 않는다.

## URL 노출 보호

fragment는 일반 HTTP 요청·Referer에 전송되지 않지만 브라우저 기록, 화면 캡처, 복사, 확장 프로그램과 페이지 JavaScript에는 노출될 수 있다. 서버가 query를 기록하지 않는 것만으로 완전히 보호되는 것은 아니다.

- 페이지에 `Referrer-Policy: no-referrer`, `Cache-Control: no-store`를 설정하고 HTTPS를 사용한다.
- 토큰 추출·주소 제거 전 분석 SDK, 오류 수집, 세션 리플레이, 외부 스크립트·이미지·폰트 등을 실행하지 않는다. 재설정 페이지에는 이런 도구를 제외하는 것이 안전하다.
- 허용한 출처만 사용하는 CSP를 적용하고 XSS를 방지한다. 토큰을 DOM, HTML, query, localStorage/sessionStorage, 쿠키에 저장하지 않는다.
- 리버스 프록시·웹 서버·API 요청 로깅·오류 수집에서 요청 본문의 `reset_token`, `new_password`를 마스킹하거나 수집하지 않는다.
- 프론트 라우터가 fragment를 별도 해시 라우팅에 사용하면 이 전달 계약과 충돌한다. 승인된 페이지는 pathname 기반 경로를 사용하도록 사전 합의한다.
- 이메일 보안 게이트웨이의 링크 재작성으로 fragment가 보존되는지는 프론트 주소 확정 후 별도 실제 수신 테스트로 확인한다. 이번 검증은 실제 Gmail을 발송하지 않는다.

## 격리 검증 결과

2026-11-15: 새 datadir `reset-button-tests-c32227d09376`에서 `accounts.test_api.AccountAPITests` **31개 모두 통과**, 27.269초. 메일은 locmem 백엔드로만 처리했다. 전체 회귀 테스트는 재실행하지 않았다.

HTML 버튼·동일 텍스트 URL·UTF-8 multipart/alternative, URL 미설정·비HTTPS·자격정보·query/fragment·제어문자·역슬래시 거부, 요청자 redirect_url 거부, 기존 확인 API의 토큰 호환성·만료·재사용 거부·이전 비밀번호 거부·refresh 무효화를 검증했다. 기존 계정 API 검사도 통과했다.

격리 system check는 오류 없음, `makemigrations --check --dry-run`은 `No changes detected`다. 기준 개발 DB에는 접속하지 않았고 실제 SMTP 발송도 없었다. `.env`와 미추적 감사 문서의 SHA-256은 실행 전후 동일하다. 증거는 `.mysql-rehearsal/reset-button-tests-c32227d09376/`에 보존했다.
