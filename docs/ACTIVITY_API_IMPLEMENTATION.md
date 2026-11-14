# 개별 활동지 관리 및 조회

> 2026-11-14 후속 작업에서 개발 DB에 `activities.0001_initial` 적용과 백업 복원 검증을 완료했습니다. 아래 미적용 표기는 최초 구현 시점의 기록이며, 현재 상태와 관리자/카테고리 준비 절차는 [활동지 DB 적용 결과](ACTIVITY_DB_DEPLOYMENT.md)를 참고하세요.

> 후속 작업에서 카테고리 2개 추가와 관리자 개월 수 표시 변경을 완료했습니다. 실제 자료 파일은 아직 없어 활동지 등록은 보류되어 있습니다. [등록 준비 결과](ACTIVITY_SAMPLE_REGISTRATION.md)에 최신 상태와 필요한 파일을 정리했습니다.

> 위 보류 상태는 해소되었습니다. 루트 폴더의 실제 파일로 활동지 4개를 등록·공개했고 HTTP 조회와 원본 바이트 일치를 검증했습니다. [최종 등록 결과](ACTIVITY_SAMPLE_IMPORT_RESULT.md)가 현재 상태입니다.

## 변경 범위와 기존 구조

`activities` 앱을 추가했습니다. 기존 accounts/email_verification/children/categories의 기능과 migration은 변경하지 않았습니다. 기존 JWT 설정 및 공통 `auth_exception_handler` 오류 형식을 재사용합니다. Child의 ActivityRecord는 아이 삭제 정책을 위한 기존 모델이며 이번 활동지 모델에 연결하거나 변경하지 않았습니다.

Activity는 제목, 설명, 최소/최대 개월 수, 난이도, 최소/최대 소요 시간, 가격, 표지, PDF, 공개 여부, 생성/수정 시각을 저장합니다. 기존 Category와 ActivityCategory(`activity_categories`)를 통한 다대다 관계이며 연결 중인 카테고리는 삭제로부터 보호됩니다. PDF와 표지는 DB에 파일 참조만 저장합니다.

가격 기본값은 0이고 모델 검증 및 DB CHECK 제약으로 다른 값을 거부합니다. QuerySet.update/bulk_create에도 DB 제약이 적용됩니다. 개월 수 및 시간 범위와 난이도에도 DB 제약이 있습니다. 카테고리 필수 선택은 관리자 폼에서 검증합니다(직접 ORM으로 만든 미연결 객체까지 금지하는 DB 제약은 없습니다).

## API

| 메서드 | URL | 동작 |
|---|---|---|
| GET | `/api/v1/activities` | 공개 활동지 목록 |
| GET | `/api/v1/activities/{activity_id}` | 공개 활동지 상세 |
| GET | `/api/v1/activities/{activity_id}/files/pdf` | 공개 PDF 스트리밍 |
| GET | `/api/v1/activities/{activity_id}/files/image` | 공개 표지 스트리밍 |

조회는 명세의 보안 요구가 없는 공개 GET 계약을 따라 비로그인 접근을 허용합니다. 토큰을 제공하면 기존 JWT 인증기가 검증하므로 잘못된 토큰은 401입니다. 관리 쓰기 REST API는 없습니다. 비공개 또는 없는 ID는 404이며 관리자라도 공개 조회 API에서는 비공개 파일을 받을 수 없습니다.

목록은 `count`, `next`, `previous`, `results` 구조입니다. 기본 page=1, page_size=20, 최대 100입니다. 유효하지 않은 쿼리는 400, 없는 페이지는 DRF 기준 404입니다. q는 제목/설명 부분 검색, category는 기존 정수 ID, age_years는 해당 나이의 개월 수 구간(5세=60~71개월)과 활동지 권장 개월 수 범위의 겹침, duration은 `5-10` 형태의 분 구간 겹침 필터입니다. difficulty, price_min, price_max도 지원합니다. sort는 latest(기본), oldest, title, price_asc, price_desc이며 ID로 동률을 해소합니다.

상세와 목록 항목은 기존 id/title/price/sale_status/description을 유지하고 age_min_months, age_max_months, difficulty, duration_min, duration_max, categories(정수 ID 배열), image, pdf(접근 제어 URL)를 추가합니다. 공개된 무료 자료는 기존 sale_status 예시인 on_sale으로 표시하며 결제 기능을 의미하지 않습니다.

### 미확정 정책 및 명세 확장

기존 v1.5 명세는 상세 5개 필드 이외의 메타데이터, 난이도 enum, 필터/정렬 세부 규칙 및 파일 URL 구조를 확정하지 않았습니다. 위 확장은 이번 요구사항을 충족하는 구현안이며 팀 정책 확정이 필요합니다. 하=easy, 상=hard만 우선 지원합니다. 중 난이도는 임의로 추가하지 않았습니다. popular는 순위 근거가 없으므로 400으로 거부하며 인기순을 다른 정렬로 대체하지 않습니다. 기존 category=painting 예시는 현 Category에 code가 없어 지원하지 않고 기존 카테고리 API의 정수 ID를 사용합니다. 원본 명세는 수정하지 않았습니다. 기존 구매 다운로드 권한 발급 API(`/download`)는 구현하지 않았습니다. 무료 공개 파일 URL은 이번 기능의 추가 경로입니다.

## 관리자가 활동지를 등록하는 순서

1. 관리자 계정으로 `/admin/`에 로그인합니다. 일반 회원은 접근할 수 없습니다.
2. **활동지 관리 → Activity → 추가**를 선택합니다.
3. 제목과 설명을 입력하고 최소 개월 수와 최대 개월 수를 입력합니다(예: 권장 연령: 만 5세 (60~65개월)).
4. 하 또는 상을 선택하고 소요 시간을 분으로 입력합니다. 정확히 5분이면 최소와 최대 모두 5를 입력합니다.
5. 기존 카테고리를 선택합니다. 목록이 비어 있으면 담당자에게 기존 카테고리 준비를 요청합니다. 임의의 ID를 입력하지 않습니다.
6. 표지(PNG/JPEG/WEBP)와 미리 분리한 개별 PDF를 각각 하나씩 선택합니다. 전체 놀이북을 자동 분리하지 않습니다.
7. 공개 여부를 선택하고 저장합니다. 가격은 읽기 전용 0원입니다. 공개하면 조회 API에 즉시 반영됩니다.
8. 수정하려면 목록에서 제목을 선택합니다. 파일을 새로 선택하면 교체되며 선택하지 않으면 기존 파일을 유지합니다. 공개 체크를 해제하고 저장하면 상세와 파일 URL도 404가 됩니다.

등록/수정에는 해당 Django 모델 권한이 필요합니다. 관리자 권한은 기존 Django Admin 권한 체계를 따릅니다. 비공개 파일의 관리자 미리보기는 제공하지 않습니다.

## 파일 저장과 접근 정책

기본 저장소는 별도 `STORAGES['activities']`이며 `private_uploads/activities/{UUID}.{확장자}`에 저장합니다. `ACTIVITY_PRIVATE_ROOT`로 위치를 지정할 수 있습니다. PDF는 20MiB, 이미지는 5MiB 제한이며 설정으로 조정할 수 있습니다. 확장자 및 PDF 헤더/종료 표식, Pillow의 실제 이미지 디코딩/검증을 사용합니다. MIME 헤더만 신뢰하지 않습니다. PDF 검사는 구조 전체의 유효성 검증이나 악성 코드 검사가 아니므로 운영 시 검사기 도입을 검토해야 합니다.

파일 이름은 UUID를 사용해 원본 이름 충돌과 경로 입력을 방지합니다. 저장소 url()은 직접 URL 발급을 거부합니다. 모든 파일 응답에서 공개 여부를 DB로 확인하며 attachment, nosniff, private/no-store를 사용합니다. 한 번 내려받은 파일이나 이미 시작한 전송을 공개 취소로 회수할 수는 없습니다.

교체·삭제한 기존 파일은 자동 삭제하지 않습니다. DB 롤백/공유 참조로 인한 손실을 피하기 위해 보존하며, 실패한 업로드 역시 고아 파일이 남을 수 있습니다. 보존 기간과 참조 확인 후 정리 절차는 운영 정책 확정이 필요합니다. 저장소는 Django Storage 인터페이스로 교체 가능하며 운영 저장소는 반드시 비공개 버킷이어야 합니다. 이 디렉터리에 MEDIA_URL, nginx alias, 공개 CDN을 연결하면 접근 제어가 우회되므로 금지합니다. 운영의 영구 볼륨/백업/HTTPS/업로드 프록시 제한 및 비공개 버킷 설정은 아직 검증되지 않았으며 운영 배포 준비 완료를 의미하지 않습니다.

## Migration 적용 계획

신규 파일은 `activities/migrations/0001_initial.py` 하나입니다. categories.0001_initial에 의존하며 activities/activity_categories 테이블과 CHECK/UNIQUE/FK 제약을 추가합니다. 기존 테이블 데이터 변경이나 예시 삽입은 없습니다.

**실제 개발 DB에는 적용하지 않았습니다.** 별도 승인 후 DB 백업과 대상 확인 → `showmigrations activities` / `migrate --plan` 검토 → 신규 migration 적용 → 관리자 등록/조회 확인 순서로 진행합니다. 기존 migration의 수정, fake, flush, 초기화는 필요하지 않습니다. MySQL DDL은 완전한 트랜잭션 롤백을 보장하지 않으므로 실패 시 생성된 구조를 확인한 뒤 대응해야 합니다.

## 예시 입력 자료

원본 PDF는 프로젝트에서 발견되지 않았습니다. 아래 정보는 요청문 기준이며 PDF 내용 검증이나 실제 DB 삽입을 수행하지 않았습니다. 각 PDF는 관리자가 직접 분리하여 준비합니다. 모두 60~65개월, 가격 0원입니다.

| 제목 | 원본 페이지 | 난이도 | 최소/최대 시간 |
|---|---|---|---|
| 단비와 보리의 징검다리 모험 | 3~9 | 하 | 5/5 |
| 단비와 보리의 숫자 놀이 | 10~18 | 상 | 10/10 |
| 단비랑 보리의 콩 놀이 | 19~27 | 상 | 5/5 |
| 단비와 보리의 공 놀이 | 28~36 | 상 | 15/15 |

신체운동·건강/자연탐구는 요청문의 후보 명칭입니다. 개발 DB의 실제 카테고리 내용은 조회하지 않았으므로 매핑을 확정하지 않았습니다. 관리자에서 실제 목록을 확인하여 선택해야 합니다.

## 검증과 후속 범위

테스트는 기존 `scripts/run_isolated_feature_tests.py --instance-dir .mysql-rehearsal/auth-api-d2ae7f54b9c0`를 가상환경 Python으로 실행합니다. 이 도구는 별도 MySQL 서버(33307)의 서버 ID/데이터 디렉터리/UUID를 확인하고 격리 테스트 DB에만 migration을 적용합니다. 개발 DB에 test/migrate를 실행하지 마세요.

활동지 테스트는 모델 제약, 업로드 형식/용량, 필터/검색/페이지네이션, 공개 파일 및 비공개 전환, 관리자 등록/수정/가격 변조 방지/일반 회원 거부를 검증합니다. 실행 결과는 작업 완료 보고 및 아래 결과 기록을 참고하세요.

2026-11-14 최종 실행: 전체 114개 중 112개 통과, 2개는 기존 preview 전용 SQL 차단 테스트여서 격리 설정에서 제외되었습니다. 신규 활동지 테스트 10개 및 기존 인증/아이 API 회귀 테스트가 통과했습니다. 격리 `check --database default`, `makemigrations --check --dry-run`도 통과했습니다. 결과는 `.mysql-rehearsal/child-tests-ff9912a20d0f/{test.txt,check.txt,makemigrations.txt,report.json}`에 있습니다. 서버 신원 확인 및 종료가 완료되었고 개발 DB에는 접근하지 않았습니다. 초기 실행에서 발견한 스트리밍 테스트의 연결 종료 및 Windows 파일 핸들/재검증 문제를 수정한 뒤 전체를 다시 실행한 결과입니다.

제외: 결제/PG/유료 상품/주문/장바구니/찜/추천/활동 완료 기록/PDF 자동 분리/프론트엔드. 후속 권장 순서는 미확정 계약 확정 → 승인된 개발 DB migration → 실제 PDF 등록 및 카테고리 매핑 → 운영 비공개 영구 저장소와 백업/파일 정리/악성 파일 검사 검증입니다.
