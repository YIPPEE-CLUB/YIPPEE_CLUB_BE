# 25번 현재 선택 아이 변경 API 구현

> **최신 상태:** 후속 승인으로 개발 DB에 accounts.0004를 적용하고 기존 데이터/파일 보존 및 Django 검증을 완료했다. 현재 테이블 25개·migration 29개다. 아래 미적용 설명은 최초 구현 단계의 기록이며 [최종 DB 적용 결과](ACTIVE_CHILD_DB_DEPLOYMENT.md)의 13절을 따른다.

2026-11-15. 기존 사용자·아이·JWT·공통 오류 구조를 재사용해 선택 아이 변경 API를 추가했다. 개발 DB migration 적용, 개발 DB 데이터 쓰기, Git stage/commit/push/PR/merge는 수행하지 않는다.

## 1. 사전 확인 및 계약

- 시작 브랜치 `dev`, HEAD `2af4c38153dd35ae3b42a98230ebe5574c2ee4c2`.
- 원격 dev도 같은 SHA, main은 `fc6b600eccf463074262439987a7d4ce5789c17e`. 이전 읽기 전용 비교에서 main은 같은 파일 내용의 병합 커밋이며 이번 원격 조회에서 SHA가 그대로임을 확인했다. 브랜치 변경/원격 갱신은 하지 않았다.
- 시작 작업 트리에는 미추적 `docs/API_V1_5_IMPLEMENTATION_AUDIT.md`가 있었다. 해당 감사 문서를 수정하지 않고 보존했다.
- User는 정수 PK와 이메일 로그인 식별자를 사용하는 모델이며 Child.user는 이 모델의 FK다. 선택 상태를 저장할 기존 필드/모델은 없었다.
- Markdown 25번과 OpenAPI의 `PUT /users/me/active-child`는 JWT, 필수 integer child_id, 200 active_child_id를 정의한다. 400/401/409/500이 있고 404는 없으므로 없는/타인 아이는 같은 400으로 처리했다.

```http
PUT /api/v1/users/me/active-child
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{"child_id": 1}
```

성공 HTTP 200:

```json
{"active_child_id": 1}
```

조회/선택 해제 API나 profile/아이 응답 필드는 추가하지 않았다. 25번은 PUT만 지원하며 동일 아이 반복 선택도 200이다. 선택 저장 상태는 DB에 유지된다.

## 2. 변경 파일

| 파일 | 변경 |
|---|---|
| accounts/models.py | User.active_child nullable FK 추가 |
| accounts/migrations/0004_user_active_child.py | 새 AddField migration, 기존 migration 불변 |
| children/serializers.py | ActiveChildSerializer, 기존 엄격한 정수 ID 필드와 StrictSerializer 재사용 |
| children/views.py | ActiveChildView 추가, 아이 삭제 시 선택과 동일한 잠금 순서 적용 |
| children/urls.py | users/me/active-child 경로를 기존 /api/v1 include에 연결 |
| children/test_active_child.py | API·정합성·삭제·동시성·업그레이드 테스트 |
| docs/ACTIVE_CHILD_API_IMPLEMENTATION.md | 본 보고서 |

accounts URL이나 기존 profile serializer, Child 모델/기존 migration, 인증/활동지/찜/장바구니 구현은 수정하지 않았다. 기존 카테고리 ID 필드를 재사용하는 것은 같은 정수 타입/범위 검사를 공유하는 것이며 선택 ID를 카테고리 테이블에서 조회한다는 뜻은 아니다.

## 3. 저장 구조 및 migration 영향

`User.active_child` → `children.Child` FK, null=True, blank=True, editable=False, on_delete=SET_NULL, related_name=selected_by_users.

- 기존 accounts_user에 nullable active_child_id 컬럼·FK·인덱스를 추가한다. 기존 User PK나 Child.user 관계는 변경하지 않는다.
- 신규 사용자와 migration 이전 사용자는 선택값 NULL로 시작한다. 처음 등록한 아이를 임의로 자동 선택하거나 기존 행에 임의의 아이를 배정하지 않는다.
- 사용자의 선택은 한 컬럼이므로 여러 아이를 동시에 선택하는 복수 관계 행이 생기지 않는다.
- FK는 존재하는 아이만 참조하게 한다. ‘그 아이가 해당 사용자의 소유’인지는 API의 SQL 조건/권한 검사로 보장하며 단일 FK가 이를 DB 차원에서 자동 보장하지는 않는다. 내부 writer도 같은 검증을 지켜야 한다.
- editable=False로 기존 Django Admin 폼에 임의의 선택 입력을 추가하지 않는다. API 응답에도 사용자 ID나 아이 상세 정보는 노출하지 않는다.

신규 migration 의존성은 accounts.0003_user_agreements_user_name_user_nickname_user_phone_and_more 및 children.0001_initial이다. Child 초기 migration은 User의 첫 migration에 의존하므로 이번 후속 AddField로 순환 migration을 만들지 않는다. 기존 migration을 수정하거나 fake 적용하지 않는다.

migration 파일은 DB 차단 preview 설정의 MigrationLoader(None)/Autodetector/Writer로 생성했다. 개발 DB 이력 조회나 SQL 실행 없이 새 파일만 작성했다. 실 SQL과 기존 행 보존은 새 격리 테스트 DB의 업그레이드 테스트에서 확인한다.

## 4. 인증·입력·소유권·오류

기존 ChildAPIView의 JWT/IsAuthenticated·IsChildOwner·auth_exception_handler를 재사용한다.

1. 토큰 누락·무효·만료·refresh 오사용·비활성 사용자는 401.
2. child_id는 JSON 정수 1~9223372036854775807이어야 한다. 누락/null/bool/문자열/실수/객체/배열/범위 초과는 400.
3. user_id/is_staff/active_child_id 등 정의되지 않은 입력 필드는 StrictSerializer가 400으로 거부한다.
4. `Child.objects.select_for_update().filter(pk=child_id, user=request.user)`로 본인의 아이만 찾고 object permission도 확인한다.
5. 없거나 타인의 아이면 같은 400 VALIDATION_ERROR, 같은 메시지·details를 사용한다. 타인 아이의 이름/소유자/존재 여부를 구별해 주지 않는다.
6. 기존 오류 envelope의 code/message/details/request_id를 유지한다. 선택 요청이 실패하면 이전 선택은 그대로다.

서버의 request.user만 저장 대상으로 사용하고 요청에서 사용자/권한을 바꿀 경로는 추가하지 않았다. 이미 같은 아이가 선택됐으면 별도 UPDATE 없이 200을 반환한다.

## 5. 삭제 및 동시성

선택은 atomic 안에서 **대상 Child → 현재 User** 순서로 select_for_update 잠금을 취한다. 같은 사용자의 서로 다른 아이 선택도 User 행에서 직렬화된다. 성공적으로 마지막에 처리된 선택이 저장되며 요청 도착 순서나 기기별 우선순위까지 보장하지 않는다.

기존 DELETE children/{child_id}도 먼저 본인 Child를 잠그고 현재 User를 잠근 뒤 기존 ORM delete를 수행한다. 응답·소유권·CASCADE 동작은 유지하면서 선택과 잠금 순서를 통일했다.

- 선택된 아이 삭제: Django SET_NULL이 선택을 NULL로 초기화한다. 형제 아이를 자동 선택하지 않는다.
- 선택되지 않은 아이 삭제: 현재 선택을 보존한다.
- 선택 중 같은 아이 삭제: 선택이 먼저 성공한 뒤 삭제되면 NULL, 삭제가 먼저 완료되면 선택은 400이다. dangling FK를 허용하지 않는다.
- 이전 선택 아이 삭제와 형제 아이 선택 경합: User 행에서 순서를 정하고 새 형제 선택을 보존한다.
- ChildInterest·ActivityRecord는 기존 ORM CASCADE로 삭제하고 Category/User/다른 아이·기록은 보존한다. 실패하면 선택값과 삭제 대상도 atomic rollback된다.
- 직접 ORM Child.delete에도 SET_NULL이 적용된다. 사용자 ORM 삭제의 기존 Child CASCADE도 유지한다.

**SET_NULL은 Django ORM 삭제 정책**이다. MySQL FK에 ON DELETE SET NULL을 별도 지정한 것이 아니므로, 참조 중인 Child를 직접 SQL로 삭제하는 경우 DB FK가 거절할 수 있다. 외부 SQL/다른 writer가 선택·소유권을 임의 변경하는 시나리오까지 API 잠금 규약이 보호한다고 해석하지 않는다. 현재 사진 필드/스토리지 정리는 기존과 같이 없으며 이를 새로 구현하지 않았다.

## 6. 검증 방식

기존 `.venv/Scripts/python.exe scripts/run_fresh_feature_tests.py`를 재사용한다. 실행할 때마다 `.mysql-rehearsal/cart-tests-<새 ID>/data`에 새 MySQL을 초기화하고 port 33307/server_id 9133307/datadir를 확인한다. 기존 datadir·테스트 DB를 재사용하지 않는다.

새 suite DB에서만 migration·테스트 데이터를 사용한다. 업그레이드 테스트는 이 새 일회용 스키마 안에서 accounts 0003 상태를 구성하고 기존 사용자/아이/기록을 만든 뒤, 0004 하나의 forward plan/SQL과 nullable 기본값·FK·데이터 보존을 검증하고 최신 상태로 복구한다. 개발 DB를 내리거나 기존 migration 파일을 바꾸는 작업이 아니다.

신규 테스트 범위:

- 선택 성공/형제 전환/동일 아이 반복/새 클라이언트의 서버 저장 상태.
- 타인/없는 아이의 동일 오류·아이 없는 사용자 NULL 유지.
- JWT 누락/무효/만료/refresh/비활성, 엄격한 자료형·필수 필드·권한 주입 거부.
- 선택/비선택 아이 삭제, 타인 삭제 거부, ORM SET_NULL·User CASCADE, 실패 rollback, dangling FK 차단.
- profile/아이 응답 불변, 지원 메서드, 활동지·찜·장바구니·권한 데이터 보존.
- 동시 서로 다른/같은 선택, 같은 아이 삭제 경합, 형제 선택과 이전 아이 삭제 경합, 삭제 잠금 이후 대기 선택 거부.
- 기존 데이터가 존재하는 상태의 신규 migration 업그레이드·FK 검증 및 migration 충돌 검사.

## 7. 실행 결과

첫 실행 `.mysql-rehearsal/cart-tests-010a8b636801/`은 신규 17개를 포함한 168개 중 166개 통과·기존 preview 전용 2개 제외였다. 추가로 타 앱 데이터 보존 검사를 넣고 삭제 대기 경합/SQL 검증을 강화했다.

두 번째 `.mysql-rehearsal/cart-tests-a50f833c4fa1/`은 169개 중 166개 통과·테스트 보조 코드 오류 1개·기존 2개 제외였다. MigrationExecutor에 없는 collect_sql을 호출한 검사 오류였으며 실제 Django sqlmigrate가 사용하는 MigrationLoader.collect_sql로 수정했다. 해당 실행의 기능/권한/삭제/동시성 회귀는 통과했고, 실패 스키마도 정상 제거·서버 종료했다. 개발 DB 변경이나 migration 복구 작업은 없었다. 실패 증거도 보존했다.

세 번째 `.mysql-rehearsal/cart-tests-ce83a4bcc1c9/`에서는 SQL의 `REFERENCES children(id)`와 검사 문자열 사이 공백 유무만 달라 SQL 문자열 검사 1개가 실패했다(166개 통과·기존 2개 제외). SQL 의미나 기능 오류가 아니며 검사를 SQL 공백을 허용하는 정규식으로 보완했다. 이 실행도 새 스키마 제거·서버 정상 종료를 완료했다.

**최종 실행: `.mysql-rehearsal/cart-tests-d382bebcb5dd/`.**

| 검증 | 결과 |
|---|---|
| 신규 아이 선택 테스트 | **18개 모두 통과**: API/삭제/정합성 12, 동시성 5, 기존 데이터 migration 1 |
| 기존 회귀 | **151개 중 149 통과, 기존 preview 전용 2개 제외** |
| 전체 | **169개 중 167 통과, 실패/오류 0, 제외 2**, 107.284초 |
| 새 DB 전체 migration | 0004 포함 정상 적용 |
| 기존 데이터 업그레이드 | 0004 하나의 forward plan/SQL 확인, 기존 사용자/아이/기록 및 NULL 초기값·FK 확인 |
| Django system check | 오류 없음 |
| makemigrations --check --dry-run | No changes detected |
| migration graph/model 대조 | DB 차단 상태에서도 충돌 없음·모델과 migration 일치 |
| 기존 profile/아이 응답 | 변경 없음, 명세 25의 URL/PUT/정수 요청·응답 확인 |
| 기존 migration 파일 | 이전 증거의 해시와 모두 동일 |
| .env/기타 기존 Python 코드 | 의도한 기존 파일 4개 외 변경 없음, 구매 권한 플래그 False 유지 |
| 실제 파일 | private 저장 파일 20개·원본 자료 8개 해시/파일 집합 동일 |
| 개발 DB 접근 | **없음**, migration/테스트 계정/아이/데이터 쓰기 없음 |
| 테스트 DB 재사용 | 없음, 실행마다 새 datadir와 새 테스트 스키마 |
| 종료 | 새 테스트 스키마 제거·격리 MySQL 정상 종료 |

`test.txt`, `check.txt`, `makemigrations.txt`, `report.json`에 결과가 있다. 최종 report의 success=true, development_database_accessed=false, existing_test_database_reused=false, isolated_server_shutdown=true를 확인했다. 기존 코드/설정 해시 및 신규 변경 파일 해시는 같은 디렉터리 `active-child-source-hashes.json`에 보관한다. 이전 실패/성공 증거도 삭제하지 않았다.

회귀 범위는 인증/이메일/JWT/프로필/아이/공통 카테고리/활동지·파일·Admin/찜/장바구니·구매 권한 검사를 포함한다. 실제 SMTP/PG나 실제 개발 DB의 인증 쓰기는 수행하지 않았다. 이번 환경에서 통과했다는 결과이며 Python 3.12 실행을 대신하지 않는다.

## 8. 개발 DB 적용 및 남은 정책

**개발 DB에는 0004를 적용하지 않았다.** 이 코드의 실제 서비스 배포 전에는 별도 승인에 따른 백업/복원 리허설과 migration 적용이 필요하다. User에 새 컬럼이 생기므로 migration 없는 기존 DB에서 신규 모델 코드로 인증/사용자 ORM을 실행하면 컬럼 부재 오류가 날 수 있다. 이번 작업에서는 개발 DB로 해당 코드를 실행하지 않았다.

초기/아이 없음/선택 아이 삭제 후 NULL은 저장 상태의 정책이다. 성공 PUT은 실제 선택한 integer만 반환하므로 25번의 non-null 성공 응답과 충돌하지 않는다. 요청 null을 선택 해제로 해석하지 않는다. 선택 상태 GET·프로필 노출·자동 선택·멀티 기기 UI/실시간 동기화는 명세/요청 범위에 없어 추가하지 않았다.

로컬 환경은 Python 3.13.3/Django 5.2.19/MySQL 8.0.46이며 Python 3.12 CI 검증은 별도 과제다. CART_PURCHASE_ENTITLEMENTS_VERIFIED=False, 실제 .env·PDF/이미지·백업·기존 계정·개발 데이터는 변경하지 않는다. 감사 문서의 집계는 감사 시점의 기록으로 보존하며 이번에 과거 감사 결과를 덮어쓰지 않았다.
