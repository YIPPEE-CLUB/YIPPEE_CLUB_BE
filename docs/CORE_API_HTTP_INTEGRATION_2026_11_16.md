# 2026-11-16 핵심 API HTTP 통합 검증

## 기준과 보존

- dev HEAD: `6e102eb5b6d85745c77070684fa4321f63078220`.
- 직전 선택 아이 GET 구현의 수정 6개, 미추적 테스트 및 기존 감사 문서를 포함해 작업 전 파일 해시를 기록했다. 검증 후 기존 파일 변경은 0개다.
- Python 3.13.3, MySQL 신규 datadir, Django LiveServerTestCase WSGI 서버를 사용했다. urllib가 loopback TCP로 요청하며 APIClient는 사용하지 않는다.
- MySQL 서버 ID/포트/datadir를 확인한 뒤 신규 DB만 생성했다. HTTP worker의 thread-local DB 연결에도 기존 SQL guard를 적용했다.
- locmem 이메일 백엔드와 임시 활동지 저장소만 사용했다. 실제 SMTP, 개발 DB, 공유 테스트 DB, 실제 업로드 저장소는 쓰지 않았다.

## 실행과 결과

검증 실행기:

```powershell
.\.venv\Scripts\python.exe .mysql-rehearsal\http-integration-789638e03bd4\run_validation.py
```

실행기는 기존 `scripts/run_fresh_feature_tests.py`를 기반으로 새 검증 경로에 작성했다. 매 실행마다 별도의 신규 MySQL datadir를 만들며 기존 보존 자료는 재사용하지 않는다.

아래 Django 명령은 모두 `.venv\Scripts\python.exe manage.py` 및 `--settings=config.user_model_rehearsal`로 실행했다. 격리 DB 환경변수는 실행기에서만 설정했고 인증 정보는 출력하지 않았다.

| 명령 | 결과 |
|---|---|
| `check --database default` | 정상 |
| `makemigrations --check --dry-run` | 변경 없음 |
| `test accounts.test_http_integration --noinput -v 2` | 2 통과, 0 실패, 0 제외 |
| `test --noinput -v 2` | 183 통과, 0 실패, 2 제외 (총 185) |

제외 2개는 기존 preview 전용 SQL 차단 테스트다. HTTP 시나리오는 단독 실행과 전체 회귀에 각각 포함되므로 통과 수를 합산하지 않는다.

| HTTP 흐름 | 단독 요청 수 | 결과 |
|---|---:|---|
| 인증·계정·아이 관리 및 선택 | 54 | 모두 기대 상태 코드 및 시나리오 검증 통과 |
| 카테고리·활동지·샘플 다운로드·찜·장바구니 | 67 | 모두 통과 |
| 합계 | 121 | 실패 0, 제외 0 |

전체 회귀에서 동일한 121건을 다시 실행했다. 두 실행의 실제 HTTP 요청은 총 242건이다. 오류를 의도한 요청의 400/401/404/409도 기대 결과에 맞으면 통과로 계산한다. 저장한 HTTP 메타데이터에는 토큰·비밀번호·인증번호·메일 본문이 없다.

인증 흐름은 이메일 중복 확인, 메모리 메일의 인증번호 확인, 가입, 로그인, JWT 프로필 조회, refresh 및 발급 access 사용, 프로필 PATCH, 비밀번호 변경, 이전 비밀번호/refresh 거부, logout 및 폐기 refresh 거부, 비밀번호 재설정 발급·소비·재사용 거부를 포함한다.

아이 흐름은 A/B 생성·목록·수정, 선택 및 전환, 새 HTTP opener와 새 로그인 JWT를 통한 복원, 미선택/선택 아이 삭제, null 복원, 타인 GET/PATCH/DELETE 차단 및 선택 거부를 포함한다.

활동지 흐름은 공개 목록·상세, 키워드·카테고리·연령·난이도·시간 필터, 5종 정렬, 페이지 이동, 오류 쿼리, 비공개 상세/파일 차단을 검증한다. 저장소의 샘플 PDF 4개·PNG 4개를 읽어 임시 저장소에 복사하고 HTTP 다운로드 8건의 SHA-256을 원본과 비교했다. 개발 DB의 기존 샘플 레코드는 조회·수정하지 않았다.

찜·장바구니는 추가·조회·중복 409·비공개 추가 거부·삭제·타인 목록 격리 및 삭제 404를 확인했다. 장바구니 합계는 0원이다.

## API 계약

- PyYAML 6.0.3을 이번 검증 전용 `yaml-vendor` 경로에 설치했다. 기존 가상환경 패키지는 변경하지 않았다.
- OpenAPI YAML 파싱 성공, operationId 99개 및 경로/메서드 매핑 유지.
- 16번 GET의 `active_child_id`: required, integer, nullable=true.
- 위 필드 정의·required 항목·예시를 제외한 파싱 결과가 기존 HEAD와 완전히 같다.
- HTTP 테스트는 응답 상태, JSON content type, 객체 구조, 주요 성공 응답 키, 공통 오류 envelope, 인증 및 소유권과 시나리오 값을 검증한다. 전체 OpenAPI schema를 자동 검증하는 범용 validator는 사용하지 않았다.

## 증거와 한계

- 준비·해시·YAML 결과: `.mysql-rehearsal/http-integration-789638e03bd4/`.
- 격리 MySQL·명령 로그·HTTP 메타데이터·종료 결과: `.mysql-rehearsal/http-integration-mysql-dfdfcfd141d2/`.
- report.json: success=true, development_database_accessed=false, existing_test_database_reused=false, isolated_server_shutdown=true.
- WSGI HTTP 서버도 테스트 종료 시 정리됐다. 새 결과 자료와 datadir는 보존했다.
- 발견한 API 결함은 없으며 애플리케이션 코드·계약·migration은 변경하지 않았다. 새 HTTP 테스트와 이 보고서만 추가했다.
- Python 3.12는 기존 환경에서 확인되지 않아 미검증이다. 임의 설치하지 않았다.
- 실제 SMTP 전달, 외부 도메인/TLS/reverse proxy, 운영 서버 및 ASGI 경로는 이번 검증 범위가 아니다.
- 11월 18일까지의 후속 검토 항목은 프론트 연동, 준비된 Python 3.12 환경에서 호환성 확인, 별도 승인 범위의 운영 검증이다. 이번 작업에서 시작하지 않았다.
