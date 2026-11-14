# 즐겨찾기 개발 DB 최종 적용 결과

사용자가 승인한 **favorites.0001_initial 하나**를 로컬 dev의 기존 개발 DB에 적용했습니다. 기존 migration 재적용/수정, 사용자/활동지/카테고리 변경, 실제 테스트 계정/즐겨찾기 생성, 파일 변경, Git commit/push/PR/merge는 하지 않았습니다.

## 적용 전 사전 검증

실제 DB는 `yippee_club_db`, 포트 **3306**, 서버 UUID **5491c807-5688-11f1-a0bf-c86e08e6aa63**입니다. 매 SQL 실행 전에 DB/계정/포트/UUID를 확인했습니다.

기존 준비 증거 `.mysql-rehearsal/favorites-deploy-b36bb56183fa/report.json`의 성공 및 격리 서버 종료 기록, 전체 코드/migration 해시, 전체 DB 스키마/컬럼/행 해시/FK/이력, 기존 활동지 공개 API 응답, 저장 파일 20개와 원본 자료 8개 해시가 현재 상태와 정확히 일치했습니다. 전체 대기 migration은 favorites.0001_initial 하나였습니다.

승인된 백업 `yippee_club_db.sql`(28,412 bytes)의 SHA-256도 다음 값과 일치했습니다.

`35c1da37880452c8a236485379e0f128857ee4f52c34a8f269e2e9c48405ec53`

원본이 이전 성공 리허설 상태와 같고 백업/코드도 동일하므로 기존 검증된 백업을 사용했습니다. 별도 새 백업/복원 리허설을 반복하지 않았고, 요청된 전체 회귀 테스트는 허용된 기존 격리 MySQL에서 새로 실행했습니다.

## 실제 적용 결과

| 항목 | 적용 전 | 적용 후 |
|---|---:|---:|
| 테이블 | 22 | **23** |
| migration 이력 | 25 | **26** |
| favorites 행 | 테이블 없음 | **0** |
| 사용자 / 활성 관리자 | 0 / 0 | **0 / 0** |
| 공개 활동지 | 4 | **4**, ID 1~4·모두 0원 유지 |
| 카테고리 | 2 | **2**, ID 1·2 유지 |
| ContentType | 16 | **17** |
| Permission | 64 | **68** |
| 저장 파일 / 원본 자료 | 20 / 8 | **20 / 8**, 모든 해시 동일 |

신규 테이블 favorites는 다음 구조입니다.

- id: BigAutoField 기본 키.
- user_id: 기존 accounts_user.id FK.
- activity_id: 기존 activities.id FK.
- `unique_user_activity_favorite`: **(user_id, activity_id) 복합 UNIQUE**. 실제 information_schema의 NON_UNIQUE=0과 컬럼 순서로 확인했습니다.

신규 테이블/컬럼/FK 스키마와 메타데이터 내용은 성공 리허설의 보존용 업그레이드 복원본과 일치합니다. 새 migration 적용 시각을 제외한 실제 행 내용까지 대조했고, 기존 모든 migration 행과 업무 데이터는 그대로입니다. 기존 활동지의 가격 0원 CHECK 및 다른 제약도 기존 스키마 비교로 보존을 확인했습니다.

적용은 `scripts/apply_favorites_deploy.py`로 수행했습니다. 이 도구는 승인된 증거/백업을 고정하고 적용 직전 상태를 다시 비교합니다. SQL 변경 허용 범위를 favorites 생성 및 FK 추가, 정확한 신규 migration 기록·Favorite ContentType·네 Permission INSERT로 제한했습니다. 기존 업무 테이블의 ALTER/DROP/UPDATE/DELETE/INSERT는 허용하지 않습니다. 적용 실패 시 재실행/자동 복구하는 코드는 없습니다.

실제 기록된 변경 SQL 분류는 테이블 생성 1건, FK 제약 추가 2건, migration INSERT 1건, ContentType INSERT 1건, Permission 4행 INSERT 1건입니다. UNIQUE는 CREATE TABLE에 포함되었습니다. 예기치 않은 기존 테이블 DDL/DML은 없었습니다.

## 검사·회귀·공개 API

- 이번 전체 격리 테스트: **135개 중 133개 통과, 기존 preview 전용 2개 제외**. 즐겨찾기 14개, 동시성/UNIQUE/권한/응답 계약, 인증/이메일/아이/카테고리/활동지/파일 회귀 포함. 적용 직전 동일 코드 상태에서 실행했습니다.
- 실제 개발 DB Django system check: 오류 없음.
- `makemigrations --check --dry-run`: 변경 없음.
- `showmigrations favorites`: `[X] 0001_initial`.
- 전체 대기 migration: 없음.
- 실제 개발 DB 공개 API 목록/상세 응답: 기존 내용과 동일, 목록 count=4.
- 임시 loopback HTTP 서버를 통한 기존 공개 목록과 네 상세: 모두 200. PDF 4개·표지 4개 다운로드: 모두 200, 원본 SHA-256과 일치. 임시 서버는 정상 종료했습니다.
- 검색/카테고리/연령/난이도/시간/가격 등 공개 API 12개 조건과 없는 ID 404 검증 통과.
- 공개 API 검사 뒤 전체 DB 스냅샷이 검사 전과 동일함을 확인했습니다. 검사로 세션/사용자/즐겨찾기 등 실제 데이터를 생성하지 않았습니다.

실제 개발 DB에는 여전히 사용자/관리자가 없으므로 JWT를 이용한 인증된 즐겨찾기 쓰기 검증은 **미실행**입니다. 준비 단계의 독립 HTTP 복원본 검증 28건과 이번 전체 격리 회귀 결과를 활용합니다. 실제 사용은 사용자가 직접 회원가입하거나 관리자 계정을 준비한 뒤 진행합니다. 기존 [준비 문서](FAVORITES_DB_PREPARATION.md)의 계정 및 수동 검증 안내를 참고하세요. 이미 migration 적용이 완료되었으므로 적용 명령을 다시 실행할 필요는 없습니다.

## 보존 증거

적용 증거 디렉터리: `.mysql-rehearsal/favorites-apply-7dfeec326257/`

| 파일 | 내용 |
|---|---|
| apply-started.json | 승인된 단일 대상과 실제 DB 식별자 |
| migrate.txt | favorites.0001_initial 적용 성공 로그 |
| checks.txt | 실제 DB system check·migration 변경 검사·적용 이력 |
| report.json | 적용 전후 전체 스냅샷, 변경 SQL 분류, 기존 데이터/파일 보존, UNIQUE, 공개 API/HTTP 다운로드 검증 결과 |
| git-status.txt, git-audit.json | 최종 로컬 Git 변경 목록, 추적 제외 및 민감정보 점검 결과 |

전체 회귀 증거: `.mysql-rehearsal/child-tests-d2bff9656785/`. 기존 준비 증거와 백업은 덮어쓰거나 삭제하지 않았습니다.

## Git 및 민감정보

브랜치는 **dev**입니다. 기존 로컬 변경 사항은 그대로 보존했습니다. 전체 저장소의 추적 파일 수정 상태는 `.gitignore`, `config/settings.py`, `config/urls.py`, `requirements.txt` 네 개이며 이전 작업부터 있던 변경입니다.

기존 미추적 작업물은 activities/·favorites/ 앱, 리허설 설정 파일들, 활동지/즐겨찾기 문서들, 준비/검증 스크립트들입니다. 이번 단계에서는 `scripts/apply_favorites_deploy.py`와 이 결과 문서를 추가하고 기존 즐겨찾기 문서에 최신 상태 링크를 추가했습니다. 상세 파일별 상태는 git-status.txt에 보관합니다. 어떤 파일도 stage/commit/push하지 않았습니다.

`.env`, `.mysql-rehearsal/` 전체(백업·자격정보·스냅샷 포함), `private_uploads/`, `sample_activities/`, `local_dev/`는 Git 추적 제외 규칙을 확인했습니다. Git 반영 후보 파일에서 실제 환경의 SECRET_KEY/DB 비밀번호/이메일 비밀번호 값과 JWT 형식을 검사하되, 값 자체는 출력하지 않습니다. 확정되지 않은 토큰이나 비밀을 문서에 기록하지 않았습니다. 이는 현재 후보 파일에 대한 정적 점검 범위이며 향후 변경이나 GitHub 게시를 대신 승인하지 않습니다.

최종 Git 반영 후보 **141개 파일**에서 실제 비밀값/JWT 형식/개인 키 헤더 일치 **0건**입니다. 추적 파일 수정 4개 및 미추적 파일 40개가 있고, 민감한 위치 6개는 모두 추적 제외 확인을 통과했습니다. 파일별 목록과 검사 범위는 git-audit.json에 기록했습니다.

발견된 적용 오류는 없습니다. 남은 작업은 사용자 직접 계정 준비와 실제 JWT 사용자 기능 확인, 별도 요청에 따른 Git 반영입니다.
