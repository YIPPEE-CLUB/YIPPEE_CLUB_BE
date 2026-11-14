# 아이 관리·공통 카테고리 API 개발 DB 적용 완료

2026-11-13 KST. 승인된 신규 migration 두 개만 실제 개발 DB에 적용했다.
최종 **20개 테이블, 24개 migration**이며 기존 원본 데이터와 인증 스키마/FK를 보존했다.
아이 관리·공통 카테고리 API를 개발 DB에서 사용할 수 있고 다음 기능 개발을 시작할 수 있다.
활동지 API 구현, 실제 테스트 데이터 생성, Git commit/push는 수행하지 않았다.

## 사전 확인

- `CHILD_API_IMPLEMENTATION.md`의 확정 계약과 categories/children migration을 검토했다.
- DB `yippee_club_db`, 계정 `yippee_app@localhost`, 포트 3306,
  UUID `5491c807-5688-11f1-a0bf-c86e08e6aa63`를 적용 전후 확인했다.
- 초기 16개 테이블/22개 migration 상태가 인증 API 적용 완료 당시의 전체 스냅샷과 일치했다.
- 기존 migration 파일은 Git HEAD와 바이트가 일치했다. 이번 작업 중 신규 migration도 수정하지 않았다.
- 관련 로컬 Django/worker/테스트 프로세스는 없었다. 현재 계정에 보이는 개발 DB 연결은 점검 연결뿐이었다.
  앱 계정으로 다른 계정의 전체 세션을 새로 확인했다고 주장하지 않는다.
  기존 쓰기 중지 유지 확인을 반영했고, 백업부터 적용 직전까지 source 전체 상태가 동일함을 검사했다.
- source 계획에는 categories.0001_initial, children.0001_initial만 포함됐다.
  기존 User 0001/0002나 인증 0003을 다시 적용하지 않았다.

## 새 백업과 독립 복원/업그레이드

증거 디렉터리: `.mysql-rehearsal/child-deploy-c8e16469dd12/`.
백업은 해당 폴더의 `yippee_club_db.sql`, 크기는 19,234 bytes다.

```text
SHA256: 4101a0aaca2067e0ffe7a7d87442f9bd145959c0fbb28ae97186da9a0858dd5f
```

기존 검증된 mysqldump 읽기 전용 옵션을 사용했다. 백업/자격정보는 Git 제외 폴더에서
실행 사용자와 SYSTEM만 접근하도록 보관했으며 비밀번호를 CLI 인자/로그에 출력하지 않았다.

기존 격리 MySQL을 재사용하고 server_id 9133307, 포트 33307, 기존 UUID와 datadir를 검사했다.
source 서버/DB와 별개임을 확인한 후 해당 인스턴스에 빈 `test_yippee_migration_legacy` 복원 스키마를
준비했다. 격리 서버의 전용 계정에 이 스키마 한정 권한을 부여했으며 개발 서버 권한은 변경하지 않았다.
기존 복원/테스트 스키마나 데이터를 삭제하거나 덮어쓰지 않았다.

백업을 복원한 뒤 전체 테이블/컬럼/제약조건/FK/모든 행 해시/migration 이력을 비교해 일치를 확인했다.
그 복원 DB의 계획에서도 신규 migration 두 개만 확인하고 적용하여 20개 테이블/24개 migration을 검증했다.
기존 suite DB에서 전체 테스트를 재확인하고 source가 바뀌지 않은 것도 확인했다.
완료 후 격리 인스턴스만 정상 종료했고 모든 데이터 디렉터리와 증거는 보존했다.

## 실제 실행 명령과 결과

아래 `python`은 `.\.venv\Scripts\python.exe`이며, 각 단계 결과를 확인하고 순서대로 실행했다.
모두 종료 코드 0이다. 실제 source DDL은 아래 migrate 적용 명령 한 번으로만 수행했다.

| 명령 | 실제 결과 |
|---|---|
| `python manage.py migrate --settings=config.settings --plan` | 신규 categories.0001/children.0001 두 개뿐 |
| `python scripts/prepare_child_api_deploy.py prepare` | 새 백업, 독립 복원 일치, 두 migration 업그레이드, 전체 회귀 테스트 PASS |
| `python scripts/prepare_child_api_deploy.py verify-before --evidence .mysql-rehearsal/child-deploy-c8e16469dd12` | source 식별자/16 tables/22 migrations/백업 시점 상태 일치 PASS |
| `python manage.py migrate --settings=config.settings --plan` | 적용 직전 계획도 같은 두 개뿐 |
| `python manage.py migrate --settings=config.settings --noinput` | categories.0001_initial OK, children.0001_initial OK |
| `python scripts/prepare_child_api_deploy.py verify-final --evidence .mysql-rehearsal/child-deploy-c8e16469dd12` | 20 tables/24 migrations, 전체 스키마/FK 및 원본 행 보존 PASS |
| `python manage.py check --settings=config.settings --database default` | System check identified no issues (0 silenced) |
| `python manage.py makemigrations --settings=config.settings --check --dry-run` | No changes detected |
| `python manage.py showmigrations --settings=config.settings` | 24개 모두 [X] |

## 실제 추가된 스키마와 보존 검증

- 적용 migration: `categories.0001_initial`, `children.0001_initial`.
- 새 테이블: `categories`, `children`, `child_interests`, `activity_records`.
- FK: children.user_id → accounts_user.id.
- FK: child_interests.child_id → children.id, category_id → categories.id.
- FK: activity_records.child_id → children.id.
- `(child_id, category_id)` unique 제약은 격리 업그레이드 결과와 동일하다.
- 기존 Admin FK `django_admin_log.user_id → accounts_user.id`와 모든 기존 FK를 유지했다.
- source의 최종 전체 테이블/컬럼/제약조건/행 건수는 같은 백업의 격리 업그레이드 결과와 일치했다.
- 이전 16개 테이블의 모든 원본 행 해시가 최종 데이터에 보존됐다.
- Django ContentType은 14건, auth_permission은 56건, migration 기록은 24건으로 추가됐다.
- 사용자/아이/카테고리/활동 기록/관심 연결/Admin 로그/Refresh/이메일 인증/속도 제한 데이터는 모두 0건이다.
- 새 백업 파일과 전체 migration 파일의 해시가 준비 시점부터 최종 검사까지 유지됐다.

## 통합 테스트

기존 격리 MySQL의 전용 `test_yippee_migration_suite`에서만 HTTP API 테스트를 수행했다.
source DB에서는 API 호출/테스트 사용자·아이·카테고리 생성을 하지 않았다.

- **95개 중 93개 성공, 0개 실패, 2개 skip**.
- 기존 인증 회귀 72개와 신규 아이/카테고리 23개를 포함한다.
- skip 2개는 실제 SQL을 금지하는 오프라인 설정 전용 검사다.
- 정상 CRUD/JWT/소유권/관심사 ID 검증/NULL 계약/M2M unique/삭제 CASCADE 및 rollback을 포함한다.
- 로그: 증거 디렉터리의 `migrate-plan.txt`, `migrate.txt`, `test.txt`, `report.json`.
- 최종 source 스냅샷: `verify-final.json`. 실제 운영 HTTP 성공을 테스트 데이터로 입증한 것은 아니며,
  기존 인증 스키마 보존과 격리 환경의 정상·오류 회귀 테스트로 검증했다.

## 현재 범위와 다음 작업

아이 관리 5개와 공통 카테고리 조회 1개, 기존 인증 12개 operation의 DB 준비가 완료됐다.
서버를 자동 재시작하지 않았다. 실제 카테고리 목록이 미확정이므로 비즈니스 데이터를 임의로 넣지 않았다.

정수 카테고리 ID/{id,name}, 아이 목록 {results:[...]}, PATCH name/birth_date null 400 및
gender/interests null 초기화는 사용자가 확정한 계약을 유지한다.
카테고리 초기 목록, 성별 enum, 연령 경계, 사진 저장/정리 정책은 별도 확정이 필요하다.
현재 ActivityRecord는 id/child FK만 가진 최소 관계 모델이다. 활동지/기록 작성 API는 아직 구현하지 않았다.
주문/결제 모델이나 삭제 로직은 추가하지 않았다.

이번 작업은 DB 적용과 검증·기록에 한정했다. 신규 운영 검증 도구
`scripts/prepare_child_api_deploy.py`를 추가했고 모델/serializer/view/URL 및 기존 migration은 변경하지 않았다.
활동지 API는 다음 작업으로 남겨둔다. `test_yippee_club_db`, `team3_db`에는 접근하지 않았으며
DB 삭제/초기화/fake/기존 migration 수정/Git commit/push는 수행하지 않았다.
