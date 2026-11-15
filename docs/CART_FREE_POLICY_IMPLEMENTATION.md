# 무료 장바구니 정책 적용 및 검증

> 후속 명세 동기화: 공식 Markdown/OpenAPI의 0절 및 장바구니 44~46번을 무료 정책에 맞췄다. 아래 원본 미수정 설명은 최초 기능 구현 단계의 기록이며, 다른 API와 기존 스키마는 보존했다.

2026-11-15. 모든 활동지를 무료로 제공한다는 사용자 확정 정책에 따라 기존 장바구니 API에서 구매 권한 의존성만 제거했다. 기존 구매 권한 기록을 미구매로 판정하거나 수정/삭제하지 않는다. 결제·주문·PG·환불 기능은 추가하지 않았다.

## 시작 상태와 원격 관계

- 브랜치 dev, 분석 시작 HEAD `0d9f513e19d4a0b4f9e0708168a2e3c774f3eacc`.
- 기존 미추적 `docs/API_V1_5_IMPLEMENTATION_AUDIT.md`를 보존한다.
- 원격 dev도 같은 SHA다. 최신 main은 `3e9f2eda507ef81d2deff5ce7b22ecde48176757`이며 GitHub compare에서 ahead 2/behind 0/files=[]로 소스 차이가 없다. 로컬 origin/main 캐시의 과거 SHA와 구분해 기록한다. fetch/checkout/merge로 작업 트리를 바꿀 필요가 없어 수행하지 않았다.
- 개발 DB는 읽기 전용으로 사전 전체 스키마/행 해시/FK·migration·파일·공개 목록 응답을 기록했다. 테이블 25개·migration 29개를 확인했다. 이 기준과 작업 후 상태를 비교한다.

## 기존 503 원인과 최소 변경

기존 `CartCreateView.post`는 JWT/입력 검증 후 `CART_PURCHASE_ENTITLEMENTS_VERIFIED=False`이면 무조건 503 SERVICE_UNAVAILABLE를 반환했다. True로 가정한 경우에도 본인 active PurchaseEntitlement가 있으면 409 ALREADY_PURCHASED로 거부했다. 이는 당시 구매 정책/미이관 데이터 보호 목적이었으나 새 무료 정책에서는 정상 추가를 막는다.

다음 부분만 제거했다.

1. 구매 검증 플래그에 의한 503 분기.
2. PurchaseEntitlement 조회 및 ALREADY_PURCHASED 분기.
3. View의 불필요한 settings/PurchaseEntitlement import.

활동지 공개 검사 → Activity select_for_update → CartItem.get_or_create는 기존 atomic 안에서 유지했다. 같은 활동지에 대한 추가/공개 취소·삭제 경합과 동시 중복을 기존 방식으로 보호하며 DB 사용자/활동지 UNIQUE도 그대로다. API 경로·Serializer·소유권·성공/기존 오류 형식은 바꾸지 않았다.

새 무료 정책 분기 플래그를 만들지 않았다. **기존 CART_PURCHASE_ENTITLEMENTS_VERIFIED=False는 그대로**이며 이제 무료 장바구니 추가의 조건으로 읽지 않는다. 다른 격리 설정의 안전 검사 등은 변경하지 않았다.

## API 계약과 예시

세 API 모두 JWT Bearer access token이 필수다. 로그인 사용자는 request.user에서만 결정한다.

| API | 동작/성공 |
|---|---|
| GET /api/v1/cart | 본인의 공개 활동지만 기존 최근 등록순·ActivitySerializer로 반환, 200 |
| POST /api/v1/cart/items | 본인의 공개 무료 활동지 추가, 201 |
| DELETE /api/v1/cart/items/{activity_id} | 본인의 장바구니 관계만 삭제, 204, 본문 없음 |

POST 요청 및 응답:

```json
{"activity_id": 1}
```

```json
{"activity_id": 1, "message": "처리되었습니다."}
```

빈 GET 응답:

```json
{"items": [], "total_amount": 0}
```

항목이 있으면 items는 기존 ActivitySerializer 필드(id/title/price/sale_status/description/연령/난이도/시간/categories/image/pdf)를 그대로 사용한다. 각 항목의 price와 total_amount는 0이다. 합계 계산 코드를 0으로 하드코딩하지 않고 **DB 가격 합산을 유지**했다. 기존 Activity의 price 기본값·validator·`activity_price_zero` DB CHECK가 0원만 허용하며 해당 모델/제약은 수정하지 않았다. 클라이언트 price/total_amount 입력은 기존 StrictSerializer가 거부한다.

비공개로 전환된 항목은 관계와 원본을 보존하고 GET items/합계에서 제외한다. 본인은 해당 관계를 DELETE할 수 있다. 다시 공개되면 기존 관계가 목록에 표시되며 중복 추가는 409다.

| 조건 | HTTP / code |
|---|---|
| JWT 누락·무효·만료·refresh 오사용 | 401 AUTHENTICATION_REQUIRED |
| activity_id 누락/null/bool/문자열/실수/범위 오류·알 수 없는 입력 필드 | 400 VALIDATION_ERROR |
| 없는/비공개 활동지 추가 | 400 VALIDATION_ERROR, 기존 공개 검증 유지 |
| 본인 장바구니에 이미 존재 | 409 INVALID_STATE |
| 삭제 대상이 없거나 타인에게만 존재 | 404 NOT_FOUND |
| 정상 공개 무료 활동지 추가 | 201, 구매 검증용 503 없음 |

오류 envelope는 기존 code/message/details/request_id다. 새 변경은 다른 장애까지 영구적으로 503/500이 없어진다는 의미가 아니라 **구매 연동 상태에 따른 의도적 차단을 제거**한 것이다.

## 원본 v1.5 명세와의 차이 및 구매 데이터 보존

원본 Markdown/OpenAPI를 재작성하지 않았다. 새 사용자 확정 무료 정책이 다음 과거 규칙을 대체한다.

| 원본 위치/기록 | 과거 | 현재 무료 정책 |
|---|---|---|
| API_SPEC_v1.5.md 0-1/0-2/0-3, 45번 | 유효 구매 권한이 있으면 담기 금지, ALREADY_PURCHASED 제안 | 구매 권한 유무와 무관하게 공개 활동지 추가 가능 |
| openapi_v1.5.yaml api45_post description | 같은 구매 차단 규칙 설명 | 적용하지 않음. 경로/요청/201 응답/중복 409는 유지 |
| CART_API_IMPLEMENTATION의 최초 안전 정책 | 구매 데이터 연결 확인 전 503 | 무료 장바구니에서는 플래그와 권한 조회를 사용하지 않음 |

PurchaseEntitlement 모델/테이블·migration·User/Activity PROTECT·UNIQUE·상태 CHECK는 모두 그대로다. active/revoked 기록이 있어도 무료 추가를 허용하며 장바구니 요청에서 권한 행을 조회하거나 변경하지 않는다. 새 코드에서 구매 상태를 변환하거나 권한 행을 만들어 주지도 않는다.

실행 코드 검색 결과, 제거한 장바구니 조회 외에 PurchaseEntitlement를 사용하는 곳은 모델/migration 및 기존 관련 테스트였다. 아이 선택 테스트에서도 구매 권한 보존을 검증한다. 설정/격리 배포 도구의 플래그·과거 정책 기록은 삭제하지 않았다. 향후 결제나 유료 서비스를 도입한다면 이번 무료 계약과 별도로 정책/설계/테스트가 필요하다.

## 변경 파일 및 DB 범위

- cart/views.py: 구매용 503/권한 차단 제거, 잠금/중복/공개/소유권 정책 유지.
- cart/tests.py: 기본 False 상태에서 무료 추가·기존 권한 기록 보존을 검증하도록 수정, 구매 테이블 미조회 검사 추가.
- docs/CART_API_IMPLEMENTATION.md: 과거 기록을 보존하면서 현재 무료 정책 문서 링크 추가.
- docs/CART_FREE_POLICY_IMPLEMENTATION.md: 본 문서.

신규/기존 migration, 모델·테이블·컬럼·가격 제약·실제 .env·config/settings.py는 변경하지 않았다. 개발 DB는 읽기만 하며 새 데이터·스키마 변경·테스트 계정 생성·API 쓰기를 수행하지 않는다. 감사 문서와 이전 DB 적용/구현 기록도 보존한다. Git stage/commit/push/PR/merge는 수행하지 않는다.

## 검증

기존 새 인스턴스 실행기 `.venv/Scripts/python.exe -B scripts/run_fresh_feature_tests.py`를 사용한다. 새 datadir·별도 MySQL port 33307/server_id 9133307 신원을 확인한 후 새 테스트 스키마에서만 쓰기/migration/테스트를 수행하며 기존 테스트 DB를 재사용하지 않는다. 개발 DB에는 migrate/flush/fake/테스트 데이터 변경을 하지 않는다.

기준선은 169개 중 167개 통과·기존 preview 전용 2개 제외다. 기존 테스트의 ‘구매 시 409/플래그 False 시 503’ 기대를 새 정책에 맞게 바꾸고 다음을 검증한다.

- False 상태에서 정상 추가 201, 정상 조회 200·가격/합계 0, 삭제 204.
- 엄격한 ID/추가 필드·없는/비공개·JWT 검증, 본인 관계만 조회/삭제, 타인 관계 보존.
- 동일 항목 409, 동시 요청 201/409와 관계 행 1개.
- active 권한 보유자도 추가 가능, 중복/조회/삭제 후 권한의 모든 필드 동일. revoked 기록도 보존.
- 장바구니 추가/조회/삭제 SQL에 purchase_entitlements 조회가 없음.
- 기존 가격 0원 제약/권한 제약 및 인증·아이 선택·아이 CRUD·활동지·파일·Admin·찜 회귀.

### 실제 실행 결과

새 격리 실행 증거: `.mysql-rehearsal/cart-tests-e098691b4ce6/`.

| 항목 | 결과 |
|---|---|
| 전체 회귀 재실행 | **170개 중 168 통과, 실패/오류 0, 기존 preview 전용 2개 제외**, 37.543초 |
| 장바구니 | **17개 모두 통과**, 위 결과에 포함 |
| API 44 | JWT·본인 공개 목록·기존 응답/정렬·price/total_amount=0 통과 |
| API 45 | False 상태 201·중복409·입력/없는/비공개400·무효 인증401·동시201/409·단일 관계 행 통과 |
| API 46 | 204·본인만 삭제·타인/없는 관계404·원본/권한 보존 통과 |
| 구매 권한 | active/revoked 행 보존 및 장바구니 3개 처리 중 권한 테이블 미조회 통과 |
| Django system check | 격리 DB와 개발 설정 모두 오류 없음 |
| migration 정합성 | 충돌 없음·기존 이력 일관, makemigrations --check --dry-run: No changes detected |
| DB 변경 | 새 migration 없음, 개발 DB 테이블 25개·적용 migration 29개·미적용 없음 유지 |
| 격리 종료 | 새 테스트 스키마 제거·격리 서버 정상 종료, 기존 테스트 DB 재사용 없음 |

기존 169개 기준선에서 과거 구매 차단 기대를 무료 계약으로 수정하고 SQL 비의존 검사 1개를 추가해 총 170개가 됐다. 나머지 인증/아이 선택/아이 CRUD/활동지/파일/Admin/찜 회귀도 함께 실제 재실행했다. 이전 테스트 기록을 이번 결과로 재사용하지 않았다.

개발 DB 읽기 전용 전후 증거: `.mysql-rehearsal/free-cart-validation-2fe6efc6a5fe/before.json`, `after.json`, `protected-hashes.json`.

- **전체 개발 DB 스키마/컬럼/FK/인덱스/행 수·해시/migration 이력과 공개 활동지 응답이 전후 동일**했다. PurchaseEntitlement 테이블도 같은 비교에 포함된다.
- 활동지 4개·카테고리 2개, private 저장 파일 20개·원본 자료 8개의 해시/집합을 보존했다.
- 기존 migration 전부·.env·미추적 전수 감사 보고서의 바이트 해시는 동일했다. 실제 .env를 출력하거나 변경하지 않았다.
- 테스트 실행기의 report.json에서 success=true, development_database_accessed=false, existing_test_database_reused=false, isolated_server_shutdown=true를 확인했다. 이 플래그는 테스트 실행기에 대한 것이며, 별도의 전후 검증은 개발 DB에 읽기 전용으로 접속했다.
- 보존 증거/로그/자격증명은 기존 Git 제외 디렉터리에만 있다. 실제 백업·데이터·PDF/이미지를 Git에 추가하지 않았다.

이번 실행은 로컬 Python 3.13.3/Django 5.2.19/MySQL 8.0.46 기준이며 Python 3.12 검증을 대신하지 않는다. 실패한 검증이나 미해결 코드 오류는 없다.

## 프론트엔드 주의사항 및 남은 사항

POST 경로/JSON/201 응답은 동일하다. 이제 구매 연동 준비 상태나 권한 유무 때문에 무료 추가를 비활성화할 필요가 없다. 로그인은 필요하며 중복은 계속 409 INVALID_STATE다. 삭제 경로에는 cart_item_id가 아니라 **activity_id**를 전달한다. 비공개 항목은 목록에서 숨지만 삭제는 가능하다.

현재 확정 무료 정책의 미결정 사항은 없다. 후속 승인으로 공식 명세의 구매 차단 설명을 무료 계약에 동기화했다. 원본의 다른 API·번호·필드 구조는 유지했다. Python 3.12 CI 검증은 별도 과제다(로컬 3.13.3). 이번 Git 반영은 사용자가 조건부 승인했으며 실제 배포와 DB 변경은 포함하지 않는다. DB migration은 필요 없다.
