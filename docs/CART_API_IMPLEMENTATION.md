# 장바구니 API 분석 및 설계

## 사전 확인

- 시작 브랜치 `dev`, 작업 트리 변경 없음. commit/push/PR/merge는 수행하지 않는다.
- 기존 앱: accounts, email_verification, children, categories, activities, favorites.
- `accounts.User`와 SimpleJWT 인증 및 기존 공통 오류 처리기를 재사용한다.
- 개발 DB migration 26개 모두 적용됨을 `showmigrations --plan`으로 읽기 전용 확인했다.
- 기존 활동지는 `is_public`과 가격 0원 CHECK 제약을 사용한다. 별도의 판매 상태 필드는 없고 기존 Serializer는 `on_sale`을 반환한다. 이 구조는 변경하지 않는다.
- 모델·migration 전체에 구매/주문/구매 권한 모델은 없다. v1.5의 `purchase_entitlements`는 제안 단계다.

## 명세와 요청의 차이

Markdown 및 OpenAPI 44~46번 계약을 우선한다.

| 기능 | 경로 | 응답 |
|---|---|---|
| 조회 | `GET /api/v1/cart` | 200, `items`, `total_amount` |
| 추가 | `POST /api/v1/cart/items` | 201, `activity_id`, `message` |
| 삭제 | `DELETE /api/v1/cart/items/{activity_id}` | 204, 본문 없음 |

조회 페이지네이션·정렬·items 원소 스키마는 명세에 정의되지 않았다. 구현 선택은 전체 조회, 최근 등록 ID 순서, 기존 ActivitySerializer 재사용이다. 명세 확정 사항과 구별해야 한다. 명세에 없는 조회 query는 기존 StrictSerializer 방식으로 400 처리한다. GET /cart/items 별칭은 추가하지 않았다.

## 장바구니 관계

`cart_items`: 기존 User 및 Activity FK, (user, activity) UNIQUE. 두 FK는 CASCADE로 관계 행만 제거하며, 장바구니 행 삭제가 원본을 삭제하지 않는다. 별도 carts 컨테이너는 명세의 CartItem 사용자별 UNIQUE 구조에 불필요하므로 만들지 않는다. 신규 initial migration만 추가하고 개발 DB에는 적용하지 않는다.

## 승인된 구매 권한 최소 설계

이미 구매한 활동지 차단은 확정이지만 `ALREADY_PURCHASED` 오류 코드는 제안이다. 기존 구매 정보를 확인할 수 없는 상황을 미구매로 취급하지 않는다.

사용자는 **최소 구매 권한 모델 작성 + 확인 전 추가 차단** 안을 선택했다. `purchase_entitlements`에 user/activity FK, 사용자·활동지 UNIQUE, active/revoked 상태, granted_at/revoked_at을 구현했다. 결제/주문/PG 및 구매 권한 생성 API는 구현 범위에서 제외한다. 신규 빈 테이블 생성만으로 구매 이력 검증이 완료되지 않으므로 `CART_PURCHASE_ENTITLEMENTS_VERIFIED=False`를 기본값으로 한다. 이때 유효한 형식의 추가 요청은 DB 조회·삽입 전에 503 SERVICE_UNAVAILABLE로 거절한다. 입력 오류는 400, 인증 실패는 401이 우선한다. 이 운영 보호 응답은 v1.5 추가 계약이며 사용자가 선택한 안전장치다.

구매 권한 추가에는 별도 신규 migration과 ContentType/Permission 생성 영향이 있다. 기존 사용자·활동지·가격·구매 데이터를 변경하거나 기존 migration을 수정할 필요는 없다.

- 권한 데이터 보존을 위해 두 FK는 PROTECT다. 권한이 연결된 사용자·활동지 삭제는 거부된다. 기존 활동지/사용자의 일반 수정·조회에는 영향을 주지 않지만, 향후 탈퇴/삭제 정책에서는 별도 보존·익명화 정책을 정해야 한다.
- active는 revoked_at NULL, revoked는 revoked_at NOT NULL이어야 하며 DB CHECK로 검증한다.
- active 권한이 있으면 409 ALREADY_PURCHASED로 거절한다. 이 코드는 여전히 v1.5 제안 코드다. 회수된 권한은 유효한 구매 권한이 아니므로 추가 가능하게 구현했다. 환불/취소/재구매 최종 정책은 확정되지 않았다.
- 한 사용자·활동지에 한 권한 행을 유지한다. 결제 이력 테이블이 아니며 여러 구매 시도 이력을 표현하지 않는다. 무료 다운로드를 구매로 간주해 자동 권한을 생성하지 않는다.
- 장바구니 추가는 transaction.atomic 내 Activity select_for_update → active 권한 조회 → get_or_create 순서다. 동시 장바구니 요청은 같은 활동지 잠금과 UNIQUE로 방어한다.
- **향후 권한 부여·회수 처리도 같은 Activity 행을 먼저 select_for_update해야 한다.** 아직 권한 writer는 구현하지 않았다. 이 규약을 지키지 않는 외부 DML/향후 결제 구현과의 동시성까지 보장한다고 해석하지 않는다.
- 연결 확인 플래그는 구매 원천 연결·기존 데이터 이관·정합성 확인 완료 후에만 켠다. 이 플래그 자체가 데이터 완전성을 검증하거나 구매 권한을 부여하지 않는다.

비공개 활동지는 추가 시 400, 조회 items/total_amount에서 제외하며 기존 관계는 보존하고 삭제는 허용한다. 별도 판매 상태, 유료 가격, 가격 변경/판매 종료 정책은 만들지 않았다. 합계는 반환하는 활동지 객체의 DB 가격 합이며 현재 스키마에서는 모두 0원이다.

## 생성 및 변경 파일

- `cart/`: 앱 설정, CartItem 모델, Serializer, View, URL, API·DB 제약·동시성 테스트, `migrations/0001_initial.py`.
- `purchases/`: 앱 설정, PurchaseEntitlement 모델, `migrations/0001_initial.py`.
- `config/settings.py`: 두 앱 등록 및 기본 False 설정.
- `config/urls.py`: 기존 API prefix에 cart URL 통합.
- `.env.example`: 기본 False 설정 설명. 실제 `.env`는 변경하지 않는다.
- `scripts/run_fresh_feature_tests.py`: 신규 datadir에서만 실행하는 격리 회귀 실행기.
- 본 문서.

두 신규 migration은 기존 accounts/activities migration에 의존하며, 기존 테이블 ALTER/DROP/데이터 migration이 없다. 개발 DB에는 적용하지 않는다.

## 안전한 검증

기존 `run_isolated_feature_tests.py`는 `--keepdb`로 기존 테스트 스키마를 재사용한다. 이번 요청은 무단 재사용을 금지하므로 그대로 실행하지 않았다. 새 실행기는 새 datadir의 MySQL 인스턴스에서 비어 있는 신규 테스트 스키마를 만들고 기존 `config.user_model_rehearsal` SQL 대상 검증 설정을 재사용한다. port 33307, server_id 9133307, 정확한 datadir를 검증한 후에만 DDL을 허용한다. 기존 테스트 DB를 재사용하지 않으며 기본 Django 실행으로 새 테스트 DB를 생성/제거한다. 개발 DB migrate/flush/DDL/DML은 실행하지 않는다.

실행 명령: `.venv/Scripts/python.exe scripts/run_fresh_feature_tests.py`. 테스트 중에만 override_settings로 구매 데이터 검증 완료 상태를 설정하며, 차단 상태도 별도로 검증한다.

로컬 실행 환경은 Python **3.13.3**, Django **5.2.19**, MySQL **8.0.46**이다. 요청된 Python 3.12 환경은 로컬에서 확인되지 않았으므로 3.12에서 실행했다고 보고하지 않는다.

초기 offline preview의 system check는 통과했으나 makemigrations는 해당 설정의 의도된 연결 차단으로 실행되지 않았다. migration 생성은 일반 설정의 읽기 전용 이력 조회로 수행했으며, 실제 적용/충돌·모델 일치 검증은 격리 DB에서 수행한다.

## 검증 결과

증거 디렉터리: `.mysql-rehearsal/cart-tests-9008cb2a4d92/` (Git 추적 제외).

| 검증 | 결과 |
|---|---|
| 전체 회귀 테스트 | 151개 중 149 통과, 0 실패/오류, 기존 offline preview 전용 2개 제외 |
| 신규 장바구니 테스트 | 16개 모두 통과; 위 전체 결과에 포함 |
| 기존 회귀 | 기존 135개 중 133 통과, preview 전용 2개 제외 |
| 신규 migration 실제 적용 | 새 격리 MySQL 테스트 스키마에서 두 migration 적용 성공 |
| Django system check | 오류 없음 |
| migration 충돌·모델 일치 | makemigrations --check --dry-run: No changes detected |
| 동시 추가 요청 | 두 요청의 응답 201/409, 최종 관계 행 1개 |
| 기존 테스트 DB 재사용 | 없음; 새 datadir 및 스키마 생성 |
| 종료 | 새 테스트 DB 제거, 격리 MySQL 정상 종료 |

최종 개발 DB 읽기 전용 재확인: migration 충돌 없음, 미적용 migration은 `cart.0001_initial`, `purchases.0001_initial` 두 개뿐이다. 활동지 ID 1~4는 모두 공개·0원, 카테고리 2개, 사용자 0개 상태를 확인했다. 실제 개발 DB에 테스트 계정을 생성하지 않았다.

`test.txt`, `check.txt`, `makemigrations.txt`, `report.json`에 결과가 있다. 테스트에는 인증/JWT/프로필/아이/카테고리/활동지 검색·필터/다운로드/Admin/즐겨찾기 회귀, 구매 권한 격리·유효/회수 상태·확인 전 차단, 원본 보존, DB UNIQUE/CHECK 및 동시 요청 검증이 포함된다. 실제 개발 DB에서 인증 쓰기 요청이나 신규 migration은 실행하지 않았다.

## 남은 확인 및 다음 작업

1. 프론트엔드는 v1.5 경로를 사용해야 한다. `cart_item_id`와 `activity_id`를 혼용하지 않는다.
2. items 원소, 최근 등록순, 비공개 항목 제외, 회수된 권한 재추가, PROTECT 삭제 정책을 팀 계약으로 확정한다. `ALREADY_PURCHASED`도 제안 코드임을 확인한다.
3. 구매 권한의 원천·연결/이관·정합성 검증을 완료하기 전에는 기본 False를 유지한다. 개발 DB에 아직 두 테이블이 없으므로 현재 코드의 DB 연동 장바구니 조회·삭제를 사용하려면 먼저 migration 승인이 필요하다.
4. 개발 DB migration 적용은 별도 승인 후 백업/복원 리허설 및 기존 데이터 보존 검증과 함께 수행한다. 현재는 신규 migration 파일 작성과 격리 적용 검증만 완료했다.
5. 향후 결제·권한 writer는 위 잠금 규약과 주문/결제 상태 검증을 함께 구현해야 한다. 외부 DML writer와의 동시 구매/추가 경합은 이번 검증 범위가 아니다.
6. Python 3.12 CI/격리 환경에서 재검증한다. 실제 개발 데이터의 유료 가격·판매 종료 상태는 현재 모델에 없어서 검증할 수 없다.

개발 DB 데이터 수정/삭제/초기화, 기존 migration 수정, flush, fake migrate, 기존 테스트 DB 재사용, stage/commit/push/PR/merge는 수행하지 않았다. 실제 `.env`, PDF/이미지, 기존 계정은 변경하지 않았다.
