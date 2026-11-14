# 즐겨찾기 DB 적용 준비와 승인 후 검증 절차

> **후속 적용 완료:** 사용자 승인 후 개발 DB에 favorites.0001_initial 하나를 적용했습니다. 현재 23개 테이블·26개 migration, favorites 0행이며 기존 데이터와 파일은 보존되었습니다. 아래 승인 대기 표기는 준비 당시 기록입니다. [최종 적용 결과](FAVORITES_DB_APPLICATION.md)를 참고하세요.

이번 작업은 **준비와 독립 리허설까지만** 수행합니다. 실제 개발 DB에는 migration/DDL/DML/계정/즐겨찾기를 생성하지 않습니다. 기존 API 계약, 비공개 활동지 정책, 페이지네이션 정책과 기존 로컬 변경 사항을 유지합니다. 실제 적용은 최종 결과를 확인한 사용자의 별도 승인이 필요합니다.

## 최종 실행 결과

2026-11-14 검증 완료. **리허설 기준 적용 준비가 통과했으며 실제 개발 DB 적용은 승인 대기입니다.**

| 항목 | 실제 개발 DB | 독립 보존 검증용 복원본 |
|---|---|---|
| DB | yippee_club_db, 3306 | test_yippee_migration_fresh, 33307 |
| 서버 UUID | 5491c807-5688-11f1-a0bf-c86e08e6aa63 | beb32aa8-e02c-11f1-be99-00155d623862 |
| 테이블 / migration | **22 / 25 유지** | **23 / 26**, favorites.0001_initial 적용 |
| 공개 활동지 | ID 1~4, 가격 모두 0원, 변경 없음 | 기존 4개와 파일 참조 보존 |
| 카테고리 | ID 1 신체운동·건강, ID 2 자연탐구 | 기존 두 행 보존 |
| 사용자 / 활성 관리자 | **0 / 0**, 생성하지 않음 | 기존 상태 그대로 |
| 즐겨찾기 | 테이블 미생성, 데이터 미생성 | 테이블 생성 및 FK/UNIQUE, 0행 |

보존 검증용과 HTTP용 두 복원본 모두 원본의 모든 테이블·컬럼 메타데이터·전체 행 해시·개별 행 해시·FK·migration 이력이 정확히 일치한 뒤 업그레이드했습니다. 업그레이드 시 기존 모든 업무 데이터와 스키마를 보존했고, migration 1행/content type 1행/permission 4행만 정상 추가되었습니다. 전체 테스트 및 HTTP 검증 뒤 보존용 복원본이 업그레이드 직후 상태와 정확히 같음을 다시 확인했습니다.

전체 Django 테스트는 **135개 중 133개 통과, 기존 preview 전용 2개 제외**입니다. 즐겨찾기 14개 테스트, 동시 추가의 201/409 및 단일 UNIQUE 관계, 기존 인증/이메일/아이/카테고리/활동지/실제 파일 회귀 테스트를 포함합니다. 별도 스크립트 안전성 단위 테스트는 **19개 통과**했습니다. 격리 system check, `makemigrations --check --dry-run`도 통과했습니다.

실제 TCP/WSGI HTTP 검증은 별도 HTTP용 복원 DB에서 **28건 모두 통과**했습니다. 무작위 자격정보의 A/B 계정 생성은 이 복사본에서만 수행했습니다. 기존 로그인 엔드포인트의 JWT 발급, 추가 201, 중복 409, 목록/타 사용자 격리, 삭제 204/반복 404, 비공개 활동지 400/404, user_id 주입 거부, 토큰 누락/오류 401 및 응답 JSON 계약을 확인했습니다. 비밀번호와 토큰은 출력하지 않았고 HTTP 서버는 정상 종료했습니다.

실제 개발 DB의 모든 스키마/데이터/FK/이력 및 기존 활동지 응답이 작업 전후 동일합니다. 실제 파일 8개와 기존 미참조 12개를 포함한 저장 파일 20개, 원본 sample 파일 8개, 기존 migration 해시도 동일합니다. 원본을 수정하지 않고 독립 파일 복사본만 사용했습니다. 실제 개발 계정 로그인과 실제 즐겨찾기 API 쓰기는 **미실행**입니다.

### 백업과 증거

최종 성공 증거 디렉터리: `.mysql-rehearsal/favorites-deploy-b36bb56183fa/`

- 백업: `yippee_club_db.sql`, **28,412 bytes**.
- SHA-256: `35c1da37880452c8a236485379e0f128857ee4f52c34a8f269e2e9c48405ec53`.
- `report.json`: 대상 식별자, 전체 원본 스냅샷, 백업 메타데이터, 두 복원/업그레이드 결과, 작업 후 원본 동일성, 코드 해시, 격리 서버 정상 종료 기록. success=true, development_written=false.
- `preservation-plan.txt`, `preservation-sql.txt`, `preservation-migrate.txt`: 보존용 단일 migration 계획/생성 SQL/적용 결과.
- `http-copy-plan.txt`, `http-copy-sql.txt`, `http-copy-migrate.txt`: HTTP용 복사본의 같은 검증 결과.
- `test.txt`, `check.txt`, `makemigrations.txt`: 전체 회귀 및 검사 결과.
- `http.txt`: 비밀번호/토큰 없이 요청 메서드·경로·상태 코드만 기록한 28건의 성공 결과.
- `restored-uploads/`: 원본 저장 파일 20개의 독립 복사본. 테스트 후 해시 동일.
- `data/`: 이번에 새로 초기화한 MySQL 데이터. 서버는 정상 종료했고 증거는 삭제하지 않았습니다.

독립적인 작업 전후 원본 감사 기록은 `.mysql-rehearsal/favorites-validation-c620c62c6d7d/{before.json,after.json}`에 있습니다. 파일과 백업·자격정보는 기존 정책대로 접근을 제한한 Git 제외 위치에 보존합니다.

첫 시도 `.mysql-rehearsal/favorites-deploy-aec76f6fe2af/`는 복원·업그레이드·전체 테스트까지 통과했지만, 인증 거부 POST의 HTTP 연결 중단으로 완료 처리하지 않았습니다. 인증 거부로 읽히지 않은 요청 본문이 Windows의 wsgiref 소켓 종료에 영향을 줄 수 있어 **검증 서버에서만** 제어된 본문을 먼저 버퍼링하도록 보완했습니다. 기존 API는 변경하지 않았습니다. 첫 시도 자료와 서버 정상 종료 기록을 그대로 보존하고, 새 백업과 새 물리 인스턴스로 전 과정을 다시 실행한 결과가 위 최종 성공 기록입니다.

### 판단

이번 원본 스냅샷과 코드 상태에서는 단일 신규 migration 적용을 준비할 수 있는 근거가 확보되었습니다. 그러나 **사용자 승인 없이 개발 DB에 적용하지 않았고**, 준비 도구에도 개발 apply 기능을 넣지 않았습니다. 다음 적용 직전에는 원본 상태/대상/단일 계획/백업/코드 해시를 다시 확인해야 합니다. 실제 사용자와 관리자 계정은 없으므로 직접 계정 준비와 실제 로그인·API 사용 확인도 남아 있습니다. 아래 승인 이후 절차를 따릅니다.

## 적용 대상과 준비 도구

`favorites.0001_initial`의 작업은 favorites 테이블 생성 하나입니다. 기존 User·Activity를 참조하는 FK 두 개와 `(user_id, activity_id)` 복합 UNIQUE를 포함합니다. 기존 accounts/children/categories/activities 테이블 ALTER, 데이터 이동, RunPython/RunSQL 작업은 없습니다. 기존 migration을 수정하지 않았습니다.

준비 도구:

- `scripts/prepare_favorites_deploy.py`: inspect/prepare만 제공합니다. **개발 DB apply 기능은 없습니다.** 기존 `prepare_activity_deploy.py`의 대상 식별 및 `run_mysql_rehearsal.py`의 snapshot/digest와 검증된 백업 옵션을 재사용합니다.
- `config/favorites_deploy_rehearsal.py`: 이번에 새로 만든 MySQL 인스턴스의 UUID/실제 데이터 디렉터리/포트/서버 ID/DB allowlist를 확인합니다. 기존 설정과 기존 리허설 인스턴스를 변경하지 않습니다.
- `scripts/favorites_http_smoke.py`: 별도 HTTP 검증용 복원 DB에서만 실제 TCP/WSGI 요청으로 로그인·JWT·즐겨찾기를 확인합니다. 무작위 검증 계정/비밀번호는 이 독립 복사본과 프로세스 메모리에서만 사용하고 출력하지 않습니다.

## 격리 구조와 검증 순서

1. 개발 DB를 읽기 전용으로 식별하고 전체 스키마/컬럼/행 해시/FK/migration 이력, 활동지 API 응답, 원본 파일과 private 파일 해시를 기록합니다. 전체 대기 계획이 favorites.0001_initial 하나인지 확인합니다.
2. 새 접근 제한 디렉터리에 단일 트랜잭션/테이블 잠금 생략/DROP 문 생성 생략 옵션으로 전체 mysqldump 백업을 만듭니다. 트리거/루틴/이벤트/뷰/비-InnoDB 테이블은 별도 검토가 필요하므로 발견 시 중단합니다.
3. 소스 DB가 백업 중 바뀌지 않았는지 확인하고 파일 20개를 이번 디렉터리에 독립 복사하여 해시를 대조합니다.
4. 새 데이터 디렉터리에서 별도 MySQL(127.0.0.1:33307, server_id=9133307)을 초기화합니다. 기존 서버/DB/자격정보/백업/증거를 재사용하거나 덮어쓰지 않습니다.
5. 새 인스턴스 안에 보존 검증용 `test_yippee_migration_fresh`, HTTP 검증용 `test_yippee_migration_legacy`, 전체 회귀용 `test_yippee_migration_suite`를 분리합니다. 같은 이름의 과거 DB는 별도 물리 인스턴스에 있으므로 열지 않습니다.
6. 보존용과 HTTP용 DB에 각각 백업을 복원하고 원본의 모든 테이블/행 해시/FK/이력과 일치하는지 확인합니다. 두 복원본에 각각 단일 신규 migration만 적용하고 기존 데이터 보존 및 예상 메타데이터 추가만 있는지 검증합니다.
7. 회귀용 DB에서 전체 테스트를 실행하고 HTTP용 복원본에서 실제 로그인/즐겨찾기 HTTP 흐름을 실행합니다. HTTP용 복사본에만 임시 계정·인증 기록·비공개 fixture가 남을 수 있으며, 원본 DB나 보존용 복원본을 테스트 데이터로 오염시키지 않습니다.
8. 보존용 업그레이드 DB가 테스트 전후 그대로인지, 독립 파일 복사본이 그대로인지, 실제 개발 DB/모든 원본 파일/코드가 그대로인지 재확인하고 격리 서버를 정상 종료합니다.

적용 리허설의 정상 예상 결과는 **23개 테이블·26개 migration**, 새 favorites 0행, 기존 모든 업무 행 동일입니다. Django post_migrate의 예상 추가는 migration 기록 1행, Favorite content type 1행, permission 4행입니다. 이 메타데이터 테이블의 AUTO_INCREMENT 증가는 정상이며, 기존 행의 해시와 컬럼 정의는 보존되어야 합니다.

## HTTP 계약 검증 범위

HTTP 검증용 복원본에 무작위 자격정보의 사용자 A·B를 준비하고 기존 `/api/v1/auth/login`으로 실제 JWT를 발급받습니다. 토큰/비밀번호/로그인 응답 본문을 출력하지 않습니다. API 구현이나 응답 계약은 변경하지 않습니다.

- A의 추가 201, `activity_id/message` 응답 일치, 본인 목록 results 및 기존 ActivitySerializer 항목 일치.
- 중복 추가 409, B 목록 격리, B가 A 관계 삭제 시 404와 A 관계 유지, A/B가 같은 활동지를 각각 저장 가능.
- user_id 본문 주입 400, A 정상 삭제 204 및 빈 본문, A 삭제 후 빈 목록, 반복 삭제 404, B 관계 유지 후 삭제.
- 별도 비공개 fixture 추가 거부 400, 활동지 상세/PDF 404, 숨긴 관계 목록 제외 및 본인 삭제 가능.
- 토큰 누락과 잘못된 JWT의 GET/POST/DELETE 401, 없는 활동지 추가 400.
- 오류의 code/message/details/request_id 구조, 가격 0원 유지. HTTP 종료 시 즐겨찾기 fixture는 0행입니다.

JWT 만료, 비활성 계정, 동시 요청/UNIQUE, ORM 삭제 관계, 페이지네이션, 재공개 정책과 기존 인증/이메일/아이/카테고리/활동지/파일 다운로드는 전체 회귀 테스트에서 검증합니다.

## 실제 계정 준비: 이번 작업에서는 미실행

즐겨찾기에는 일반 로그인 계정으로 충분합니다. 실제 DB에 사용자가 없다면 사용자가 기존 이메일 인증/회원가입 API 또는 본인이 선택한 클라이언트에서 직접 가입합니다. 경로와 절차는 기존 `AUTH_API_IMPLEMENTATION.md`를 참고합니다. 관리자도 필요한 경우 아래 명령을 직접 실행하여 이메일과 비밀번호를 입력합니다.

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

이 명령이나 실제 회원가입은 이번 준비에서 실행하지 않습니다. 비밀번호는 코드/명령 인자/문서/로그에 적지 않습니다. 기존 사용자나 비밀번호를 임의로 변경하지 않습니다.

## 승인 이후에만 수행할 절차

1. 최신 DB 식별자·전체 스냅샷·백업 SHA-256·코드 해시와 단일 migration 계획이 이번 검증 상태와 일치하는지 다시 확인합니다. 상태가 바뀌었다면 새 백업과 리허설을 준비합니다.
2. 사용자 승인을 받은 후 대상 DB를 재확인하여 favorites.0001_initial 하나만 적용합니다. 이번 문서는 실행 승인을 대체하지 않습니다.
3. 23개 테이블·26개 migration, FK/UNIQUE, 기존 데이터/활동지/파일 해시 보존, system check 및 migration 변경 없음 확인 후 실제 사용을 시작합니다.
4. 사용자가 직접 준비한 계정으로 아래 로그인 절차를 사용합니다. 예시는 **승인/적용 이후 수동 검증용이며 이번 작업에서 실행하지 않습니다.**

PowerShell에서 자격정보를 출력하지 않고 로그인 응답은 변수에만 보관합니다.

```powershell
$apiBase = 'http://127.0.0.1:8000/api/v1'
$loginEmail = Read-Host '본인 계정 이메일'
$loginPassword = Read-Host '비밀번호' -AsSecureString
$loginBody = @{
    email = $loginEmail
    password = [System.Net.NetworkCredential]::new('', $loginPassword).Password
} | ConvertTo-Json
$loginResult = Invoke-RestMethod -Method Post -Uri "$apiBase/auth/login" -ContentType 'application/json' -Body $loginBody
$favoriteHeaders = @{ Authorization = 'Bearer ' + $loginResult.access_token }
Remove-Variable loginBody, loginPassword
```

본인의 기존 목록을 먼저 확인합니다. 이미 저장한 활동지는 검증을 위해 삭제하지 않습니다. 새 검증 관계를 만들려면 현재 본인이 저장하지 않은 공개 활동지 ID를 선택합니다.

```powershell
$beforeFavorites = Invoke-RestMethod -Method Get -Uri "$apiBase/favorites" -Headers $favoriteHeaders
$beforeFavorites.results | Select-Object id, title, price
```

사용자가 새 검증 관계 생성을 선택한 경우에만 다음을 실행합니다. 추가 201, 같은 요청 반복 409, 목록 포함을 확인하고 **이번에 새로 만든 본인 관계에 한해** 삭제 204 및 목록 제외를 확인합니다. 실제 활동지/PDF/표지는 수정하지 않습니다.

```powershell
$selectedActivityId = [long](Read-Host '현재 저장하지 않은 공개 활동지 ID')
$favoriteBody = @{ activity_id = $selectedActivityId } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$apiBase/favorites" -Headers $favoriteHeaders -ContentType 'application/json' -Body $favoriteBody
Invoke-RestMethod -Method Get -Uri "$apiBase/favorites" -Headers $favoriteHeaders
# 본인이 이번 검증에서 새로 생성한 관계만 삭제:
Invoke-WebRequest -UseBasicParsing -Method Delete -Uri "$apiBase/favorites/$selectedActivityId" -Headers $favoriteHeaders | Select-Object StatusCode
Remove-Variable loginResult, favoriteHeaders, favoriteBody
```

중복/오류 응답은 PowerShell에서 예외로 표시될 수 있습니다. 토큰이 든 변수/헤더나 자격정보가 담긴 로그인 요청을 출력하지 않습니다. 사용자 B 격리 검증은 두 번째 사용자의 직접 로그인으로 얻은 별도 JWT가 필요합니다. 실제 자료를 비공개로 바꾸는 테스트는 하지 않고 이번 격리 검증 결과를 사용합니다.

## 남은 위험과 승인 조건

MySQL DDL은 완전한 트랜잭션 롤백을 보장하지 않으므로 적용 중 실패하면 추가 DDL이나 자동 재실행 없이 실제 상태를 확인해야 합니다. 리허설 이후 DB/코드가 바뀌면 이번 백업과 비교 결과만으로 적용하지 않습니다. 실제 개발 계정 로그인과 실제 DB 즐겨찾기 생성은 아직 검증하지 않았으며, migration 미적용 상태에서는 새 API를 실제 사용하지 않습니다. 비공개 처리·페이지네이션 등 이전 구현 정책은 유지했으며 계약 변경은 별도 합의 대상입니다.
