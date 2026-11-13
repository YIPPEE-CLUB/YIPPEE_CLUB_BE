# TEAM_YIPPE_CLUB_BE
YIPPEE CLUB Backend API Server

Python 3.12, Django 5.2 LTS, Django REST Framework, MySQL 기반 백엔드입니다.
환경변수는 django-environ으로 읽으며 JWT 인증과 CORS 설정을 포함합니다.
이메일 인증, 회원가입·로그인, JWT 갱신·로그아웃, 프로필 및 비밀번호 API를 구현했습니다.
아이 관리 API는 이번 범위에 포함하지 않습니다.

## 로컬 설치

Python 3.12와 MySQL 8.0.11 이상을 설치한 뒤 저장소 루트에서 실행합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS/Linux에서는 `python3.12 -m venv .venv`와 `source .venv/bin/activate`를 사용합니다.
mysqlclient 설치 시 소스 빌드가 필요한 환경에서는 MySQL/MariaDB 개발 라이브러리,
컴파일러, pkg-config가 필요합니다. Ubuntu에서는 다음을 먼저 설치할 수 있습니다.

```bash
sudo apt-get install python3-dev default-libmysqlclient-dev build-essential pkg-config
```

## MySQL DB 생성

MySQL 관리자 계정으로 접속합니다.

```bash
mysql -u root -p
```

로컬 개발용 DB와 계정을 생성합니다. 비밀번호는 실제 환경에 맞게 변경하세요.

```sql
CREATE DATABASE yippee_club_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'yippee_user'@'localhost' IDENTIFIED BY 'local-dev-password';
GRANT ALL PRIVILEGES ON yippee_club_db.* TO 'yippee_user'@'localhost';
```

## 환경변수 설정

`.env.example`을 복사해 루트에 `.env`를 직접 생성합니다.

```powershell
Copy-Item .env.example .env
```

macOS/Linux에서는 `cp .env.example .env`를 사용합니다.

- `SECRET_KEY`: 개발 예시값을 고유한 비밀키로 변경합니다.
- `DEBUG`: 로컬에서는 `True`, 배포에서는 `False`로 설정합니다.
- `ALLOWED_HOSTS`: 쉼표로 구분한 호스트 이름입니다. 스킴과 포트를 넣지 않습니다.
- `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_HOST`, `MYSQL_PORT`: 생성한 MySQL DB 연결 정보입니다.
- `CORS_ALLOWED_ORIGINS`: 허용할 프런트엔드 origin 목록입니다. 스킴과 포트를 포함하고 쉼표로 구분합니다.

프로세스에 이미 설정된 환경변수가 `.env`보다 우선합니다.
`.env`는 Git에서 제외되며, 저장소에는 예시 파일만 포함합니다.
DB 설정이 없거나 MySQL 연결에 실패하면 오류를 표시하며 SQLite로 전환하지 않습니다.

## 검사, 마이그레이션 및 서버 실행

```bash
python manage.py check
python manage.py migrate
python manage.py runserver
```

`check`는 일반적인 설정 검사이며 실제 DB 연결 성공을 보장하지 않습니다.
`migrate`는 실행 중인 MySQL 서버와 올바른 DB 권한이 필요합니다.
위 명령은 신규 DB용입니다. 기존 auth.User DB는 먼저
[검증된 User 이관 절차](docs/USER_MIGRATION_STAGE1.md)를 검토해야 합니다.

```bash
curl http://127.0.0.1:8000/api/v1/health/
```

응답은 HTTP 200, `{"status":"ok"}`입니다. 인증과 DB 조회 없이 프로세스 상태를 확인합니다.
기본 DRF 인증은 JWT이며 헬스 체크는 공개 엔드포인트입니다.

DB를 생성하거나 연결하지 않는 헬스 체크 테스트:

```bash
python manage.py test config
```

## 인증 API 및 검증

명세 기준은 [API_SPEC_v1.5.md](docs/API_SPEC_v1.5.md)와
[openapi_v1.5.yaml](docs/openapi_v1.5.yaml)이며 Markdown 0절의 확정 정책을 우선합니다.
구현된 12개 operation의 URL·요청·응답 비교는 [계약 비교](docs/API_SPEC_ALIGNMENT.md)를 참조하세요.

개발 DB의 커스텀 User 및 인증 migration 적용을 완료했습니다(16개 테이블, 22개 migration).
테스트 결과와 남은 정책은 [인증 API 적용 기록](docs/AUTH_API_DEPLOYMENT.md)에 정리했습니다.
실제 SMTP 발송에는 공급자 설정이 필요합니다.

DB에 연결하지 않는 안전한 검사:

```bash
python manage.py check --settings=config.user_model_preview
python manage.py test accounts.test_preparation accounts.tests config email_verification.tests.AuthUnitTests --settings=config.user_model_preview --noinput
```

MySQL API 테스트는 개발 DB 및 기존 공유 테스트 DB에서 실행하지 않습니다.
격리 설정과 실행 조건은 [개발 안내](docs/AUTH_API.md)를 참조하세요.
