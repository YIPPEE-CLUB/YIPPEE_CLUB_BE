# 아이 선택 API 신규 migration 개발 DB 적용 준비 및 보류 결과

> **최신 상태 (2026-11-15): accounts.0004 개발 DB 적용 및 보존 검증 성공.** 테이블 25개·migration 29개, active_child_id/FK/인덱스 생성 완료. 사용자 관리자 조회 및 점검 창 유지 확인 후 앱 계정으로만 적용했다. 자세한 최종 결과는 **13절**을 따른다. 아래 1~12절의 보류·대기 기록은 당시 이력이며 삭제하지 않았다.

2026-11-15 (Asia/Seoul).

**적용 결과: 안전 조건 미충족으로 실제 개발 DB 적용 보류.** 사용자가 ‘중지 여부를 확인할 수 없으므로 실제 적용은 보류합니다’를 선택했다. 이에 따라 개발 DB에 `accounts.0004_user_active_child`를 적용하지 않았으며 자동 재시도하지 않는다. 승인된 범위의 읽기 전용 사전 확인·새 백업·격리 복원/migration/회귀 검증만 수행했다.

## 1. 작업 전 Git 및 코드 상태

- 브랜치 `dev`, HEAD `2af4c38153dd35ae3b42a98230ebe5574c2ee4c2`.
- 기존 수정: accounts/models.py, children/serializers.py, children/urls.py, children/views.py.
- 기존 미추적: accounts/migrations/0004_user_active_child.py, children/test_active_child.py, docs/ACTIVE_CHILD_API_IMPLEMENTATION.md, docs/API_V1_5_IMPLEMENTATION_AUDIT.md.
- 위 파일을 삭제하거나 덮어쓰지 않았다. 이번에 기능 코드/기존 migration을 수정하지 않았다.
- 이전 최종 169개 회귀 실행의 `active-child-source-hashes.json`과 현재 기존 Python 코드·migration·설정·.env 해시가 일치했다. 최초 보조 비교에서 Windows 경로 구분자 차이를 정규화한 뒤 내용 변경이 없음을 확인했다.
- 신규 migration은 AddField 한 개이며 accounts.0003 및 children.0001에 의존한다. nullable·editable=False·Django SET_NULL FK이며 기존 선택 API 구현도 보존했다.

## 2. 실제 개발 DB 사전 점검

| 항목 | 확인 결과 |
|---|---|
| DB | yippee_club_db |
| 접속 대상 | 127.0.0.1:3306 |
| DB 계정 | yippee_app@localhost |
| 서버 UUID | 5491c807-5688-11f1-a0bf-c86e08e6aa63 |
| MySQL | 8.0.46 |
| 테이블 | 25개 |
| 적용 migration | 28개 |
| 미적용 계획 | accounts.0004_user_active_child 하나, forward |
| 사용자 / 아이 | 0 / 0 |
| 활동지 / 카테고리 | 4 / 2 |
| 찜 / 장바구니 / 구매 권한 | 0 / 0 / 0 |
| active_child_id | 개발 DB에 아직 없음 |

기존 전체 DB 스냅샷은 직전 장바구니 적용 증거 `.mysql-rehearsal/cart-deploy-1f7fdfc90b4f/apply-report.json`의 최종 상태와 정확히 일치했다. 기존 테이블/컬럼/행 해시/PK·인덱스·FK/migration 이력이 동일했다. User PK 및 Child.user FK 변경은 없었다. 활동지 공개 API와 기존 파일 해시도 같았다.

**테이블명 주의:** 요청문은 `children_child`라고 표기했지만 실제 기존 Child 모델의 db_table과 개발 DB 테이블은 **children**이다. 신규 migration도 children.id를 참조한다. 기본 테이블명으로 바꾸거나 가짜 children_child 테이블을 만들지 않았다.

개발 DB 연결은 기존 서버 식별자 검증 및 읽기 전용 트랜잭션으로 수행했다. .env 본문·DB 비밀번호·백업 내용은 출력하지 않았다. CART_PURCHASE_ENTITLEMENTS_VERIFIED=False를 유지했다.

## 3. 실제 적용을 보류한 안전 조건

- 로컬 서버/worker 후보 프로세스를 읽기 전용으로 조회했으며 조회 시점에 후보가 없었다. 최초 OS 프로세스 조회는 샌드박스 권한으로 거절되어 승인된 읽기 전용 조회로 재확인했다. 명령줄 원문이나 비밀값은 출력하지 않았다.
- yippee_app에는 전역 PROCESS/전체 세션 조회 권한이 없다. PROCESSLIST에서 확인할 수 있었던 것은 점검 연결 한 개뿐이며, 이를 다른 계정의 연결/쓰기까지 없다는 증거로 해석하지 않았다.
- 스냅샷이 여러 시점에 동일하다는 사실만으로 모든 writer가 중지됐음을 증명할 수 없다.
- 사용자에게 ‘모든 DB 쓰기를 중지하고 완료까지 유지할 수 있는지’를 확인했으나 **중지 여부 확인 불가·실제 적용 보류** 답변을 받았다.

따라서 실제 개발 DB apply 조건이 충족되지 않았다. DB 전체 읽기 전용 전환, 계정 잠금/권한 변경, 세션 강제 종료 등 승인 범위 밖 조치는 하지 않았다. 백업/격리 검증 성공이 이번 보류 결정을 자동으로 해제하지 않는다.

## 4. 최신 백업 및 복원 검증

증거 디렉터리: `.mysql-rehearsal/active-child-deploy-7ad71f2449b2/`.

- 새 전체 백업: `yippee_club_db.sql`, **32,317 bytes**.
- SHA-256: `eae285b25c3b50880166e04ad097c09f62d5159baba12985c60438ce3516507d`.
- 기존 백업/증거를 덮어쓰거나 삭제하지 않았다. 새 접근 제한 디렉터리에 백업·자격증명·증거를 보관했으며 모두 Git 추적에서 제외된다.
- mysqldump single-transaction/skip-lock-tables를 사용했고 원본 DB에 DDL/DML을 실행하지 않았다.
- 기존 전체 CREATE TABLE/컬럼/인덱스/PK·FK/행 수·해시/migration 이력을 `report.json`에 보관했다. SHOW CREATE TABLE의 인덱스 정의도 함께 비교했다.
- private 파일 20개의 독립 복사본을 만들고 해시를 비교했다. 원본 자료 8개 및 실제 저장 파일 해시는 전후 비교 대상에 포함했다.
- **새 datadir**의 MySQL을 초기화하고 port 33307, server_id 9133307, 정확한 datadir, 개발 DB와 다른 UUID를 확인한 후에만 격리 스키마를 만들었다.
- 빈 새 인스턴스에 test_yippee_migration_fresh를 생성한 뒤 백업을 복원했다. 이전 datadir/기존 공유 테스트 DB는 사용하지 않았다.
- 복원본의 전체 25개 테이블/컬럼/스키마·인덱스/FK/행 해시/28개 migration 이력이 원본 사전 스냅샷과 완전히 일치했다.

## 5. 격리 migration 리허설

격리 복원 DB의 계획이 accounts.0004 하나인지 확인한 뒤 표준 Django 명령으로 적용했다.

```powershell
.venv/Scripts/python.exe manage.py migrate accounts 0004_user_active_child --noinput --settings=config.active_child_deploy_rehearsal
```

이 명령의 연결은 새 격리 DB에 한정된다. UUID/datadir/port/server_id/DB명/user를 연결 시 확인하고 기존 rehearsal SQL guard도 재사용한다.

실제 검토 및 리허설 SQL:

```sql
ALTER TABLE `accounts_user`
  ADD COLUMN `active_child_id` bigint NULL,
  ADD CONSTRAINT `accounts_user_active_child_id_6b38fe1e_fk_children_id`
    FOREIGN KEY (`active_child_id`) REFERENCES `children` (`id`);
```

MySQL이 FK에 필요한 active_child_id 인덱스를 생성했음을 확인했다. 기존 User 컬럼/PK/인덱스/제약은 새 필드·FK·인덱스만 제외하면 같았다. 기존 User 컬럼을 projection한 행 해시·행 수도 동일했다. 개발 DB에 실제 사용자가 없으므로 이 복원본의 ‘기존 사용자 NULL’ 검사는 빈 집합에 대한 검사이며, 데이터가 있는 업그레이드 동작은 회귀의 별도 migration 테스트로 보완한다.

다른 서비스 테이블은 스키마와 전체 데이터 해시가 완전히 동일했다. Child.user FK를 포함한 기존 FK를 보존하고 새 FK 하나만 추가됐다. django_migrations는 기존 28개를 유지하고 accounts.0004 한 행만 늘었다. AddField이므로 ContentType/Permission 등 기존 metadata의 추가/변경은 없었다.

| 대상 | 적용 전 | 격리 적용 후 |
|---|---:|---:|
| 테이블 | 25 | 25 |
| migration 이력 | 28 | 29 |
| accounts_user.active_child_id | 없음 | bigint NULL, children.id FK, 인덱스 |
| 기존 업무 행/컬럼/관계 | 기준 스냅샷 | 보존 |

## 6. 전체 회귀 및 Django 검증

회귀는 복원 보존본과 별도의 **새 test_yippee_migration_suite**를 생성해 실행하고 제거한다. --keepdb는 사용하지 않는다. 개발 DB에는 사용자·아이·선택 상태를 만들지 않는다.

이번 새 격리 실행의 최종 결과:

| 검증 | 결과 |
|---|---|
| 전체 회귀 | **169개 중 167 통과, 실패/오류 0, 기존 preview 전용 2개 제외** |
| 신규 아이 선택 | **18개 모두 통과** (전체 169개에 포함) |
| 데이터가 있는 0004 업그레이드 테스트 | 사용자/아이/기록 보존, 기존/신규 사용자 선택 NULL·실제 FK 확인 |
| 선택 API·소유권 | 성공/변경/반복, 타인/없는 ID·아이 없음·JWT/입력 검증 통과 |
| 삭제·정합성 | Django SET_NULL·기존 기록 CASCADE·rollback·동시 선택/삭제 경합·다른 서비스 데이터 보존 통과 |
| Django check --database default | 새 격리 DB에서 오류 없음 |
| makemigrations --check --dry-run | 새 격리 DB에서 No changes detected |
| 복원 보존본 | 테스트 전후 스키마·데이터·User projection 해시 동일 |
| 개발 DB | 사전/최종 전체 스냅샷 동일, 미적용 계획 0004 하나 유지 |
| 실제 자료 파일 | 기존 private 20개·원본 자료 8개 해시 보존 |
| 종료 | 새 테스트 스키마 제거, 격리 MySQL 정상 종료 |

report.json의 preparation_success=true, development_applied=false, apply_deferred_by_user=true, isolated_server_shutdown=true를 확인했다. 이는 **준비 검증 성공**이지 개발 DB 적용 성공이 아니다. 테스트에는 기존 인증/이메일/JWT/프로필/아이/공통 카테고리/활동지·파일·Admin/찜/장바구니/구매 권한 회귀가 포함된다. 실제 SMTP/PG나 개발 DB의 POST/PUT/DELETE 검증은 하지 않았다.

## 7. 실제 개발 DB 적용 및 적용 후 상태

**실제 적용 명령은 실행하지 않았다.** 개발 DB에 active_child_id가 생겼다거나 API 25가 사용 준비됐다고 주장하지 않는다. showmigrations의 미적용 항목을 --fake로 맞추거나 다른 migration을 적용하지도 않았다.

| 개발 DB 항목 | 작업 전 | 작업 후 |
|---|---:|---:|
| migration | 28 | 28 |
| 테이블 | 25 | 25 |
| accounts.0004 | 미적용 | 미적용 유지 |
| active_child_id | 없음 | 없음 유지 |

동시 쓰기 중지가 확인되지 않아 작업 후 상태도 마지막 읽기 시점의 관측값일 뿐 향후 외부 변경을 막았다는 뜻이 아니다.

## 8. 생성·변경 파일 및 Git

이번 단계에서 새로 생성한 파일:

- `config/active_child_deploy_rehearsal.py`: 새 격리 인스턴스와 복사 파일 경로를 검증하는 설정.
- `scripts/prepare_active_child_deploy.py`: 읽기 전용 사전 확인/백업 및 새 격리 복원/migration/회귀 준비 도구. **개발 DB 적용 기능은 없다.**
- `docs/ACTIVE_CHILD_DB_DEPLOYMENT.md`: 본 준비·보류 기록.

기존 기능 코드·accounts/children의 기존 migration·.env·자료 파일·기존 미커밋/미추적 작업은 보존했다. 이번 도구/설정 추가 외에 기존 파일을 수정하지 않았다. Git stage/commit/push/PR/merge/branch 변경은 수행하지 않았다.

보호된 증거 디렉터리의 주요 파일은 report.json(전후 스냅샷/백업/리허설), git-status.txt, plan.txt, sql.txt, migrate.txt, test.txt, check.txt, makemigrations.txt 및 백업/새 datadir/독립 파일 복사본이다. 비밀 자격증명과 DB 백업은 보고서/커밋 대상에 복사하지 않는다.

## 9. 다음 조치 및 운영 주의사항

1. 사용자가 실제 개발 DB의 앱·worker·DB 클라이언트·자동 writer를 중지하고 적용 완료까지 유지할 수 있는 상태를 먼저 마련해야 한다. 현재 보류 지시는 유지한다.
2. 이후 별도 재개 지시가 있으면 DB 식별/코드·migration 해시/현 DB 스키마·데이터·이력/단일 적용 계획과 백업 유효성을 다시 확인해야 한다. 상태가 달라졌다면 이번 준비 증거로 자동 적용하지 않는다.
3. 실제 적용 때도 표준 Django migrate accounts 0004 하나만 허용하고, 25개 테이블·29개 migration·새 FK·인덱스·기존 User projection 데이터와 다른 서비스 전체 보존을 재검증한다. 이 문서는 적용 명령을 지금 실행하라는 지시가 아니다.
4. **새 User 모델 코드와 미적용 DB로 인증/User ORM을 서비스하면 컬럼 부재 오류가 날 수 있다.** migration 전에는 API 사용/서비스 재시작을 완료 상태로 간주하지 않는다.
5. Python 3.12 실행 검증은 별도 과제다. 이번 로컬은 Python 3.13.3/Django 5.2.19/MySQL 8.0.46이다. 구매 권한 설정 False는 그대로 유지한다.

## 10. 2026-11-15 재개 점검 — 실제 적용 재보류

사용자가 이전 보류 원인을 더 조사하고 객관적인 안전 조건이 확보된 경우에만 0004를 적용하도록 요청했다. 이전 기록은 보존하고 이번 결과를 추가한다. **최종 결과는 안전 조건 미충족으로 보류이며 실제 migrate 명령은 실행하지 않았다.**

### 10-1. 코드·DB·백업의 독립 재확인

이번 재개 점검의 새 증거: `.mysql-rehearsal/active-child-resume-e604347b0c53/report.json`. 실제 적용 없음, 사전/최종 스냅샷 동일, 백업 구조/해시·기존 검증 성공과 writer 판단 한계를 기록했다. 이전 증거는 수정하지 않았다.

- 브랜치 dev, HEAD `2af4c38153dd35ae3b42a98230ebe5574c2ee4c2`, 기존 수정/미추적 파일 목록 그대로다.
- 현재 전체 DB·파일·공개 활동지 응답·migration 파일 스냅샷이 이전 준비의 before/after와 정확히 일치했다. Python 코드/설정/.env 해시도 당시 code_hashes와 일치했다. 실제 .env 내용은 출력하거나 변경하지 않았다.
- DB 이름·계정·서버 UUID·접속 대상은 위 2절과 동일하다. active_child_id는 아직 없고 적용 이력 28개, 테이블 25개, 전체 pending plan은 accounts.0004 하나다.
- 신규 migration은 이전과 같은 단일 AddField/SQL이며 기존 accounts/children migration도 불변이다.
- 기존 백업 32,317 bytes 및 SHA-256 `eae285b25c3b50880166e04ad097c09f62d5159baba12985c60438ce3516507d`를 다시 확인했다. 25개 CREATE TABLE과 dump 완료 표식도 확인했다. 이 구조 검사만으로 복원을 보장한다고 판단하지 않고, 같은 바이트 백업의 기존 독립 복원 완전 일치·0004 리허설 성공 증거와 함께 검증했다.
- 이전 report.json의 preparation_success/restore_exact/isolated_server_shutdown과 test.txt의 169개·OK(skipped=2)를 다시 확인했다. **이번 재개 점검에서 회귀/복원을 재실행하지 않았다.** 현재 DB와 백업 시점이 동일하고 기존 증거가 유효해 새 백업/새 리허설을 반복하지 않았다. 기존 백업/격리 datadir도 수정하거나 재사용하지 않았다.

### 10-2. 동시 writer 조사: 확인된 사실

| 조사 | 실제 관측 결과 |
|---|---|
| 로컬 프로세스 | Python/Node/Celery/Gunicorn/Uvicorn/Daphne/MySQL 클라이언트/Workbench/Java/PHP/dotnet/주요 DB GUI 후보에서 mysqld 두 프로세스만 관측. 후보 앱·worker는 없음. 두 mysqld의 명령줄은 보이지 않아 임의로 역할을 확정하지 않음 |
| Windows 서비스 | MySQL80 실행 중. 서비스/프로세스를 중지하지 않음 |
| 예약 작업 | 실행 파일/인수에서 python/mysql/node/celery 또는 프로젝트명·manage.py와 일치하는 작업은 관측되지 않음. 모든 범용 스크립트의 내부 동작까지 분석한 것은 아님 |
| 실제 수신 포트 | PID 6216이 `[::]:3306`, `[::]:33060`에서 Listen |
| MySQL 설정 | bind_address=*, mysqlx_bind_address=*, skip_networking=OFF, event_scheduler=ON |
| 네트워크 | 활성 네트워크 프로필 Public, IPv4 Internet. 이 값만으로 외부 DB 접속 가능성을 확정하지 않음 |
| Windows 방화벽 기본값 | Domain/Private/Public 모두 ON, 기본 BlockInbound/AllowOutbound |
| 명시적 허용 규칙 | `Port 3306`, `Port 33060` 규칙은 Enabled, Inbound Allow, Domain/Private/Public, RemoteIP Any, LocalIP Any |
| 전역 연결 수 | Django 점검 연결을 닫고 전용 읽기 연결만 사용한 반복 관측에서 Threads_connected=1. 제한된 PROCESSLIST에도 점검 연결 한 개만 보임 |
| 실행 스레드 수 | Threads_running=2 관측. 이를 사용자 writer 두 개라고 해석하지 않음. 내부/스케줄러 작업과 연결 수는 서로 다른 지표 |
| 대상 스키마 이벤트 | 현재 계정이 조회한 yippee_club_db의 이벤트 0개. 이벤트 스케줄러 자체는 ON |

관측 중 **확인된 앱 writer는 없고, 강제 종료하거나 새로 중지한 writer도 없다.** 남아 있는 활성 writer가 확인됐다고 주장하지 않는다. 그러나 전체 인터페이스 수신과 모든 원격 IP 허용 규칙 때문에 로컬 전용·외부 접근 차단 조건이 입증된 것도 아니다. 공유기/NAT/외부 네트워크에서 실제 도달 가능하다는 테스트는 수행하지 않았다.

### 10-3. 현재 권한으로 확인할 수 없는 사항

- mysql.user의 계정 Host/잠금 범위: SELECT 거부(1142). 따라서 localhost 계정만 존재하는지, 다른 원격 writer 계정이 허용되는지 확인 불가.
- performance_schema.threads의 전체 foreground 연결: SELECT 거부(1142).
- information_schema.INNODB_TRX의 전체 활성 트랜잭션: PROCESS 권한 부족(1227).
- 다른 계정/스키마의 자동 작업이 대상 DB를 변경할 수 있는 범위, 숨겨진/범용 예약 스크립트, 다른 기기의 재접속/향후 쓰기 중지 상태는 확인 불가.
- PowerShell 포트별 ActiveStore 방화벽 조회는 권한 부족으로 실패했지만, 읽기 전용 netsh 출력으로 위의 명시적 두 허용 규칙을 확인했다. 조회 권한 실패를 ‘방화벽 차단’으로 오판하지 않았다.

전역 Threads_connected는 계정 제한 PROCESSLIST보다 보완적인 증거이며 **관측 순간의 다른 접속 부재**를 뒷받침한다. 하지만 새로운 원격 연결/자동 작업이 migration 중 생기지 않도록 중지됐다는 증거는 아니다. 기존 계정의 실제 접근 범위와 writer 중지·유지 확인이 없는 현재 조건에서는 안전 요건 9번을 충족하지 못한다.

### 10-4. 최종 10개 조건 판정

1~8번(DB 식별·미적용·단일 계획·파일 불변·데이터 동일·유효 백업·복원/리허설)은 기존 증거와 이번 재확인으로 충족했다. 9번 **동시 writer 중지의 충분한 근거**는 미충족이다. 10번은 마지막 읽기 스냅샷까지 동일했지만 ‘적용 직전’ 단계로 진행하지 않았으므로 실제 적용 조건 충족으로 판정하지 않았다.

실제 DB는 **테이블 25→25, migration 28→28**, accounts.0004 미적용·active_child_id 없음이다. 기존 활동지 4개·카테고리 2개 및 전체 업무 데이터/스키마/파일 해시는 동일했다. 이번에는 적용 후 새 FK·인덱스·29개 이력을 만들거나 생성됐다고 보고하지 않는다. Django DB 연동 사후 검사는 적용하지 않았으므로 재실행하지 않았고 기존 격리 check/makemigrations 성공 증거만 재확인했다.

### 10-5. 필요한 최소 추가 조치

관리자 비밀번호 변경, PROCESS 권한 부여, 서버 read_only 변경이나 전체 MySQL 중지는 이번 판단에 필수로 요구하지 않는다. 먼저 **DB 소유자/관리자가 비밀번호를 공유하지 않고 읽기 전용으로 계정 Host 및 대상 DB 쓰기 권한 범위, 관련 자동 작업·연결/트랜잭션을 확인**해 실제 writer 범위를 정해야 한다. localhost 전용 계정만 있는지 확인할 수 있다면 현재 네트워크 허용 규칙과 별개로 중요한 근거가 된다.

그 범위의 앱·worker·클라이언트·자동 writer를 점검 창 동안 중지하고 재접속하지 않는 상태를 담당자가 확인·유지해야 한다. 원격 writer가 가능하다면 외부 writer도 포함해야 한다. 필요한 접근 통제 변경은 별도 승인·담당자 조치 범위로 남기고 이번에는 방화벽/계정/서버 설정을 바꾸지 않았다. 이 확인 후 재개 지시가 있으면 당시 DB·코드·백업·단일 계획을 다시 대조해 0004만 적용한다.

이번에 수행한 것은 OS/DB 읽기 전용 조사와 새 보존 증거 및 이 추가 기록뿐이다. 기능/설계·기존 코드·migration·.env·서버/방화벽·계정 권한·기존 증거를 변경하지 않았다. Git stage/commit/push/PR/merge는 수행하지 않았다.

## 11. 2026-11-15 root 관리자 점검 요청 — 안전한 로컬 인증 결과 대기

### 11-1. 이번 사전 재확인 및 현재 상태

사용자는 로컬 root 비밀번호를 알고 있으며 본인이 로컬 보안 입력창/터미널에서 직접 입력하도록 지시했다. 현재 도구에는 사용자가 직접 입력하는 로컬 보안 프롬프트를 전달할 수 있는 연결이 없다. 따라서 root 비밀번호를 채팅/도구 stdin으로 요청하거나 명령 인수/스크립트/.env/임시 파일에 저장하지 않는다. 아래 로컬 MySQL 클라이언트 절차를 사용자가 실행한 결과를 기다린다. **아직 root에 접속하거나 관리자 조사를 실행했다고 주장하지 않는다.**

이번 읽기 전용 재확인에서 dev/HEAD/기존 작업 트리를 보존했고, 개발 DB의 전체 스냅샷·기존 파일·코드/설정 해시·백업 해시가 이전 준비 결과와 일치했다. 테이블 25개·migration 28개, active_child_id 없음, 미적용 계획은 accounts.0004 하나다. 기존 복원/리허설/정상 종료와 169개 중 167개 통과·2개 제외 기록도 유효했다. 테스트를 이번에 다시 실행하지 않았다. 실제 DB migration 적용은 아직 하지 않았으며, 관리자 인증과 writer 통제 조건 확인을 기다린다.

### 11-2. 사용자가 직접 실행할 최소 읽기 전용 관리자 절차

**별도의 로컬 PowerShell**에서 아래 명령을 실행한다. 실제 비밀번호를 명령 뒤에 붙이지 말고 `Enter password:` 프롬프트에서 직접 입력한다. 비밀번호는 화면에 표시되지 않으며 채팅에 보내지 않는다.

```powershell
& 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' --no-defaults --protocol=TCP --host=127.0.0.1 --port=3306 --user=root --password --skip-auto-rehash
```

접속 후 **먼저 아래 한 문장만 실행**한다.

```sql
SELECT DATABASE(), CURRENT_USER(), @@hostname, @@port, @@server_uuid, @@version;
```

port=3306, UUID=`5491c807-5688-11f1-a0bf-c86e08e6aa63`, CURRENT_USER가 의도한 root 계정인지 확인한다. DATABASE()가 NULL인 것은 아직 DB를 선택하지 않았기 때문이다. 서버 식별자가 다르면 아래 조사를 진행하지 말고 그 사실만 알려준다.

식별자가 맞으면 아래 읽기 전용 SQL 묶음을 실행한다. 비밀번호 해시·authentication_string·실행 SQL 원문·트랜잭션 SQL·잠긴 행의 실제 값은 선택하지 않는다. 일반 mysqldump, Django, 테스트, 계정/권한/서버 설정 변경은 이 root 세션에서 실행하지 않는다.

```sql
-- 1) 계정 Host, 잠금/만료, 인증 방식만 확인 (비밀 인증 문자열 제외).
SELECT User, Host, account_locked, password_expired, plugin
FROM mysql.user ORDER BY User, Host;

-- 2) 모든 계정/역할의 전역·스키마·테이블·컬럼 권한.
-- 스키마 이름이 wildcard/escape 패턴일 수 있어 특정 이름으로만 필터하지 않는다.
SELECT GRANTEE, PRIVILEGE_TYPE, IS_GRANTABLE
FROM information_schema.USER_PRIVILEGES ORDER BY GRANTEE, PRIVILEGE_TYPE;
SELECT GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE, IS_GRANTABLE
FROM information_schema.SCHEMA_PRIVILEGES ORDER BY GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE;
SELECT GRANTEE, TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE, IS_GRANTABLE
FROM information_schema.TABLE_PRIVILEGES ORDER BY GRANTEE, TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE;
SELECT GRANTEE, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, PRIVILEGE_TYPE
FROM information_schema.COLUMN_PRIVILEGES ORDER BY GRANTEE, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME;

-- 3) 역할 상속/기본 역할/필수 역할·동적 전역 권한·proxy·저장 루틴 실행 권한.
SELECT FROM_USER, FROM_HOST, TO_USER, TO_HOST, WITH_ADMIN_OPTION FROM mysql.role_edges;
SELECT USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST FROM mysql.default_roles;
SHOW GLOBAL VARIABLES WHERE Variable_name IN ('mandatory_roles','activate_all_roles_on_login');
SELECT USER, HOST, PRIV, WITH_GRANT_OPTION FROM mysql.global_grants ORDER BY USER, HOST, PRIV;
SELECT User, Host, Proxied_user, Proxied_host, With_grant FROM mysql.proxies_priv;
SELECT User, Host, Db, Routine_name, Routine_type, Proc_priv FROM mysql.procs_priv;

-- 4) 전체 접속 상태. INFO/SQL 원문은 출력하지 않는다.
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE
FROM information_schema.PROCESSLIST ORDER BY TIME DESC, ID;
SELECT PROCESSLIST_ID, PROCESSLIST_USER, PROCESSLIST_HOST, PROCESSLIST_DB,
       PROCESSLIST_COMMAND, PROCESSLIST_TIME, PROCESSLIST_STATE
FROM performance_schema.threads
WHERE TYPE='FOREGROUND' AND PROCESSLIST_ID IS NOT NULL;

-- 5) 실행 중 트랜잭션 및 잠금/대기. TRX_QUERY와 LOCK_DATA는 제외한다.
SELECT trx_mysql_thread_id, trx_state, trx_started, trx_operation_state,
       trx_tables_locked, trx_rows_locked, trx_rows_modified
FROM information_schema.INNODB_TRX ORDER BY trx_started;
SELECT REQUESTING_THREAD_ID, BLOCKING_THREAD_ID FROM performance_schema.data_lock_waits;
SELECT THREAD_ID, OBJECT_SCHEMA, OBJECT_NAME, INDEX_NAME, LOCK_TYPE, LOCK_MODE, LOCK_STATUS
FROM performance_schema.data_locks WHERE OBJECT_SCHEMA='yippee_club_db';
SELECT OWNER_THREAD_ID, OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS='PENDING' OR OBJECT_SCHEMA='yippee_club_db';

-- 6) 전체 스키마의 이벤트. 정의 본문/접속 문자열은 출력하지 않는다.
SHOW GLOBAL VARIABLES WHERE Variable_name IN
 ('event_scheduler','bind_address','mysqlx_bind_address','port','mysqlx_port','skip_networking');
SELECT EVENT_SCHEMA, EVENT_NAME, DEFINER, STATUS, EVENT_TYPE,
       EXECUTE_AT, INTERVAL_VALUE, INTERVAL_FIELD, LAST_EXECUTED,
       (EVENT_DEFINITION LIKE '%yippee_club_db%') AS mentions_target_db
FROM information_schema.EVENTS ORDER BY EVENT_SCHEMA, EVENT_NAME;
```

오류가 발생하면 오류 내용도 함께 공유한다. 채팅에는 위의 **조회 결과만** 보내고 비밀번호·인증 문자열·.env·`SHOW CREATE USER`나 SELECT * FROM mysql.user 결과는 보내지 않는다. SQL 문장을 더 실행해 비밀정보를 추가 수집할 필요는 없다. 항목이 많으면 1~3번(계정/권한/역할)과 4~6번(접속/잠금/이벤트)으로 나눠 공유할 수 있다. 진단을 마치면 `exit`로 root 세션을 종료한다.

### 11-3. 결과를 받은 뒤의 판단 범위

계정 Host/잠금 상태와 전역·패턴 스키마·테이블/컬럼·루틴 권한, 재귀 역할 상속/기본·필수 역할, proxy·동적 관리 권한을 함께 검토해 실제 writer 후보를 구분한다. 잠긴 계정이 역할로 사용될 수 있으므로 account_locked만으로 권한 경로를 제외하지 않는다. 시스템 계정과 앱/사람/역할을 구분하되, 이름만으로 안전한 계정이라고 단정하지 않는다.

잠금·현재 연결 부재는 순간 관측이다. root 세션은 점검 연결이며 앱 writer와 구분한다. 외부 Host 허용 계정이나 자동 재접속 가능한 서비스가 있다면 담당자가 중지/점검 창 유지 여부를 확인해야 한다. 이벤트의 mentions_target_db=0도 저장 루틴/동적 SQL을 통한 간접 쓰기 부재의 증명은 아니다. 활성 이벤트가 있으면 필요한 부분만 로컬에서 추가 확인한다.

writer 통제에 설정 변경이 필요하면 영향·최소 변경·원복 계획을 제시하고 **별도 사용자 승인 전에는 실행하지 않는다**. 세션 강제 종료·서버 중지·비밀번호/계정/권한/방화벽/read_only 변경을 임의로 수행하지 않는다. 안전 조건을 충족했을 때만 적용 직전 상태를 다시 비교하고 기존 Django 앱 계정으로 표준 migrate accounts 0004 하나를 실행한다. 현재는 관리자 결과 대기이며 자동 적용을 예약하거나 준비 완료로 간주하지 않는다.

이번 단계는 이 문서에만 절차와 재확인 결과를 추가했다. 기존 기능 코드·migration·백업·자료 파일·.env·DB·Git history는 변경하지 않았고 Git stage/commit/push/PR/merge도 수행하지 않았다.

## 12. 2026-11-15 사용자 root 조회 결과 수령 및 최종 보완 점검 대기

### 12-1. 사용자가 직접 수행한 관리자 점검 결과

사용자는 root@localhost, port 3306, UUID `5491c807-5688-11f1-a0bf-c86e08e6aa63`, MySQL 8.0.46을 확인했다고 보고했다. 활성 계정은 root/yippee_app/yippee_rehearsal의 localhost 계정이고, mysql.infoschema/session/sys는 localhost·잠김이며 원격 Host 계정은 없었다. yippee_app은 대상 DB ALL PRIVILEGES, yippee_rehearsal은 전역 USAGE, root는 관리자였다.

전체 세션은 root 점검 및 빈 큐 대기 event_scheduler만 있고 다른 일반 사용자 세션은 없었다. INNODB_TRX·EVENTS·role_edges는 빈 결과였다. 이는 **사용자가 root로 직접 관측해 제공한 결과**이며 Codex가 root에 접속한 기록이 아니다. 비밀번호/인증 문자열은 수령하거나 기록하지 않았다.

이 결과는 원격 Host 계정과 기존 역할 상속·활성 이벤트·현재 트랜잭션에 대한 이전 불확실성을 줄인다. 네트워크 수신/방화벽 규칙은 바꾸지 않았으며, localhost 인증 범위가 확인됐다고 해서 터널/로컬 대리 프로세스·새 재접속의 중지까지 자동 보장된다고 해석하지 않는다.

### 12-2. 이번 독립 재확인

- 개발 DB 전체 스냅샷·파일·코드/설정·이전 백업 해시는 기존 성공 준비 증거와 동일하다. 25개 테이블·28개 migration, pending은 accounts.0004 하나다. 신규 DDL도 불변이다.
- 앱 계정의 SHOW GRANTS는 개발 DB ALL PRIVILEGES, test_yippee_club_db 관련 기존 권한 및 전역 USAGE만 표시했다. 테스트 DB 권한은 이번에 사용하지 않았다.
- mandatory_roles는 빈 문자열, activate_all_roles_on_login=OFF, 앱 CURRENT_ROLE()=NONE이다.
- mysql.default_roles/proxies_priv/global_grants는 앱 계정에 SELECT 권한이 없어 오류 1142로 확인 불가다. 조회를 위해 권한을 부여하거나 root 인증을 우회하지 않았다.
- OS에서 Python/Node/일반 DB GUI/앱 worker/SSH·DB 터널 후보와 프로젝트 관련 예약 작업을 점검했다. mysqld, VS Code/Codex, mysql.exe 클라이언트가 보였고 프로젝트 writer/터널 명령은 발견되지 않았다. IDE 확장 내부의 자동 작업까지 안전하다고 단정하지 않는다.
- MySQL 포트에는 로컬 `::1` 클라이언트 연결이 보였다. 전역 Threads_connected=2는 로컬 관리자 점검 클라이언트와 앱 계정의 점검 연결로 설명 가능한 수치다. OS 연결만으로 관리자 세션의 현재 SQL·트랜잭션을 확정하지는 않았다.

### 12-3. root 터미널에서 필요한 최종 보완 SQL

이미 열려 있는 안전한 로컬 root 터미널에서 아래 SELECT만 실행하고 결과를 공유한다. 새 비밀번호 입력·권한/설정 변경·비밀 인증 데이터 조회는 필요 없다.

```sql
SELECT USER, HOST, DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST FROM mysql.default_roles;
SELECT User, Host, Proxied_user, Proxied_host, With_grant FROM mysql.proxies_priv;
SELECT USER, HOST, PRIV, WITH_GRANT_OPTION FROM mysql.global_grants ORDER BY USER, HOST, PRIV;
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE
FROM information_schema.PROCESSLIST ORDER BY ID;
SELECT trx_mysql_thread_id, trx_state, trx_started, trx_rows_modified
FROM information_schema.INNODB_TRX;
```

기본 역할은 role_edges 빈 결과와 비교하고 proxy/동적 권한은 이미 확인한 실제 계정과 연결해 판단한다. 새 계정이나 외부 인증 경로가 추가로 발견되면 적용하지 않고 담당 범위를 확인한다. 관리자 조회 결과와 함께 **적용 완료까지 root 점검 이외의 SQL 쓰기·앱/worker/DB 클라이언트 자동 연결 작업을 시작하지 않고 유지 가능한지** 확인이 필요하다. 활성 writer가 확인됐다는 뜻이 아니라 최종 점검 창을 명확히 하기 위한 확인이다.

현재 적용 상태는 **관리자 보완 결과 및 점검 창 확인 대기**다. 개발 DB migration을 실행하지 않아 25개 테이블·28개 migration·0004 미적용 상태를 유지한다. 위 확인 후에도 실제 실행 직전 DB/코드/파일/백업/단일 계획과 관측 가능한 연결을 다시 확인하고 앱 계정으로만 적용한다. Git stage/commit/push는 수행하지 않았다.

## 13. 2026-11-15 최종 관리자 보완 확인 후 개발 DB 적용 성공

### 13-1. 보류 조건 해소와 확인 근거

사용자가 로컬 root로 마지막 점검을 수행한 결과를 제공했다.

- default_roles는 빈 결과다.
- proxies_priv는 root@localhost 관련 한 행만 있고 Proxied_user/Proxied_host 공백, With_grant=1이다. 이를 다른 계정의 실제 proxy 접속이 존재한다는 증거로 해석하지 않았다.
- global_grants 52행은 root/MySQL 내부 계정에만 있으며 yippee_app/yippee_rehearsal 행은 없다.
- 전체 연결은 빈 큐를 기다리는 event_scheduler와 root 관리자 조회 세션뿐이고 INNODB_TRX는 비어 있다.
- 앞서 계정 Host가 모두 localhost, EVENTS와 role_edges가 비어 있음을 확인했다.
- **사용자는 적용 완료까지 다른 SQL 쓰기·Django/worker/DB 클라이언트 자동 연결을 새로 시작하지 않겠다고 명시적으로 확인했다.**

위의 관리자 결과는 사용자가 직접 관측해 제공한 증거다. Codex가 root 비밀번호를 받거나 root에 접속한 것은 아니다. 앱 계정에서 독립 확인했던 mandatory_roles 빈 값·자동 역할 활성화 OFF·CURRENT_ROLE NONE, 로컬 writer/터널/관련 예약 작업 부재 관측과 함께 판단했다. 모든 root/시스템 권한을 제거한 상태가 아니라, 확인된 localhost 계정 범위와 자동 작업 부재·현재 연결/트랜잭션 상태·사용자의 점검 창 유지 약속을 근거로 이번 단일 적용의 충분한 안전 조건을 확보했다.

방화벽/전체 인터페이스 수신은 변경하지 않았다. localhost 계정만 있다는 결과를 근거 없이 인터넷 완전 차단으로 확대하지 않으며, 향후 원격 계정·터널·자동 작업이 추가되면 이 점검 창의 판단을 재사용하지 않는다.

### 13-2. 실제 적용 직전 재대조

- dev / HEAD `2af4c38153dd35ae3b42a98230ebe5574c2ee4c2`, 기존 작업 트리 보존.
- 기존 준비 report의 before/after와 현재 전체 DB·업무 행 해시·인덱스/컬럼/FK·파일·공개 목록 응답·migration 파일 해시 완전 일치.
- 전체 Python 코드/설정/.env 해시도 준비 시점과 일치했고 실제 .env는 출력/변경하지 않았다.
- 백업 SHA-256 `eae285b25c3b50880166e04ad097c09f62d5159baba12985c60438ce3516507d` 재확인. 같은 백업의 독립 복원 일치·0004 리허설·격리 서버 정상 종료 증거가 유효했다.
- 신규 migration SQL은 이전 검토된 accounts_user AddField DDL 한 개와 일치. 전체 미적용 계획은 accounts.0004 하나, forward였다.
- 앱 점검 연결 외의 자체 Django 연결을 닫은 상태에서 전역 Threads_connected=2 이하임을 다시 확인했다. 사용자 보고 root 읽기 전용 점검 세션 + 앱 점검 연결 범위에 부합했다. 이 전역 수치를 SQL/트랜잭션 내용까지 확인한 결과라고 주장하지 않는다. 전체 세션/빈 트랜잭션은 사용자 root 관측 결과를 사용했다.
- 위 확인 후 실제 DDL 직전에 DB 스냅샷/코드/단일 계획을 다시 대조했다. 환경·권한·writer 통제를 임의로 변경하지 않았다.

현재 데이터와 코드가 검증 시점과 같아 복원/169개 테스트를 또 실행하지 않았다. 이전 실행을 이번의 새로운 테스트 실행 수치로 기재하지 않는다.

### 13-3. 실제 적용 명령과 실행 범위

실행 DB는 yippee_club_db / 127.0.0.1:3306 / UUID `5491c807-5688-11f1-a0bf-c86e08e6aa63`, **기존 앱 계정 yippee_app@localhost**다. root로 migration/서버/테스트를 실행하지 않았다.

표준 Django 명령과 동일한 call_command 실행:

```powershell
.venv/Scripts/python.exe manage.py migrate accounts 0004_user_active_child --noinput
```

실제로는 아래 새 증거 디렉터리의 `apply_approved.py`가 표준 `call_command('migrate', 'accounts', '0004_user_active_child', interactive=False)`를 호출했다. SQL wrapper는 서버 식별자를 매 statement마다 검사하고 **리허설에서 확인한 DDL 원문 한 개와 accounts.0004 migration INSERT 한 개만** 쓰기로 허용했다. 예상 밖 metadata/업무 DML은 허용하지 않았다. 재시도 방지용 apply-started.json을 생성했고 실패 시 자동 복구/재적용 코드도 없다.

결과: `Applying accounts.0004_user_active_child... OK`. 오류·부분 적용·재시도·fake·임의 rollback은 없었다. 실제 변경 SQL은 accounts_user에 컬럼/FK를 추가하는 DDL 1건(필요 인덱스는 MySQL이 생성)과 django_migrations INSERT 1건뿐이었다.

### 13-4. 적용 후 DB·파일·Django 검증

| 항목 | 적용 전 | 적용 후 |
|---|---:|---:|
| 테이블 | 25 | **25** |
| migration | 28 | **29** |
| accounts.0004 | 미적용 | **적용 완료** |
| 전체 미적용 계획 | 0004 하나 | **없음** |
| active_child_id | 없음 | **bigint NULL**, children.id FK·인덱스 확인 |
| 사용자 / 아이 | 0 / 0 | **0 / 0** |
| 활동지 / 카테고리 | 4 / 2 | **4 / 2**, 내용·공개 여부·가격 보존 |
| 찜 / 장바구니 / 구매 권한 | 0 / 0 / 0 | **0 / 0 / 0** |
| ContentType/Permission | 기존 상태 | **변경 없음** |

기존 User 컬럼·PK·인덱스/제약은 신규 active_child 부분만 제외하면 같고, 기존 컬럼 projection의 행 해시도 동일했다. Child.user를 포함한 기존 FK 전체에 새 active_child FK 한 개만 추가됐다. 다른 모든 테이블의 스키마와 전체 행 해시는 동일했다. 기존 28개 migration 행은 보존하고 신규 1개만 추가했다.

최종 전체 스키마/컬럼/FK/데이터는 격리 리허설 결과와 일치했다(migration 적용 시각 제외). 원본 자료 8개·private 저장 파일 20개의 파일 집합과 해시, 공개 활동지 목록 응답도 보존됐다. 실제 사용자/아이가 없으므로 현재 DB의 NULL 검사는 빈 집합이며, 기존/신규 사용자가 있는 동작·소유권·SET_NULL·CASCADE는 이전 격리 테스트 18개로 검증했다. 개발 DB에 테스트 사용자·아이·선택 상태를 만들지 않았다.

- 실제 개발 DB의 `check --database default`: 문제 없음.
- 전체 `showmigrations`: accounts.0004 포함 모두 [X].
- `makemigrations --check --dry-run`: No changes detected.
- 검사 후 전체 DB/파일 스냅샷과 코드/설정 해시를 재확인해 추가 변경 없음.
- CART_PURCHASE_ENTITLEMENTS_VERIFIED=False 유지. 실제 SMTP/PG 및 개발 DB의 인증된 API 쓰기는 실행하지 않았다.

### 13-5. 증거·파일·Git·남은 사항

새 적용 증거: `.mysql-rehearsal/active-child-apply-0769b5699ab4/`.

| 파일 | 내용 |
|---|---|
| apply_approved.py | 정확한 준비 증거/DDL과 연결 수를 확인하는 단일 적용 실행기 |
| apply-started.json | 사용자 점검 창 확인·대상/서버 및 재시도 방지 표식 |
| migrate.txt | 실제 0004 적용 성공 로그 |
| checks.txt | 실제 개발 DB system check/전체 이력/모델 일치 검사 |
| report.json | 관리자 제공 결과 출처·점검 창·앱 계정·실행 SQL 분류·적용 전후 전체 보존 증거 |

이전 백업/복원/169개 테스트 증거는 `.mysql-rehearsal/active-child-deploy-7ad71f2449b2/`를 그대로 보존했다. 새 증거도 Git 추적 제외 디렉터리에 있으며 비밀번호/접속 토큰은 기록하지 않았다.

이번 기능 코드·기존 migration·.env·파일·서버/방화벽/계정 권한은 수정하지 않았다. 본 문서에 성공 결과와 상단 최신 상태 안내만 추가했으며 기존 보류 이력은 유지했다. 기존 미커밋 작업 전부 보존했고 Git stage/commit/push/PR/merge는 수행하지 않았다.

개발 DB 스키마 관점에서 25번 API 사용 준비가 완료됐다. 실제 JWT 수동 쓰기 검증은 사용자가 계정을 준비한 뒤 별도 범위로 진행할 수 있으며 이번에는 수행하지 않았다. Python 3.12 재검증과 구매 권한 연동 전 cart 추가 차단은 기존 남은 사항이다. 향후 적용 시에는 이번 점검 창의 사용자 약속/세션 관측을 그대로 재사용하지 않고 writer와 백업 상태를 다시 확인해야 한다.
