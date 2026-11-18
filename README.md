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

## 운영 보안 설정

`.env.example`의 HTTPS 설정은 로컬 HTTP 개발에 맞춘 기본값입니다. 운영에서는 배포 환경의 시크릿 저장소에서 `SECRET_KEY`를 주입하고 `DEBUG=False`와 실제 `ALLOWED_HOSTS`를 지정하세요. 직접 교차 출처 요청이 필요한 경우에만 `CORS_ALLOWED_ORIGINS`에 승인한 출처를 넣으세요. 세션을 사용하는 교차 출처 요청에는 `CSRF_TRUSTED_ORIGINS`에 필요한 HTTPS 출처를 별도로 지정하세요.

- **HTTPS와 쿠키** — HTTPS가 동작하면 `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`를 적용하세요. HTTP → HTTPS 전환을 Django에서 처리할 경우 `SECURE_SSL_REDIRECT=True`를 지정하세요. 프록시가 TLS를 종료한다면 HTTPS 요청이 리다이렉트 루프에 빠지지 않는지 확인하세요.
- **프록시 신뢰** — 기본 설정에서 `SECURE_PROXY_SSL_HEADER`는 비어 있습니다. 외부 클라이언트가 보낸 스킴 헤더를 프록시가 제거하고 검증된 스킴을 직접 설정하며 백엔드 직접 접근이 차단된 경우에만 운영 설정에서 해당 헤더를 신뢰하도록 구성하세요.
- **HSTS** — `SECURE_HSTS_SECONDS` 기본값은 `0`입니다. 대상 호스트에서 HTTPS를 검증한 뒤 짧은 기간부터 적용하세요. 모든 하위 도메인이 HTTPS를 지원하는 경우에만 `SECURE_HSTS_INCLUDE_SUBDOMAINS`를 활성화하세요. `SECURE_HSTS_PRELOAD`는 장기 적용과 해제 절차까지 검토한 뒤 결정하세요.
- **관리자 접근** — 공개 배포 전에 `/admin/` 접근을 VPN 또는 접근 게이트웨이 등으로 제한하고 관리자 MFA와 역할별 최소 권한을 구성하세요. 애플리케이션에서는 Django의 활성 staff 및 모델 권한 검사를 사용합니다.
- **원본 IP와 요청 제한** — 인증 API는 WSGI/ASGI 요청의 `REMOTE_ADDR`를 사용합니다. 배포 후보 환경에서 검증된 클라이언트 주소가 `REMOTE_ADDR`에 전달되도록 구성하고, 장비를 통과하는 서로 다른 클라이언트의 한도가 분리되는지와 외부 전달 헤더가 무시되는지 확인하세요.
- **응답 캐시** — 인증·계정·아이·찜·장바구니 응답에 `private, no-store`가 적용됩니다. 프록시나 CDN에서도 이를 준수하고, 서로 다른 인증 사용자에게 응답을 재사용하지 않는지 확인하세요.

배포 전에 운영 후보 설정으로 `python manage.py check --deploy`를 실행하세요. HTTPS 전환을 프록시가 맡는 경우 실제 HTTP 요청으로 전환 동작을 검증하세요.

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
