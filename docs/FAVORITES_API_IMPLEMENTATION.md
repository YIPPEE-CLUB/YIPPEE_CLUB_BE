# 활동지 즐겨찾기 API

> **개발 DB 적용 완료:** 후속 사용자 승인에 따라 favorites.0001_initial을 적용하고 기존 데이터/파일 보존 및 공개 API를 확인했습니다. 실제 계정이 없어 인증된 쓰기 검증은 아직 미실행입니다. [최종 적용 결과](FAVORITES_DB_APPLICATION.md)가 현재 상태입니다.

> 후속 작업에서 최신 백업의 두 독립 복원본, migration 리허설, 전체 회귀 및 실제 HTTP 28건 검증을 완료했습니다. **개발 DB는 여전히 미적용**이며 사용자 승인을 기다립니다. [DB 적용 준비 결과와 승인 후 절차](FAVORITES_DB_PREPARATION.md)를 참고하세요.

## 구현 범위와 파일

`favorites` 앱을 추가했습니다. `Favorite`는 기존 `accounts.User`와 `activities.Activity`를 FK로 참조하며, 사용자와 활동지의 다대다 연결을 표현합니다. DB 테이블명은 명세 제안과 같은 `favorites`, `(user_id, activity_id)` UNIQUE 제약 이름은 `unique_user_activity_favorite`입니다. 신규 사용자/활동지 테이블은 만들지 않습니다. 즐겨찾기 자체의 ID는 내부 정렬에 사용하고 응답에 노출하지 않습니다.

새 파일은 `favorites/{apps,models,serializers,views,urls,tests}.py`, 앱 및 migration 패키지 초기화 파일, `favorites/migrations/0001_initial.py`, 개발 DB/파일 보존 점검 도구 `scripts/check_favorite_source.py`, 이 문서입니다. 기존 `config/settings.py`의 앱 등록과 `config/urls.py`의 URL include만 추가했습니다. 기존 인증/아이/카테고리/활동지 구현과 원본 API 명세는 수정하지 않았습니다.

## 명세에 따른 API

v1.5 Markdown 41~43절 및 OpenAPI의 `/favorites`, `/favorites/{activity_id}`를 기준으로 구현했습니다. 경로 끝 슬래시는 없습니다. 세 API 모두 `Authorization: Bearer <access_token>`이 필요합니다.

| 메서드 | URL | 성공 응답 |
|---|---|---|
| GET | `/api/v1/favorites?page=1&page_size=20` | 200, `{"results": [...]}` |
| POST | `/api/v1/favorites` | 201, `{"activity_id": 1, "message": "처리되었습니다."}` |
| DELETE | `/api/v1/favorites/1` | 204, 본문 없음 |

추가 요청의 JSON 본문:

```json
{"activity_id": 1}
```

`activity_id`는 1~9223372036854775807 범위의 JSON 정수여야 합니다. null, bool, 실수, 문자열 ID, 누락 및 user_id 등 명세에 없는 본문 필드를 거부합니다. 저장 사용자는 토큰으로 인증된 request.user에서만 결정합니다.

목록 예시(항목은 기존 ActivitySerializer를 그대로 재사용):

```json
{
  "results": [
    {
      "id": 1,
      "title": "단비와 보리의 징검다리 모험",
      "price": 0,
      "sale_status": "on_sale",
      "description": "인형을 집까지 안전하게 이동시키며 차례를 번갈아 가며 놀이하는 활동",
      "age_min_months": 60,
      "age_max_months": 65,
      "difficulty": "easy",
      "duration_min": 5,
      "duration_max": 5,
      "categories": [1, 2],
      "image": "http://localhost:8000/api/v1/activities/1/files/image",
      "pdf": "http://localhost:8000/api/v1/activities/1/files/pdf"
    }
  ]
}
```

항목 id는 활동지 ID입니다. 다른 사용자의 ID/이메일/즐겨찾기 내부 ID를 포함하지 않습니다. 이 예시는 계약 설명이며 실제 개발 DB에 즐겨찾기를 생성한 결과가 아닙니다.

## 인증·권한·오류

기존 SimpleJWT 인증과 공통 `auth_exception_handler`를 재사용합니다. 토큰 누락/잘못된 서명/만료/refresh token 오사용/비활성 사용자는 401입니다. 목록과 삭제의 DB 조건에는 항상 request.user가 포함됩니다. 다른 사용자의 관계만 있는 경우 삭제는 404이며 해당 관계는 유지합니다. 목록 query의 user_id 및 sort 같은 미정의 필드는 400으로 거부합니다.

모든 뷰 오류는 기존 `code`, `message`, `details`, `request_id` 형식입니다. 새로운 오류 코드 enum을 만들지 않았습니다. 중복 추가는 409 `INVALID_STATE`, 요청 오류는 400 `VALIDATION_ERROR`, 삭제 대상 없음은 404 `NOT_FOUND`입니다.

## 미확정 정책의 구현안과 근거

아래 정책은 원본 명세에 세부 규칙이 없거나 여러 상태 코드가 나열되어 있어 선택한 구현안입니다. 새 엔드포인트나 응답 필드는 추가하지 않았으며 프론트엔드/팀 확인이 필요합니다.

| 항목 | 구현안과 근거 |
|---|---|
| 중복 추가 | 명세의 409를 사용. 같은 쌍은 한 행만 유지하며 성공 201로 위장하지 않음 |
| 없는/비공개 활동지 추가 | 둘 다 400, activity_id 검증 오류. POST 명세에는 404가 없으므로 400을 사용하고 비공개 여부를 구별해 노출하지 않음 |
| 반복 삭제·본인 관계 없음 | 404. DELETE 명세에 허용된 상태이며 실제 관계 없음과 일치. 성공 시만 204 |
| 비공개 활동지 목록 | 목록에서 제외하고 페이지 크기를 계산하기 전에 필터링. 숨긴 메타데이터/파일 URL을 노출하지 않음 |
| 기존 활동지가 비공개로 전환 | 관계를 삭제하지 않고 보존. 재공개 시 목록에 다시 표시되며 본인은 비공개 상태에서도 DELETE 가능 |
| 활동지/사용자 삭제 | Django ORM의 CASCADE로 즐겨찾기 관계만 삭제. 즐겨찾기 삭제는 사용자/활동지/카테고리/파일에 영향을 주지 않음. 직접 SQL로 참조 대상을 삭제하면 DB FK가 dangling 관계 생성을 차단 |
| 목록 항목 | OpenAPI items는 빈 스키마이므로 기존 ActivitySerializer 항목을 재사용. 래퍼/사용자 정보 같은 별도 필드를 만들지 않음 |
| 페이지네이션 | 명세의 최상위 results만 유지. count/next/previous를 추가하지 않음. page 기본 1, page_size 기본 20·최대 100, 범위를 벗어난 페이지는 200과 빈 results로 처리하여 GET에 미명세 404를 추가하지 않음 |
| 정렬 | 즐겨찾기 ID 내림차순, 최근 추가 순. 별도 sort 쿼리는 명세에 없어 지원하지 않음 |
| 기존 활동지 응답 | is_favorite가 명세에 없으므로 추가하지 않음. 익명/인증 상태의 기존 목록·상세 구조 동일 |

추가 요청은 트랜잭션에서 공개 Activity 행을 잠근 후 get_or_create를 수행합니다. 공개 취소/삭제와의 경합 및 같은 활동지에 대한 동시 추가를 직렬화하며 DB UNIQUE가 외부 쓰기에도 최종 중복 방어를 제공합니다. 같은 활동지를 여러 사용자가 동시에 추가할 때도 해당 행 잠금을 공유하므로 트래픽 증가 시 성능 관찰이 필요합니다.

## Migration 적용 계획

신규 migration은 **`favorites.0001_initial` 한 개**입니다. `activities.0001_initial` 및 swappable User의 초기 migration에 의존합니다. 실제 생성 SQL은 favorites 테이블, 사용자/활동지 FK와 복합 UNIQUE만 포함하며 기존 테이블 ALTER나 데이터 이동은 없습니다.

개발 DB는 **미적용**입니다. `migrate --plan`의 대기 작업은 favorites.0001_initial 하나이고, 기존 22개 테이블·25개 이력을 유지해야 합니다. 이번 코드 상태의 즐겨찾기 API를 개발 DB에서 실제 사용하려면 다음 단계의 별도 검증과 적용이 필요합니다. 승인 전에는 데이터 쓰기를 실행하지 마세요.

다음 단계 권장 순서: 정책/프론트엔드 계약 확인 → 최신 DB 대상·상태 확인 및 새 백업 → 격리 복원본 업그레이드와 기존 데이터 보존 검증 → 사용자 승인 후 신규 migration만 적용 → 23개 테이블·26개 이력 및 기존 활동지/파일 보존 확인 → 실제 JWT 사용자로 기능 확인. Django post_migrate는 신규 Favorite content type/permission 행을 추가할 수 있으므로 적용 검증에 포함합니다. 기존 migration 수정, fake, 초기화는 필요하지 않습니다.

## 검증 방법

개발 DB에는 즐겨찾기 테이블 생성이나 테스트 데이터를 넣지 않습니다. 기존 격리 실행 도구로 별도 33307 서버의 신원을 검증하고 격리 테스트 DB에만 migration을 적용합니다.

```powershell
.\.venv\Scripts\python.exe scripts/run_isolated_feature_tests.py --instance-dir .mysql-rehearsal/auth-api-d2ae7f54b9c0
```

즐겨찾기 테스트는 정상 추가/삭제·중복·응답 계약·페이지네이션·타 사용자 격리·필드 주입·잘못된 입력·JWT 누락/오류/만료·비공개 및 재공개·UNIQUE·ORM 삭제 관계·기존 활동지 응답 유지 등을 검증합니다. TransactionTestCase는 별도 DB 연결 두 개를 동시에 실행해 같은 JWT 사용자의 추가 결과가 201/409이고 실제 관계가 한 행인지 확인합니다. 작업 스레드에도 기존 SQL 대상 검증기를 명시적으로 적용합니다.

`scripts/check_favorite_source.py`는 개발 DB의 모든 테이블 스키마/행 해시/FK/이력, 공개 활동지 응답, 원본 파일 및 private_uploads 파일 해시, 기존 migration 파일 해시를 작업 전후 읽기 전용으로 비교합니다. 민감한 자료는 접근이 제한된 Git 제외 증거 디렉터리에 보관합니다.

### 실제 실행 결과

2026-11-14 최종 검증:

- 전체 Django 테스트 **135개 중 133개 통과, 2개 제외**. 제외된 항목은 기존 preview 전용 SQL 차단 테스트입니다. 새 즐겨찾기 테스트 **14개 모두 통과**했으며, 서로 다른 DB 연결의 동시 요청 결과는 201/409와 단일 관계 행입니다.
- 기존 인증/이메일/아이/카테고리/활동지 및 실제 샘플 파일 관련 회귀 테스트 포함. 실제 자료는 격리 테스트의 임시 저장소에서 복사해 사용했고 개발 DB 자료는 수정하지 않았습니다.
- 스크립트 안전성 단위 테스트 **19개 모두 통과**.
- 격리 MySQL 및 개발 설정 system check: 통과. `makemigrations --check --dry-run`: 변경 없음.
- 개발 DB `migrate --plan`: favorites.0001_initial의 Favorite 생성 하나만 대기. `sqlmigrate`에서 신규 favorites 테이블/FK/UNIQUE 외의 기존 테이블 변경 없음 확인.
- 개발 DB 작업 전후 전체 스냅샷 일치: **22개 테이블·25개 migration**, 공개 활동지 4개 및 기존 API 응답 동일. favorites 테이블은 생성하지 않았고 개발 DB 즐겨찾기 데이터도 만들지 않았습니다.
- 원본 8개 및 기존 미참조 12개를 포함한 private_uploads 파일 20개 해시 동일. 기존 migration 파일 해시도 일치합니다.

전체 테스트/격리 서버 종료 증거: `.mysql-rehearsal/child-tests-b1b81eec791c/{test.txt,check.txt,makemigrations.txt,report.json}`.

개발 DB·파일 보존 증거: `.mysql-rehearsal/favorites-validation-58e2a0757979/{before.json,after.json}`. 이 점검만 개발 DB를 읽었으며, 전체 테스트 실행 도구는 개발 DB에 접근하지 않았습니다.

**코드 작성과 격리 검증은 완료했지만 개발 DB migration 적용 및 실제 개발 사용자 즐겨찾기 사용 검증은 실행하지 않았습니다.** 정책 확인과 승인된 적용 절차는 다음 단계에 남겨두었습니다. Git commit/push/PR/merge도 수행하지 않았습니다.

결제/주문/유료 상품/장바구니/구매 내역/추천/활동 완료 기록/관리자 화면 재구현은 범위 밖입니다.
