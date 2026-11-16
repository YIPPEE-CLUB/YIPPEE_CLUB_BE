# 핵심 API 계약 정합성 수정 및 최신 감사

2026-11-15. 기존 모델·migration·개발 DB를 변경하지 않고 API 20/23의 승인 보완계약을 공식 명세에 반영하고, 37번의 인증 계약을 사용자 선택에 따라 공개 조회로 통일했다. Git stage/commit/push/PR/merge는 수행하지 않았다.

## 기준 및 판단

- dev HEAD `7618a59dd4b1f5dc69ffbcfaf82cb9f84650fa24`, 원격 dev 동일.
- 원격 main `54c8d02`는 커밋 3개 앞서지만 git diff HEAD origin/main의 파일 차이는 없다. 로컬 소스는 최신 병합 내용과 같아서 fetch로 참조만 확인하고 checkout/merge/fast-forward는 하지 않았다. 브랜치 이력을 임의로 바꾸지 않았다.
- 기존 미추적 API_V1_5_IMPLEMENTATION_AUDIT.md는 원문 바이트를 별도 보존하고 최신 결과만 끝에 추가했다.
- CHILD_API_IMPLEMENTATION.md에는 정수 Category ID, results 배열, name/birth_date null 거부 및 gender/interests null 초기화가 **과거 사용자에게 승인된 보완계약**으로 기록돼 있다. 새 정책을 임의로 만든 것이 아니므로 기존 정상 코드를 보존하고 명세를 동기화했다.
- 37번은 과거 JWT 요구와 공식 공개 명세 사이 우선순위를 사용자가 다시 결정했다. 답변은 **공개 조회, 유효 JWT 200, 잘못된 JWT 401 유지**다. 개인정보 없는 공통 id/name 목록이고 공개 활동지 목록/상세와 일관되는 근거도 확인했다.

## 변경 전후

| API | 변경 전 | 변경 후 |
|---|---|---|
| 20 GET children | 공식 명세는 단일 객체, 실제는 results 배열 | 코드는 보존. 두 명세 모두 results 배열·빈 []·본인만·id 오름차순·JWT 필수로 동기화 |
| 23 PATCH children/{child_id} | 원문 name/birth_date nullable, 코드는 400 | 코드는 보존. 선택/non-null name·birth_date, 생략 유지, gender/null→빈 문자열, interests/null 또는 []→빈 배열, 생략 유지로 명세 동기화 |
| 37 GET activity-categories | 공식 공개·실제 JWT 필수 | AllowAny로 공개 조회. 기존 JWTAuthentication은 유지해 제공된 무효/만료 토큰 401. 공통 id/name·id 오름차순 유지 |

아이 PATCH의 유효하지 않은 타입/중복·없는 카테고리 400, 타인 아이 404와 atomic rollback도 보존했다. interests를 생략한 요청이 의도치 않게 기존 값을 비우지 않는지, []는 실제로 비우는지 추가 검사했다. 공개 카테고리 변경으로 아이·프로필·장바구니·선택 API의 인증을 약화시키지 않았다. 카테고리 쓰기 API도 추가하지 않았으며 POST는 405다.

## 현재 선택 아이 조회 검토

2026-11-16 승인 보완: 16번 GET /api/v1/users/me 응답에 필수 nullable integer `active_child_id`를 추가했다. 기존 User.active_child FK를 읽으며 미선택 또는 선택 아이 삭제 후에는 null을 반환한다. JWT로 인증한 본인의 선택만 조회한다. GET 전용 serializer를 사용하므로 로그인 user 및 프로필 PATCH의 id/email/phone/name 응답과 PUT 25번 계약은 유지한다. 새 모델·컬럼·migration은 없으며 나머지 98개 API 계약은 변경하지 않았다.

## 최신 분류와 한계

기존 99개 설계 목록은 유지한다. 현재 URL/HTTP 메서드/View/Serializer/모델/Permission/테스트를 재대조한 표는 감사 문서의 추가 절에 있다.

- A 구현 완료 27, B 보완 필요 0, C 후속 개발 47, D 현재 개발 제외 25, 합계 99.
- 현재 1차 필수 분모 24개: 01/02/05/06/07/09/10/16/17/20~25/27/28/37/41~46.
- 필수 완료 24개, 계약 기준 **100%**. 인증 보조 11/12/13도 완료지만 필수 분모에 임의 포함하지 않는다.
- D는 원문의 우선 제외 59~66/74/75/78 및 무료 서비스에서 현재 제외한 구매/권한 발급/주문·결제·환불·카드 39/40/47~58이다. 원문 후속 설계를 삭제하거나 영구 폐기한다는 뜻은 아니며 재도입은 별도 승인·정책이 필요하다. 소셜/실명인증 등 원문이 후속으로 둔 기능은 C로 유지한다.
- PurchaseEntitlement 모델/테이블은 과거 기록 보존 구조이며 API 구현 완료 건수에 추가하지 않는다.
- **계약 완료율은 운영 배포 완료율이 아니다.** 실제 SMTP 전달/재설정 UX, Python 3.12 검증 및 운영 파일/로그/보안 설정 검증은 남아 있다.

## 실행 검증

새 MySQL 인스턴스 `.mysql-rehearsal/cart-tests-808e621197c8/`에서 **173개 중 171개 통과·실패/오류 0·기존 preview 전용 2개 제외**, 39.857초다. 기준선 170개에 공개 카테고리 계약·명시적 빈 관심사/생략·잘못된 PATCH 타입 검증 3개를 추가했다. 기존 무토큰 아이 보호 테스트는 유지하면서 공개로 바뀐 카테고리의 기대만 분리했다. 실패 테스트를 삭제하거나 숨기지 않았다.

아이 목록/빈 목록/소유권/JWT, PATCH null/생략/관심사 교체/[]/비정상 타입/없는 카테고리/타인 거부, 공개·유효/무효/만료 JWT 카테고리, 아이 선택/삭제 및 무료 장바구니 17개, 기존 인증/메일/활동지·파일/Admin/찜 회귀를 함께 실제 실행했다. 실제 SMTP나 PG를 실행한 것은 아니다.

격리 check와 makemigrations --check --dry-run은 통과했다. 기존 공유 테스트 DB/datadir 재사용 없이 새 port 33307/server_id 9133307을 검증한 인스턴스에서만 쓰기 테스트를 수행하고 종료했다. 개발 DB 읽기 전용 전후 비교와 명세 파싱 결과는 최종 검증 후 이 문서에 추가 기록한다.

## 변경 파일 및 다음 작업

- categories/views.py: AllowAny, 제공된 JWT 검증 유지.
- children/tests.py: 기존 보호 검사 보존, 공개 카테고리 및 PATCH 검사 추가.
- docs/API_SPEC_v1.5.md, docs/openapi_v1.5.yaml: 20/23/37 및 이미 승인된 카테고리 식별자 보완계약 동기화. 다른 API의 경로/구조 보존.
- docs/CHILD_API_IMPLEMENTATION.md: 과거 이력을 유지하며 최신 정책 안내 추가.
- docs/API_V1_5_IMPLEMENTATION_AUDIT.md: 기존 내용 보존·99개 최신 재분류/근거 추가, 미추적 유지.
- docs/API_CONTRACT_ALIGNMENT_UPDATE.md: 본 결과 문서.

우선순위는 선택 상태 조회 계약의 프론트 협의, 실제 SMTP/재설정 UX 통합 검증, Python 3.12 및 공식 계약 CI, 그다음 필요한 검색/콘텐츠 등 C 기능 범위 협의다. 99개 전체 개발이나 결제 모델 변경은 이번 범위가 아니다.


## 2026-11-15 중단 작업 최종 검증 완료

복구 후 이번 단계에서는 OpenAPI 아이 목록 스키마와 본 최종 결과만 보완했다. 실제 API Python 코드·테스트 코드는 수정하지 않았으며, 전체 99개 재감사와 173개 회귀 재실행은 하지 않았다.

- **OpenAPI 보완:** GET /children의 results.items를 ChildReadSerializer 및 기존 통과 테스트와 대조해 id(integer), name(string), birth_date(string/date), gender(string), interests(integer 배열)로 완성했다. 다섯 필드 모두 required·non-null이며 빈 gender 문자열과 빈 interests 배열을 허용한다.
- **명세 검증 PASS:** 중단된 validate_contract_alignment.py는 Git show 읽기와 YAML 비교/assert만 수행하며 DB 접근·파일 삭제·Git 변경은 없다. 원본 파일은 보존하고, 이번에 승인된 interests.items 정수형 보완만 기대값에 추가해 메모리에서 실행했다. YAML 파싱, 유일 operationId 99개, 20/23/37 이외 96개 작업 불변, children JWT 필수 및 categories 공개 설정 검증을 통과했다. 스키마 필드·required·자료형도 별도로 확인했다.
- **DB 보존 PASS:** 기존 contract-audit-f6c90bc15a0a/before.json과 새 after.json의 전체 스냅샷이 동일하다. 전체 테이블의 SHOW CREATE TABLE(인덱스·제약 포함), 컬럼 메타데이터, FK, 행 수·전체 행 SHA-256 및 migration 이력까지 일치한다. 테이블 25개, migration 29개, 활동지 4개, 카테고리 2개를 유지한다. source()와 snapshot()의 읽기 전용 세션 및 Django SELECT/SHOW 전용 가드로 비교했으며 DB 데이터·DDL·migration 쓰기는 없다.
- **파일 보존 PASS:** private_files/sample_files 전체 인벤토리·해시, migration_hashes 및 protected.json의 migration/.env 해시가 모두 일치한다. 기존 감사 원문 audit-prefix.bin은 현재 문서 앞부분에 바이트 그대로 보존되어 있다.
- **분류·완료율:** 기존 최신 99개 표의 번호 중복·누락, 집계, 필수 집합과 기존 회귀 증거를 검증했다. A 27 / B 0 / C 47 / D 25 = 99이며, 현재 확정 계약의 1차 필수는 24/24, **100%**로 확정한다. 이는 기존 코드 감사·통과 증거 및 이번 잔여 명세 검증에 근거하며 새 전수 감사나 운영 준비 완료 판정은 아니다.
- **회귀 증거 재사용:** cart-tests-808e621197c8/report.json·test.txt·server.log를 확인하고 해시를 기록했다. 기존 결과는 173개 실행 중 171 통과·2 제외·실패/오류 0, 39.857초이며 격리 서버 정상 종료를 확인했다. 이번에 테스트·check·makemigrations를 재실행하거나 기존 테스트 DB를 열지 않았다.
- **최종 증거:** `.mysql-rehearsal/contract-final-9d901247d935/after.json`, `final-validation.json`, `inputs.json`. YAML 라이브러리와 기존 보호 증거의 접근 권한 차이 때문에 명세 검증 결과는 `contract-final-29357c964fd4/final-validation.json`에서 가져오되, 입력 파일 SHA-256 불변을 재확인했다. 해당 중간 실행은 DB 비교 전 권한 오류로 종료했으며 최종 결합 검증은 성공했다. 실패·중간 실행 증거도 삭제하지 않았다.
- **범위 종료:** Git stage/commit/push/merge, 신규 기능 개발, 코드 리팩터링, DB 쓰기·migration은 하지 않았다. 선택 상태 GET 계약, 실제 SMTP/재설정 UX, Python 3.12 CI 및 운영 설정 검증은 기존 후속 과제로 남긴다. 다음 개발 단계로 진행하지 않았다.
