# 인증 API 개발 안내

명세는 [API_SPEC_v1.5.md](API_SPEC_v1.5.md)와 [openapi_v1.5.yaml](openapi_v1.5.yaml)을 따른다.
현재 계약/정책의 미확정 사항은 [API_SPEC_ALIGNMENT.md](API_SPEC_ALIGNMENT.md),
실제 DB 적용 결과는 [AUTH_API_DEPLOYMENT.md](AUTH_API_DEPLOYMENT.md)에 기록했다.

## 포함 범위

accounts, email_verification, Django/DRF 설정, migration, 인증/프로필 테스트를 포함한다.
미완성 아이 관리 코드는 포함하지 않는다. 머신에 종속된 DB 생성/복원/권한 도구와
백업/자격정보/실행 증거는 로컬에 보존하고 Git에는 포함하지 않는다.

## DB 없는 검사

```bash
python manage.py check --settings=config.user_model_preview
python manage.py test accounts.test_preparation accounts.tests config email_verification.tests.AuthUnitTests --settings=config.user_model_preview --noinput
```

이 설정은 MySQL 연결 생성 자체를 거부한다. 개발 DB에 테스트 데이터를 만들지 않는다.

## 격리 MySQL 통합 테스트

별도 MySQL 인스턴스를 loopback 포트 33307, server_id 9133307로 준비해야 한다.
기존 개발/공유 테스트 DB를 재사용하지 않는다. 전용 계정은 yippee_rehearsal이고,
test_yippee_migration_fresh와 test_yippee_migration_suite 두 빈 스키마에만 필요한 권한을 부여한다.
설정/스키마/권한 생성은 테스트 명령에 포함되지 않으며 환경 담당자가 별도로 준비한다.

비밀 저장소나 세션 환경변수로 다음을 제공한다. 비밀번호를 코드/명령 기록/로그에 넣지 않는다.

- YIPPEE_REHEARSAL_DATABASE: test_yippee_migration_fresh
- YIPPEE_REHEARSAL_PORT: 33307
- YIPPEE_REHEARSAL_PASSWORD: 전용 테스트 계정의 비밀번호

격리 서버와 빈 테스트 DB를 확인한 후:

```bash
python manage.py test --settings=config.user_model_rehearsal --keepdb --noinput
```

--keepdb도 migration과 테스트 데이터 쓰기를 수행한다. 격리 설정이 일반 개발 설정으로
바뀌지 않았는지 확인해야 하며, 개발 DB/기존 공유 테스트 DB에서는 실행하지 않는다.
최종 검증 기록은 70개 성공, 2개 오프라인 전용 skip 및 실제 TCP HTTP 검사 20개 성공이다.

## 환경 파일

.env.example은 비작동 예시이며 실제 SECRET_KEY/DB/SMTP 자격정보로 로컬에서 설정한다.
.env, 환경별 .env 파일, .venv, .mysql-rehearsal, SQL dump와 client 자격정보는 Git 제외 대상이다.
