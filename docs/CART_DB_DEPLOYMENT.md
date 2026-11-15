# 장바구니 개발 DB migration 적용 및 검증 결과

2026-11-15, 사용자가 승인한 **cart.0001_initial, purchases.0001_initial 두 migration만** 개발 DB에 적용했다. 새 백업 → 새 격리 MySQL 복원 → 두 migration 리허설 → 전체 회귀 → 실제 적용 → 데이터/파일 보존 확인 순서로 진행했다.

## 적용 전 개발 DB 상태

- 브랜치 `dev`. 기존 미커밋 변경은 보존했으며 브랜치를 변경하지 않았다.
- DB `yippee_club_db`, 로컬 루프백 MySQL, 포트 **3306**. 접속 설정은 기존 설정을 재사용했다.
- 서버 UUID `5491c807-5688-11f1-a0bf-c86e08e6aa63`, MySQL **8.0.46**. 모든 개발 DB 연결에서 DB/계정/UUID/포트를 검증했다.
- 기존 테이블 **23개**, migration **26개**. 기존 migration 충돌·불일치 없음.
- 미적용 migration은 승인된 두 개뿐. 새 모델은 각각 기존 `accounts.User`, `activities.Activity`에 의존한다.
- 활동지 **ID 1~4**, 모두 공개·가격 **0원**. 카테고리 **2개**(ID 1·2), 사용자 **0명**, 관리자 **0명**, 즐겨찾기 **0건**.
- 기존 favorites 적용 증거 `.mysql-rehearsal/favorites-apply-7dfeec326257/report.json`과 비교했다. 기존 전체 테이블의 스키마/행 해시/FK/migration 이력, 공개 API 응답, private 파일 **20개**, 원본 자료 **8개**가 일치했다. 기존 migration 파일 해시도 동일했다.
- 실제 `.env`와 구매 권한 설정은 변경하지 않았다. `CART_PURCHASE_ENTITLEMENTS_VERIFIED=False`를 적용 전후 확인했다.

## 새 백업 및 복원 검증

증거 디렉터리: `.mysql-rehearsal/cart-deploy-1f7fdfc90b4f/`.

- 전체 백업: 위 디렉터리의 `yippee_club_db.sql`, **29,549 bytes**.
- SHA-256: `a7882b6465a07fff5b23dc2486a0ea05db41e9fa4471225d23d3099fcbc1c9a4`.
- mysqldump의 single-transaction·skip-lock-tables 옵션으로 새 백업을 만들었다. 기존 백업을 덮어쓰거나 삭제하지 않았다.
- 각 기존 테이블의 CREATE TABLE, 컬럼 메타데이터, 행 수, 전체 행 해시, FK와 migration 이력을 `report.json`에 보관했다. 원본 파일을 읽어 해시를 기록하고 private 파일은 별도 복사본도 검증했다.
- 새 `data/`에 별도 MySQL을 초기화했다. 포트 **33307**, server_id **9133307**, 정확한 datadir 및 개발 서버와 다른 UUID를 확인한 후에만 격리 DDL을 실행했다.
- 새 `test_yippee_migration_fresh`에 백업을 복원했다. **기존 23개 전체 테이블의 스키마·컬럼·행 해시·FK·migration 이력 완전 일치**를 확인했다.
- 기존 격리 인스턴스나 테스트 DB는 재사용하지 않았다. 개발 DB와 원본 파일도 리허설 전후 동일했다.

## 격리 적용 및 회귀 검증

복원 DB의 적용 계획이 정확히 두 migration인지 확인하고, 개발 DB와 동일한 순서로 `cart`, `purchases`를 각각 적용했다. 예상 SQL은 새 테이블 CREATE 2건, 해당 새 테이블의 FK ADD 4건뿐이었다. 기존 테이블 ALTER/DROP 및 업무 데이터 변경 SQL은 없었다.

| 검증 | 결과 |
|---|---|
| 두 migration 적용 | 모두 성공 |
| 신규 테이블/FK | 테이블 2개, FK 4개 확인 |
| UNIQUE | 두 테이블 모두 (user_id, activity_id), NON_UNIQUE=0 확인 |
| 구매 권한 CHECK | 이름·조건·ENFORCED=YES 확인 |
| 기존 데이터·스키마 | 기존 업무 테이블 완전 일치, 기존 metadata 행 보존 |
| 전체 회귀 | **151개 중 149 통과, 0 실패/오류, 기존 preview 전용 2개 제외** |
| 신규 장바구니 테스트 | **16개 모두 통과**, 전체 결과에 포함 |
| Django system check | 오류 없음 |
| migration 충돌/모델 일치 | 충돌 없음, makemigrations --check --dry-run: No changes detected |
| 테스트 후 복원 DB | 테스트 전 스키마·데이터·제약과 동일 |
| 종료 | 새 테스트 스키마 제거, 격리 MySQL 정상 종료 |

테스트는 새 `test_yippee_migration_suite`를 생성해 실행하고 제거했다. `--keepdb`는 사용하지 않았다. 계정/JWT/이메일 인증/프로필/아이/카테고리/활동지 검색·필터·파일/Admin/즐겨찾기 회귀를 포함한다. 장바구니에서는 소유권·엄격한 입력·중복/UNIQUE·동시 요청·유효/회수 구매 권한·503 차단·삭제 시 원본 보존을 확인했다.

기본 설정은 False다. 기존 테스트의 override_settings는 격리 테스트 범위에서만 유효하며, 실제 개발 설정을 True로 바꾸지 않았다. 권한 데이터 미연결 상태의 추가 요청이 503임은 격리 테스트 `test_unverified_empty_permissions_fail_closed_and_read_delete_work`로 검증했다.

환경은 로컬 **Python 3.13.3 / Django 5.2.19 / MySQL 8.0.46**이다. Python 3.12 검증은 수행하지 않았다.

## 실제 개발 DB 적용

리허설 종료 후 다음을 다시 확인하고 실행했다.

1. 백업 SHA-256과 성공한 복원/테스트/정상 종료 증거.
2. 현재 개발 DB·기존 파일·API·전체 코드/migration 및 `.env` 해시가 리허설 시작 상태와 일치.
3. 전체 미적용 계획이 정확히 두 migration이며 예상 SQL 6건과 일치.
4. 구매 권한 설정 False.

실제 실행은 증거 디렉터리의 `apply_approved.py`로 수행했다. 한 번 적용을 시작하면 재시도하지 못하도록 `apply-started.json`을 생성했다. SQL 실행기는 리허설에서 확정한 DDL 원문 6건만 허용하고, metadata INSERT는 승인된 migration 두 개·ContentType 두 개·각 네 Permission으로 제한했다. 실행 중 각 SQL 전 개발 DB 식별자를 재확인했다.

| SQL 분류 | 실행 건수 |
|---|---:|
| 새 테이블 생성 | 2 |
| 새 테이블 FK 추가 | 4 |
| migration 이력 INSERT | 2 |
| ContentType INSERT | 2 |
| Permission INSERT (각 4행) | 2 |

총 12개 변경 SQL이며, 기존 업무 테이블의 데이터 변경·DDL은 없었다. migration 이력은 기존 26개를 그대로 보존하고 신규 2개를 추가했다. Django가 관리하는 ContentType/Permission 추가는 두 앱의 정상 migration 부수 효과다.

## 적용 후 상태

| 항목 | 적용 전 | 적용 후 |
|---|---:|---:|
| 전체 테이블 | 23 | **25** |
| migration 이력 | 26 | **28** |
| ContentType | 17 | **19** |
| Permission | 68 | **76** |
| 사용자 / 관리자 | 0 / 0 | **0 / 0** |
| 활동지 | 4 | **4**, ID 1~4, 공개·0원 유지 |
| 카테고리 | 2 | **2**, ID 1·2 및 내용 유지 |
| 즐겨찾기 | 0 | **0** |
| cart_items | 없음 | **0행** |
| purchase_entitlements | 없음 | **0행** |

미적용 migration은 없다. 기존 모든 업무 테이블의 스키마/컬럼/전체 행 해시와 기존 FK·제약조건을 보존했다. metadata는 기존 행을 모두 보존하고 예상한 새 행만 추가됐다. 실제 적용 결과의 전체 스키마·FK·데이터·제약을 격리 적용 결과와 비교해 일치를 확인했다(migration 적용 시각은 별개).

### cart_items

- InnoDB, utf8mb4_unicode_ci.
- `id`: bigint PK, AUTO_INCREMENT.
- `user_id`: int NOT NULL, 기존 accounts_user.id FK.
- `activity_id`: bigint NOT NULL, 기존 activities.id FK.
- `unique_user_activity_cart`: (user_id, activity_id) UNIQUE.
- Activity FK 인덱스 및 User/Activity FK 2개 확인.
- Django on_delete는 두 관계 모두 CASCADE. 장바구니 행 삭제가 참조 원본을 삭제하지 않는다. MySQL FK 자체에 ON DELETE CASCADE를 새로 지정한 것은 아니다.

### purchase_entitlements

- InnoDB, utf8mb4_unicode_ci.
- `id`: bigint PK, AUTO_INCREMENT.
- `user_id`: int NOT NULL, 기존 accounts_user.id FK.
- `activity_id`: bigint NOT NULL, 기존 activities.id FK.
- `status`: varchar(16) NOT NULL. 모델 기본값 active는 Django 기본값이며 임의 레코드는 생성하지 않았다.
- `granted_at`: datetime(6) NOT NULL.
- `revoked_at`: datetime(6) NULL.
- `unique_user_activity_entitlement`: (user_id, activity_id) UNIQUE.
- `entitlement_status_revoked_at`: active이면 revoked_at IS NULL, revoked이면 IS NOT NULL, **ENFORCED=YES**.
- Django on_delete는 두 관계 모두 PROTECT. 권한이 존재하는 사용자/활동지 삭제 정책은 기존 구현대로이며 변경하지 않았다.

## Django 및 공개 API 사후 검증

- 개발 DB 대상 `check --database default`: 오류 없음.
- 전체 `showmigrations`: 모든 migration `[X]`, 신규 두 개 포함.
- `makemigrations --check --dry-run`: No changes detected.
- 공개 목록 200, count=4. 활동지 상세 4개 모두 200, 없는 ID 404.
- 기존 검색/카테고리/연령/난이도/시간/가격 필터 12개 조건 확인.
- 실제 임시 loopback HTTP 서버에서 목록/상세 4개, PDF 4개·이미지 4개 GET 모두 200. 다운로드 바이트 SHA-256은 원본 자료와 일치하며 임시 서버는 종료했다.
- private 저장 파일 20개와 원본 자료 8개의 해시가 적용 전후 동일했다. PDF/이미지를 수정·삭제하지 않았다.
- 공개 GET 확인 후 DB/파일 스냅샷도 동일했다.
- 개발 DB에 계정·장바구니·구매 권한·세션·기타 테스트 데이터를 생성하거나 삭제하지 않았다. 실제 JWT 쓰기 검증은 사용자/관리자가 없으므로 실행하지 않았고 격리 결과를 사용한다.

## 발생한 오류

최초 사전 검사에서 `active_superusers`의 MySQL SUM 결과가 Decimal이고 JSON 정규화 후 문자열 `"0"`이 되어, 정수 0과 비교하는 검사 도구가 중단했다. 읽기 전용으로 실제 계정 0명 및 이전 전체 스냅샷 일치를 확인하고 집계 비교에 int 변환을 적용했다. 이때 개발 DB 변경은 없었다. 이후 백업/복원/리허설/실제 migration/사후 검증 오류는 없었다. 자동 복구·재적용·초기화도 없었다.

## 증거 및 Git 상태

위 증거 디렉터리의 주요 파일:

| 파일 | 내용 |
|---|---|
| report.json | 사전 전체 스냅샷, 백업 해시, 복원·격리 적용 결과, 제약, 코드 해시, 정상 종료 |
| yippee_club_db.sql | 새 전체 백업 |
| plan.txt, cart-sql.txt, purchases-sql.txt | 격리 적용 계획 및 SQL |
| cart-migrate.txt, purchases-migrate.txt | 격리 적용 로그 |
| test.txt, check.txt, makemigrations.txt | 회귀·Django 검증 |
| apply_approved.py, apply-started.json | 단일 적용 실행기와 시작 표식 |
| apply-report.json | 실제 적용 전후 스냅샷, 실행 SQL 분류, 공개 API·HTTP·파일 검증 |
| development-migrate.txt, development-checks.txt | 실제 적용 및 Django 검사 로그 |
| git-status-before.txt, git-status-after.txt | 적용 전후 작업 트리 |

`.mysql-rehearsal/`, 실제 `.env`, 백업/자격증명, private_uploads/, sample_activities/는 Git 추적에서 제외된다. 백업·증거는 삭제하지 않았다.

기존 미커밋 변경 `.env.example`, `config/settings.py`, `config/urls.py`와 미추적 `cart/`, `purchases/`, `docs/CART_API_IMPLEMENTATION.md`, `scripts/run_fresh_feature_tests.py`를 보존했다. 이번 단계에서 추가한 작업 파일은 다음뿐이다.

- `config/cart_deploy_rehearsal.py`: 새 격리 인스턴스 UUID/datadir/연결 검증 설정.
- `scripts/deploy_cart_db.py`: 읽기 전용 사전 확인 및 새 백업/복원/격리 리허설 도구. 실제 적용 기능은 없으며 적용 완료 후 다시 실행하면 적용 전 상태 검사에서 중단한다.
- `docs/CART_DB_DEPLOYMENT.md`: 본 결과 문서.

기능 코드/기존 migration은 변경하지 않았다. git add/commit/push/PR/merge/reset/원격 브랜치 변경은 수행하지 않았다.

## 다음 개발 단계

1. 실제 구매 권한 데이터 원천·연동·이관·정합성 검증을 설계하고 완료하기 전까지 **CART_PURCHASE_ENTITLEMENTS_VERIFIED=False**를 유지한다. 빈 테이블을 미구매 근거로 사용하지 않는다. 현재도 추가 요청은 연동 확인 전 503을 반환한다(인증/입력 오류는 기존 우선순위 유지).
2. 명세의 제안 오류 코드 ALREADY_PURCHASED, 권한 회수 후 재추가, 탈퇴/삭제 시 권한 보존 정책은 팀에서 확정한다. 실제 결제·주문·PG·환불 기능은 이번 작업에 추가하지 않았다.
3. Python 3.12 CI/격리 환경 검증을 진행한다.
4. 개발 DB의 실제 JWT 장바구니 수동 검증이 필요하면 사용자가 직접 계정을 준비한 후 별도 범위를 정한다. 구매 연동 확인 전 추가 차단 정책은 유지한다.
