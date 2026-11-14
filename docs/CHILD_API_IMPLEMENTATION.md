# 아이 관리·공통 카테고리 API 구현

> 최신 상태: [개발 DB 적용 완료 기록](CHILD_API_DEPLOYMENT.md).
> categories.0001/children.0001 적용과 최종 검증을 완료했다. 현재 20개 테이블/24개 migration이다.
> 아래 미적용/후속 적용 설명은 최초 구현 시점의 기록이며 현재 적용 결과는 최신 기록을 따른다.

## 범위와 현재 상태

기준 원본은 [API_SPEC_v1.5.md](API_SPEC_v1.5.md)의 0절 및 20~24/37번,
[openapi_v1.5.yaml](openapi_v1.5.yaml)이다. 원본 명세는 수정하지 않았다.
기존 accounts.User, SimpleJWT 인증, IsAuthenticated, 공통 오류 구조 및 StrictSerializer를 재사용한다.
인증 API 코드와 기존 migration은 수정하지 않았다.

새 migration은 격리 MySQL에만 적용했다. **개발 DB에는 이번 작업에서 연결하거나 migration/
테스트 데이터를 적용하지 않았다.** 개발 DB에서 이 API를 사용하려면 후속 적용 단계가 필요하다.
Git commit/push는 실행하지 않았다. 작업 전부터 있던 로컬 운영 도구는 그대로 보존했다.

## 구현한 API

모든 경로는 JWT 인증이 필요하고 후행 slash가 없다. 카테고리 조회의 인증은 원본의 공개 조회
표기보다 이번 작업의 명시적 JWT 요구를 우선했다. 인증 누락/무효/만료 토큰은 401이다.

| Method | URL | 성공 응답 |
|---|---|---|
| GET | /api/v1/children | 200: {results: [아이 객체, ...]} |
| POST | /api/v1/children | 201: 아이 객체 |
| GET | /api/v1/children/{child_id} | 200: 아이 객체 |
| PATCH | /api/v1/children/{child_id} | 200: 아이 객체 |
| DELETE | /api/v1/children/{child_id} | 204, 본문 없음 |
| GET | /api/v1/activity-categories | 200: {results: [{id, name}, ...]} |

아이 객체는 id/name/birth_date/gender/interests만 반환한다. interests는 공통 카테고리 정수 ID 배열이다.
user/user_id/id 등 소유권·읽기 전용 필드의 입력은 400으로 거부하며 소유자는 서버의 request.user로 정한다.
목록과 상세 조회 모두 DB queryset에서 소유자 필터를 적용한다. 타 사용자 아이의 조회/수정/삭제는
없는 아이와 같은 404 응답으로 처리하고 별도 IsChildOwner object permission도 적용한다.

추가 독립 카테고리 API는 v1.5에 정의되어 있지 않다. 카테고리 생성/수정/삭제 HTTP API,
추천·활동지 필터 API, active-child 선택 API는 이번 범위에 추가하지 않았다.
카테고리 입력은 기존 Django Admin 체계에서 권한 있는 관리자가 수행할 수 있다.
실제 목록이 미확정이므로 임의 카테고리 seed/data migration은 만들지 않았다.

## 사용자가 확정한 보완 계약

다음 세 항목은 후속 사용자 답변으로 확정됐다. 원본 명세 파일은 수정하지 않고,
원본의 공백/충돌에 대한 보완 계약을 여기에 기록한다.

1. 카테고리 타입/항목 구조: 정수 id와 {id, name}을 사용한다.
2. 아이 목록: 원본 20번이 목록에도 단일 객체를 기재하고 있어 {results: [...]}로 다중 아이를 반환한다.
   페이지 파라미터가 정의되지 않은 이 API에는 별도 pagination을 추가하지 않았다.
3. PATCH null: 원본 요청은 nullable, 응답은 non-null로 충돌한다. name/birth_date의 null은 400으로 거부하고,
   gender/interests의 null은 각각 빈 문자열/빈 배열로 초기화한다. 누락 필드는 모두 유지한다.

기타 미확정 정책:

- 카테고리 실제 이름/초기 목록은 미확정이다. 빈 목록을 정상 반환한다.
- 성별 enum은 원본에서도 제안 상태라 string 타입만 검사한다. 임의 enum이나 기본 성별은 만들지 않는다.
- 12~72개월의 기준 시각/경계/기존 계정 정책은 미확정이므로 나이 제한을 추가하지 않았다.
  유효한 날짜와 미래가 아닌 생년월일만 검사한다. 생성 시 name/birth_date는 필수/non-null이다.
- 사진 파일 저장·정리 정책은 미확정이고 현재 활동 기록에는 파일 필드/파일이 없다.
  임의 스토리지 삭제나 비동기 작업을 추가하지 않았다.

## 모델과 관계

| 모델 / 테이블 | 관계와 제약 |
|---|---|
| categories.Category / categories | 공통 카테고리, 정수 PK 및 name |
| children.Child / children | user FK → accounts.User, name/birth_date/gender |
| children.ChildInterest / child_interests | child FK CASCADE, category FK PROTECT, (child, category) unique |
| children.ActivityRecord / activity_records | child FK CASCADE, 최소 기록 식별자 |

Child.interests는 ChildInterest를 통한 Category M2M이다. 활동지 기능도 반드시 이 Category를 참조해야 하며
별도의 활동지 전용 카테고리 목록/모델을 중복 생성하지 않는다. 현재 활동지 모델/API는 아직 없으므로
activity_categories 연결 테이블이나 가짜 활동지 모델을 선행 생성하지 않았다.

ActivityRecord는 아직 없던 활동 기록 관계에서 실제 삭제 정책을 검증하기 위한 최소 모델이다.
현재 필드는 id/child뿐이며 기록 작성 API·activity FK·reaction/memo/사진 등은 활동 기록 개발 단계에서
추가 migration과 명세 검토가 필요하다. 기록 API를 구현했다고 보고하지 않는다.

등록/수정은 atomic transaction 안에서 카테고리를 잠그고 존재 여부를 확인한다.
중복 ID, 없는 ID, 다른 타입/음수/0/범위를 벗어난 ID는 400으로 거부한다.
성공한 수정은 interests를 요청 집합으로 교체하며 실패 시 아이 속성과 M2M 모두 보존한다.

아이 삭제는 잠근 본인 객체의 ORM delete만 수행한다. ChildInterest와 ActivityRecord는 ORM CASCADE로
함께 삭제되며 전체 동작은 atomic이다. 사용자·공통 카테고리·다른 아이/기록·인증 세션은 삭제하지 않는다.
주문/결제 모델은 현재 없고 관련 삭제 코드는 추가하지 않았다. 향후 금융 데이터의 child/record 참조는
삭제·보존 정책을 별도 설계해야 하며 이 CASCADE 경로에 주문/결제를 연결하면 안 된다.

## 변경 파일과 migration

- 신규 categories 앱: models/admin/serializer/view/URL 및 앱 설정.
- 신규 children 앱: models/serializer/view/permission/URL/tests 및 앱 설정.
- config/settings.py: 두 앱 등록. config/urls.py: 두 URL 모듈 연결.
- 신규 migration: categories/migrations/0001_initial.py, children/migrations/0001_initial.py.
  children은 categories.0001 및 swappable AUTH_USER_MODEL 의존성을 가진다.
- scripts/run_isolated_feature_tests.py: 기존 격리 MySQL 인스턴스를 재사용하는 테스트 실행기.
- 이 구현 기록.

기존 migration과 명세 파일의 내용/바이트는 검증 시 HEAD/원본 SHA256과 일치했다.
새 migration을 만들 때 MigrationLoader(None)/MigrationAutodetector를 사용해 DB 연결 없이 생성했다.

## 테스트 결과

기존 인증 테스트에 사용한 격리 서버의 UUID/datadir/server_id/포트를 확인하고 재사용했다.
개발 DB 백업이나 User 이관 리허설, MySQL 초기화를 반복하지 않았다.
테스트 DB는 해당 인스턴스의 test_yippee_migration_suite이며 --keepdb로 실행했다.
금지된 기존 test_yippee_club_db 및 team3_db에는 접근하지 않았다.

```powershell
.\.venv\Scripts\python.exe scripts/run_isolated_feature_tests.py --instance-dir .mysql-rehearsal/auth-api-cad00793f0c4
```

- 새 migration 두 개만 해당 격리 테스트 DB에 정상 적용했다.
- 전체 **95개 중 93개 성공, 0개 실패, 2개 skip**. 신규 아이/카테고리 테스트 23개와 기존 인증 회귀 72개 포함.
- skip 2개는 SQL 금지 오프라인 설정 전용 검사다. 오프라인 실행에서는 관련 검사 포함 34개 전부 통과했다.
- 격리 Django check: 문제 없음. makemigrations --check --dry-run: No changes detected.
- 정상 CRUD/복수 아이/소유자 목록, 누락·무효·만료 JWT, 타인 GET/PATCH/DELETE 404,
  필드 주입 거부, 날짜/관심사 검증, M2M DB unique 제약, 부분 수정/null/교체/실패 원자성,
  삭제 CASCADE 및 다른 아이/기록·User/Category/세션 보존, 삭제 중 오류 rollback을 검증했다.
- 주문/결제 실데이터 및 사진 파일 정리는 모델/스토리지가 아직 없어 통합 검증하지 않았다.
- 후속 확정 계약 반영 후 전체 95개를 다시 실행해 같은 성공/skip 결과를 확인했다.
  name/birth_date에 각각 null을 보내면 400이며 gender/interests를 포함한 변경이 저장되지 않는 것,
  gender/interests만 null로 보내면 정상 초기화되는 것을 검증했다.
- 최신 결과 로그/서버 정상 종료 증거: .mysql-rehearsal/child-tests-13b21870af60/.
  최초 실행 증거 .mysql-rehearsal/child-tests-ca95be2189b5/도 보존했다.

## 실제 개발 DB 후속 적용 — 이번 작업에서는 실행하지 않음

확정된 보완 계약을 반영했으며 카테고리 실제 목록은 추가로 준비해야 한다. 이어 쓰기 중지, 대상 식별자 확인,
새 백업·독립 복원/upgrade 검증 후 별도 승인 범위에서 실행한다.

```powershell
python manage.py migrate --settings=config.settings --plan
# 예상: categories.0001_initial, children.0001_initial 두 개뿐인지 검토.
python manage.py migrate --settings=config.settings --noinput
python manage.py check --settings=config.settings --database default
python manage.py makemigrations --settings=config.settings --check --dry-run
python manage.py showmigrations --settings=config.settings
```

개발 DB가 기존 16개 테이블/22개 migration 상태라면 적용 후 **20개 테이블/24개 migration**이 예상된다.
신규 테이블 네 개와 모델의 ContentType/permission이 추가되며 기존 auth/User/이메일 인증 테이블은
변경하거나 초기화하지 않는다. 새 API는 migration 승인/적용 이후에 개발 DB에서 사용할 수 있다.
