# 활동지 개발 DB 적용 결과 및 관리자 등록 준비

2026-11-14, 로컬 `dev` 브랜치에서 직전 활동지 구현을 이어서 수행했습니다. Git commit/push/PR/merge는 수행하지 않았습니다. 기존 migration과 인증·아이 관리 API는 변경하지 않았습니다.

> 후속 등록 준비에서 카테고리 `신체운동·건강`(ID 1), `자연탐구`(ID 2)를 추가했습니다. 아래 표의 카테고리 0개는 DB migration 적용 당시 기록입니다. 최신 상태와 필요한 파일은 [활동지 등록 준비 결과](ACTIVITY_SAMPLE_REGISTRATION.md)를 참고하세요.

> 이후 실제 자료 4개(ID 1~4)의 등록·공개 및 HTTP 조회/다운로드 검증도 완료했습니다. [최종 등록 결과](ACTIVITY_SAMPLE_IMPORT_RESULT.md)에 현재 상태를 기록했습니다.

## 실제 적용 결과

| 항목 | 적용 전 | 적용 후 |
|---|---:|---:|
| 개발 DB 테이블 | 20 | 22 |
| 적용 migration | 24 | 25 |
| 사용자 | 0 | 0 |
| 활성 superuser | 0 | 0 |
| 아이 | 0 | 0 |
| 카테고리 | 0 | 0 |
| 활동지 / 활동지-카테고리 연결 | 테이블 없음 | 각각 0 |
| 기존 인증 속도 제한 기록 | 5 | 5 |
| Django content type | 14 | 16 |
| Django permission | 56 | 64 |

대상은 로컬 MySQL 8.0.46, `yippee_club_db`, 포트 `3306`, 서버 ID `1`, 서버 UUID `5491c807-5688-11f1-a0bf-c86e08e6aa63`입니다. 설정뿐 아니라 실제 연결에서 DB명/계정/서버 UUID/포트를 대조했습니다. 비밀번호와 개인정보는 출력하지 않았습니다.

실제 적용한 migration은 **`activities.0001_initial` 하나**입니다. 생성 테이블은 `activities`, `activity_categories`이며 기존 Category 테이블은 변경하지 않았습니다. 관계 테이블의 activity_id→activities.id 및 category_id→categories.id FK와 중복 연결 방지 UNIQUE를 확인했습니다. 가격 0원, 개월 수 범위, 양수 소요 시간 및 시간 범위, 난이도 CHECK는 실제 개발 DB에서 ENFORCED=YES입니다. 기존 24개 migration 이력을 모두 보존했습니다.

기존 모든 테이블의 컬럼 메타데이터, 스키마, 행별 해시, 전체 행 해시, FK를 비교했습니다. 기존 업무 데이터는 동일하고, Django migration 기록 1행·content type 2행·permission 8행만 정상 추가되었습니다. 메타데이터 테이블의 AUTO_INCREMENT 카운터 증가는 추가 행에 따른 예상 변경이며 기존 행은 변경되지 않았습니다. 실제 개발 DB에 테스트 사용자/카테고리/활동지/세션을 생성하지 않았습니다.

## 백업과 복원 검증

증거 디렉터리:

`.mysql-rehearsal/activity-deploy-c40dcb0e60c8/`

새 백업은 해당 디렉터리의 `yippee_club_db.sql`이며 **23,636 bytes**입니다.

SHA-256: `803f5f4b58060eff63f5c9e415982179973585042f00e984a69ac4edb48d3f97`

기존 `run_mysql_rehearsal.snapshot/digest` 함수와 백업 스크립트의 안전한 mysqldump 옵션을 재사용했습니다. 단일 트랜잭션·테이블 잠금 생략·DROP 문 생성 생략 방식으로 새 백업을 만들었습니다. 트리거/루틴/이벤트/뷰 및 비-InnoDB 테이블이 없는 것도 확인했습니다. 백업과 자격정보/데이터 디렉터리는 현재 Windows 사용자와 SYSTEM에 접근을 제한한 Git 제외 디렉터리에 보존합니다.

기존 리허설 인스턴스나 공유 테스트 DB를 재사용하지 않았습니다. 새 `data/`를 초기화하고 별도 MySQL 서버(33307, server_id=9133307)를 띄워 UUID/실제 데이터 경로까지 확인한 후, 새 인스턴스에만 복원 DB와 회귀 테스트 DB를 생성했습니다. 기존 리허설 DB와 이름이 같아도 물리 인스턴스/UUID/데이터 디렉터리가 다르며, 기존 테스트 DB에는 접속하지 않았습니다. 새 인스턴스는 검증 후 정상 종료했습니다. 이전 `.mysql-rehearsal`의 자료는 수정하거나 삭제하지 않았습니다.

실행 순서는 다음과 같습니다.

1. 개발 DB를 읽기 전용으로 식별하고 20개 테이블·24개 이력과 실제 데이터 상태를 기록.
2. migration 파일과 생성 SQL을 검토하고 전체 계획이 activities.0001_initial 하나인지 확인.
3. 새 백업을 만들고 개발 DB가 백업 중 변경되지 않았음을 확인.
4. 새 독립 인스턴스에 복원하고 원본의 모든 테이블 스키마/행 해시/FK/migration 이력과 일치함을 확인.
5. 복원본에 신규 migration을 적용해 22개 테이블·25개 이력 및 기존 데이터 보존을 확인.
6. 새 인스턴스의 별도 테스트 DB에서 전체 회귀 테스트 실행. 테스트 후 복원본이 그대로임을 확인.
7. 개발 DB 상태·백업 해시·코드 해시·단일 migration 계획을 재확인하고 해당 migration만 적용.
8. 실제 적용 결과를 복원 리허설 결과와 비교하고 기존 행/스키마/FK 및 제약 보존을 확인.

주요 증거 파일:

| 파일 | 내용 |
|---|---|
| `report.json` | 적용 전 스냅샷, 백업 해시, 복원/테스트 성공, 복원본 업그레이드 결과, 격리 서버 종료 |
| `migrate-plan.txt`, `migrate.txt` | 복원본 단일 migration 계획 및 적용 |
| `test.txt` | 이번 전체 회귀 테스트 결과 |
| `check.txt`, `makemigrations.txt` | 격리 DB 검사 결과 |
| `apply-started.json`, `development-migrate.txt` | 개발 DB 적용 대상과 실제 성공 로그 |
| `verify-final.json` | 실제 개발 DB 적용 후 보존 검증 결과 |
| `environment.json` | 개발 DB 읽기 전용 관리자/조회/제약 검사, 저장소 쓰기 검사 |
| `storage-inventory.json` | 이미 존재한 저장 파일의 이름/크기/시각/해시 기록 |

## 실행한 검증

- 새 독립 MySQL 인스턴스 전체 Django 테스트: **114개 중 112개 통과, 2개 제외**. 제외된 것은 기존 preview 전용 SQL 차단 테스트입니다. 활동지 테스트 10개 및 기존 인증·이메일·아이 API 회귀 테스트가 포함됩니다.
- 기존 스크립트 안전성 단위 테스트: **19개 모두 통과** (`python -m unittest discover -s scripts/tests -v`). 실제 DB에는 연결하지 않는 테스트입니다.
- 격리 DB 및 실제 개발 DB의 Django system check: 오류 없음.
- 격리 DB 및 실제 개발 DB의 `makemigrations --check --dry-run`: 변경 없음.
- 실제 개발 DB `showmigrations activities`: `[X] 0001_initial`.
- 실제 개발 DB 적용 후 전체 migration 계획: 대기 작업 없음.
- 실제 개발 DB의 공개 활동지 목록: HTTP 200, count=0.
- 실제 개발 DB의 CHECK 활성화, FK, 기존 행 보존: 성공.

실제 개발 DB에는 제약 검증용 INSERT/UPDATE를 하지 않았습니다. 가격 변경 차단, 관리자 등록/수정/파일 교체/공개 전환, 공개 파일 스트리밍 및 비공개 파일 404는 격리 테스트에서 검증했습니다.

## 관리자 등록 환경과 남은 준비

실제 개발 DB 기준으로 Activity 관리자 메뉴와 추가 폼 렌더링(HTTP 200), 제목/설명/최소·최대 개월 수/난이도/소요 시간/카테고리/PDF/표지/공개 여부 필드, 가격 읽기 전용 0원, 카테고리 필수 선택을 확인했습니다. 익명/일반 회원 권한 거부도 확인했습니다.

**활성 관리자 계정이 0개이므로 실제 개발 DB 관리자 로그인은 아직 실행하지 않았습니다.** 개발 DB 폼 검사는 저장하지 않은 권한 객체를 사용한 읽기 전용 렌더링입니다. 실제 관리자 로그인·등록·수정·파일 교체는 새 격리 테스트 DB에서 검증했습니다. 개발 DB에 임시 관리자나 예시 활동지를 만들지 않았습니다.

관리자 계정이 필요한 담당자는 프로젝트 폴더의 PowerShell에서 아래 명령을 직접 실행합니다. 이 명령은 안내만 제공했으며 이번 작업에서 실행하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

이메일과 비밀번호를 대화형으로 입력합니다. 기존 사용자나 비밀번호는 변경하지 않습니다. 개발 서버가 실행되어 있지 않으면 다음 명령으로 로컬에서 실행하고 `http://127.0.0.1:8000/admin/`에 접속합니다. 이번 작업에서는 새 웹 서버를 시작하지 않았습니다.

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

### 카테고리

실제 Category 목록은 **빈 목록(0개)**입니다. `신체운동·건강`, `자연탐구` 모두 현재 매핑 가능한 ID가 없습니다. 임의로 생성하거나 ID를 지정하지 않았습니다.

관리자 계정 준비 후 `/admin/categories/category/`에서 기존 목록을 재확인합니다. 담당자가 공통 카테고리 명칭을 확정한 다음 **추가**를 눌러 `신체운동·건강`, `자연탐구`를 각각 저장하면 DB가 ID를 생성합니다. 아이 관심사와 활동지가 공유하는 목록이므로 기존 체계를 확인한 뒤 추가합니다. 활동지 등록 시 이 목록에서 선택하며, 카테고리가 없는 상태에서는 등록할 수 없습니다.

## 파일 저장 환경

- `ACTIVITY_PRIVATE_ROOT`: `C:\Users\kt246\Desktop\YIPPE_CLUB\TEAM_YIPPE_CLUB_BE\private_uploads`
- 업로드 경로: 위 디렉터리 아래 `activities/{UUID}.{확장자}`.
- 현재 Python 실행 계정으로 임시 검사 파일의 생성/쓰기/읽기/삭제 성공. 검사 파일은 제거했습니다. 실제 PDF 업로드나 DB 파일 참조 생성은 하지 않았습니다.
- PDF 20MiB(20,971,520 bytes), 표지 5MiB(5,242,880 bytes) 제한 확인.
- 저장소 직접 URL 발급 거부 및 `/media/`, `/private_uploads/` 직접 노출 URL 미등록 확인.
- 공개 파일은 매 요청 DB 공개 여부를 검사해 스트리밍하며 private/no-store와 nosniff를 사용합니다. 비공개 파일 차단은 격리 테스트에서 확인했습니다.
- 이 폴더를 정적 공개 경로나 공개 CDN에 연결하면 안 됩니다. 운영 서버 계정의 파일 권한/영구 볼륨/백업/비공개 버킷/프록시 설정은 별도 검증이 필요합니다.

저장 디렉터리에는 이번 준비 작업보다 앞선 2026-11-14 09:58 UTC에 생성된 DB 미참조 파일 12개(PDF 6개, PNG 6개)가 있었습니다. 현재 개발 DB 활동지는 0개이므로 등록된 활동지로 간주하지 않습니다. 파일은 삭제하거나 덮어쓰지 않고 해시/시각을 기록해 그대로 보존했습니다. 이번 격리 테스트는 새 인스턴스와 임시 저장 위치를 사용했습니다. 기존 파일의 출처와 정리 여부는 별도 확인 사항입니다.

## 실제 활동지 등록까지 남은 순서

1. 담당자가 관리자 계정을 생성하고 실제 `/admin/` 로그인 확인.
2. 공통 카테고리 목록을 확정하여 필요한 두 항목 등록, 생성된 ID 확인.
3. 사용자가 제공할 원본 놀이북을 확인하고 개별 놀이 4개의 PDF와 표지를 준비.
4. 관리자에서 각 활동지를 60~65개월, 가격 0원으로 등록하고 처음에는 비공개로 내용 확인.
5. 공개 전환 후 목록/상세/파일 조회를 실제 자료로 확인.

이번 작업에서는 원본 PDF 분리, 실제 활동지 등록, 결제 기능을 실행하거나 구현하지 않았습니다. 원본 PDF를 받은 다음 단계에서 개별 놀이 4개로 분리·등록합니다.

## 추가한 준비 도구

- `scripts/prepare_activity_deploy.py`: inspect/prepare/apply/verify. 검증된 백업/코드/대상 상태가 달라지면 중단하고 적용 재시도를 거부합니다. 이미 적용했으므로 이번 evidence로 apply를 다시 실행하지 마세요.
- `config/activity_deploy_rehearsal.py`: 새 격리 인스턴스 UUID/데이터 경로 및 DB allowlist를 추가 확인합니다. 기존 개발 설정이나 기존 리허설 설정은 변경하지 않았습니다.
- `scripts/check_activity_environment.py`: 읽기 전용 관리자 폼/공개 목록/제약 검사와 임시 파일 쓰기 확인. 개발 DB 행은 생성하지 않습니다.

반복 점검이 필요하면 다음 읽기 전용 검증을 사용합니다.

```powershell
.\.venv\Scripts\python.exe scripts/prepare_activity_deploy.py verify --evidence .mysql-rehearsal/activity-deploy-c40dcb0e60c8
```

이 보존 검증은 등록 전의 정확한 상태를 기준으로 합니다. 이후 실제 관리자/카테고리/활동지를 추가하면 상태가 달라져 중단될 수 있으며, 이는 자동 복구나 삭제를 의미하지 않습니다.
