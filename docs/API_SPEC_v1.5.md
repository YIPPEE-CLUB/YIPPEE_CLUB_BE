# YIPPEE CLUB API 상세 명세서
- Base URL: `/api/v1`
- 기준: 99개 API, Django REST Framework + MySQL
- 문서 상태: **팀 공유용 v1.5 — 확정 정책 반영 / 일부 세부 계약 검토 필요**
- 1차 핵심 구현: 이메일 인증·가입/JWT, 프로필, 다중 아이·공통 카테고리, 활동지 목록·상세·검색, 찜·장바구니. 아래 0절의 단계 구분을 우선 적용합니다.
- 1차 핵심 구현 제외: 실제 PG 결제·환불, 소셜 로그인, 외부 실명 인증, 쿠폰, 캐시·포인트, 성장 리포트, 활동 기록 수정·삭제 API(아이 삭제 시 연관 기록 자동 삭제와 구별).
- Nullable: `O` = null 허용, `X` = null 불가
- 인증: `Authorization: Bearer <access_token>` (제안)

## 0. 팀 합의 사항 및 개발 범위 (2026-11-06 확정)

> **읽는 순서:** 이 0절의 확정 정책이 뒤의 기존 API별 예시·제안 문구보다 우선합니다. 99개 API는 서비스 전체의 설계 목록이며, 모두 1차 구현 대상이라는 뜻이 아닙니다. 상세 표에 남은 `선택`, `미확정`, 예시 값은 실제 구현 전 팀 검토가 필요합니다.

### 0-1. 확정 정책

| 구분 | 확정 내용 | 개발 반영 기준 |
|---|---|---|
| 기술 | Django REST Framework + MySQL | 서버 API 및 관계형 DB 구현 |
| 가입 | 이메일·비밀번호 가입 우선, **이메일 인증번호 확인 필수** | 인증 성공 증빙이 없는 가입 거부; 인증번호 재사용 금지 |
| 인증 | JWT 기반 로그인 유지 | Access/Refresh 토큰 사용; 세부 만료·회전 정책은 별도 확정 |
| 아이 | 회원 1명이 여러 아이 등록 가능 | `children.user_id`로 소유권 확인 |
| 관심사 | 아이 1명당 여러 관심 카테고리 선택 가능 | 중복 선택 방지; 존재하는 카테고리만 허용 |
| 카테고리 | **아이 관심 카테고리와 활동지 카테고리 동일한 목록 사용** | 단일 `categories` 테이블 참조; `child_interests`, `activity_categories` 연결 테이블 사용 |
| 아이 삭제 | **해당 아이와 연결된 활동 기록도 삭제** | 본인 소유 확인 후 DB 기록 및 연결 사진 파일 삭제 처리; 주문·결제 데이터는 별도 보존 정책 |
| 활동지 등록 | **초기 제목·설명·가격·이미지는 관리자가 업로드** | 일반 회원의 등록/수정 금지; 관리자 입력 경로는 구현 방식 검토 |
| 장바구니 | **이미 구매한 활동지는 장바구니에 담을 수 없음** | 서버에서 유효한 구매 권한 검사 후 409 등 충돌 응답; 찜과는 별개 |
| 범위 | 핵심 기능 우선 개발 | 외부 결제·소셜·실명인증은 1차 핵심 구현에서 제외 |

### 0-2. 1차 개발 대상과 후속 개발 대상

| 단계 | 기능 | API 범위 / 메모 |
|---|---|---|
| 1차 필수 | 이메일 인증·가입·로그인·토큰 | 01, 02, 05~07, 09~10 (번호는 본 문서 API 상세 번호). 이메일 인증 확인 후 가입; 실제 메일 발송 연동 필요 |
| 1차 필수 | 내 프로필, 아이 등록·조회·수정·선택·삭제 | 16~17, 20~25. 아이 삭제 시 연관 활동 기록 삭제 |
| 1차 필수 | 카테고리, 활동지 목록·상세, 기본 검색·필터 | 27~36 중 필요한 조회 API, 37 등. 실제 카테고리 코드 목록은 확정 필요 |
| 1차 필수 | 찜, 장바구니 | 41~46. 구매 권한이 있으면 장바구니 담기 거부 |
| 1차 보조 | 관리자 초기 활동지 데이터 등록 | Django Admin 활용 또는 별도 관리자 API 검토; **현재 99개 목록에는 관리자 등록 API가 명시되지 않음** |
| 후속 | 실제 주문·결제·환불·카드, 소셜 로그인, 외부 실명인증 | 상세 명세는 보존하되 실서비스 연동은 정책·업체 확정 후 |
| 후속/검토 | 리뷰·활동 기록 작성·배지·알림·이벤트·문의 등 | 1차 핵심 구현 완료 후 우선순위 재협의 |
| 우선 제외 | 쿠폰, 캐시·포인트, 성장 리포트, 활동 기록 수정·삭제 API | 목록·상세 명세는 향후 개발 참고용으로 유지 |

### 0-3. 프론트엔드와 백엔드 간 필수 합의

- **회원가입 순서:** 이메일 입력 → 인증번호 발송(`POST /auth/verification/send`) → 인증번호 확인(`POST /auth/verification/confirm`) → 검증된 `verification_token`으로 가입(`POST /auth/signup`). 기존 상세 명세의 `password` 선택 표기는 **이메일 가입에 한해 필수**로 해석합니다.
- **카테고리 데이터:** `GET /activity-categories`의 카테고리 식별자를 아이 등록/수정 `interests` 배열과 활동지 카테고리 연결에 공통 사용합니다. **식별자 타입(코드 문자열 또는 정수 ID), 실제 목록은 미확정**이며 확정 후 예시·DB 필드를 일괄 통일합니다.
- **아이 삭제:** `DELETE /children/{child_id}`는 아이 및 해당 아이의 활동 기록을 함께 삭제합니다. 연결된 사진의 스토리지 삭제/비동기 정리 방식은 별도 결정하며, 타인의 아이 삭제는 금지합니다.
- **장바구니 담기:** `POST /cart/items`는 인증 사용자에 대해 기존 구매 권한을 검사합니다. 이미 구매한 활동지는 `409 ALREADY_PURCHASED`로 거부하는 **v1.5 제안 계약**을 사용합니다(최종 오류 코드 팀 확인 필요). 구매 권한 판별 모델로 `purchase_entitlements`를 제안합니다.
- **관리자:** 활동지 초기 등록 데이터는 관리자만 입력합니다. 우선 Django Admin을 사용하는 방안을 제안하며, 관리자 API가 필요하면 99개 API 외에 별도 명세를 추가합니다.

---

## 1. 공통 API 계약

### 1. 요청/응답 표준
- Content-Type: `application/json; charset=utf-8`; 파일 업로드는 `multipart/form-data`.
- 시간: UTC ISO 8601 문자열(`2026-11-06T13:00:00Z`), 날짜: `YYYY-MM-DD`.
- 금액: 원화 정수(`integer`, 소수점 없음). **서버 계산 금액을 신뢰**하고 클라이언트 금액을 최종 결제에 사용하지 않습니다.
- ID: 본 문서에서는 `integer`로 제안하되 DB PK 정책 변경 시 API 전체를 일괄 수정해야 합니다.
- 인증: 제안은 JWT Bearer access token. refresh token 저장/회전/폐기 방식은 구현 전에 결정합니다.
- 페이지 목록: `count`, `next`(string|null), `previous`(string|null), `results`(array). 기존 각 API의 단순 `results` 응답은 이 규칙으로 정규화할 것을 제안합니다. **개별 표와 충돌 시 구현 전 표를 수정**합니다.
- `Nullable: X`와 `선택`은 다릅니다. 선택 필드는 생략할 수 있지만 null을 전송할 수는 없습니다.
- 인증이 필요한 API에서 리소스 소유권은 반드시 DB에서 확인합니다. 타인의 아이·주문·기록·문의에는 접근할 수 없어야 합니다.

### 2. 오류 응답
```json
{
  "code": "VALIDATION_ERROR",
  "message": "요청값을 확인해 주세요.",
  "details": {"identifier": ["올바른 이메일 또는 전화번호를 입력하세요."]},
  "request_id": "req_test_001"
}
```
| HTTP | 제안 코드 | 의미 |
|---|---|---|
| 400 | VALIDATION_ERROR | 형식·필수 필드 오류 |
| 401 | AUTHENTICATION_REQUIRED / TOKEN_EXPIRED | 인증 실패·만료 |
| 403 | PERMISSION_DENIED | 소유권·권한 부족 |
| 404 | NOT_FOUND | 대상 없음 또는 노출 불가 |
| 409 | ALREADY_EXISTS / INVALID_STATE | 중복·상태 충돌 |
| 422 | BUSINESS_RULE_VIOLATION | 연령·판매·환불 등 업무 규칙 위반 |
| 429 | RATE_LIMITED | 호출 제한 |
| 500 | INTERNAL_SERVER_ERROR | 서버 오류 (내부 정보 비노출) |
| 503 | SERVICE_UNAVAILABLE | 점검·일시 장애 |

### 3. 제안 Enum 및 검증 기준 (서버와 프론트 합의 필요)
| 필드 | 제안 허용값 | 상태 |
|---|---|---|
| `identifier_type` | `email`, `phone` | 제안 |
| `purpose` | `signup`, `password_reset`, `phone_change` | 제안 |
| 소셜 `provider` | `kakao`, `naver`, `apple` | 화면 확인 / 표기 제안 |
| `gender` | `female`, `male`, `unspecified` | 제안; 선택값 정책 미정 |
| `duration` | `5-10`, `10-20`, `20-plus` | 화면 기반 제안 |
| `place` | `indoor`, `outdoor` | 화면 기반 제안 |
| `sort` | `popular`, `latest`, `price_asc`, `price_desc` | 화면에서 인기순 확인; 나머지 미확정 |
| `sale_status` | `on_sale`, `sold_out`, `discontinued` | 제안 |
| 주문 `status` | `pending`, `paid`, `cancelled`, `payment_failed`, `refunded` | 제안 |
| 문의 `status` | `waiting`, `answered` | 화면 기반 제안 |
| 이벤트 `status` | `ongoing`, `ended` | 화면 기반 제안 |
| `platform` | `android`, `ios`, `web` | 앱 배포 방식 미확정 |

- 비밀번호: 화면에 **영문·숫자 포함 8자 이상** 표시. 최대 길이·특수문자 정책은 미확정.
- 인증번호: 화면에 **6자리**, **03:00** 타이머 표시. 서버 만료 180초는 제안이며 재전송·시도 제한은 미확정.
- 아이 연령: 화면에 **12~72개월** 표시. 생년월일의 기준 시각·경계 처리, 초과 연령의 기존 계정 접근 정책은 미확정.
- 리뷰: 구매 후 작성 화면 확인. 구매 1건당 리뷰 허용 개수·삭제 후 재작성·배지 중복 지급은 미확정.



## 2. 전체 API 목록

### 인증·회원

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `POST` | `/auth/identifiers/check` | 이메일/전화번호 가입 여부 확인 |
| `POST` | `/auth/verification/send` | 이메일/휴대전화 인증번호 발송(가입 방식별 정책 확정 필요) |
| `POST` | `/auth/identity/start` | 실명 본인확인 시작(외부 인증사 연동 제안) |
| `POST` | `/auth/identity/confirm` | 본인확인 결과 검증(인증사 연동 제안) |
| `POST` | `/auth/verification/confirm` | 6자리 인증번호 검증 |
| `POST` | `/auth/signup` | 회원가입 완료 |
| `POST` | `/auth/login` | 이메일·비밀번호 로그인 |
| `POST` | `/auth/social/{provider}` | 카카오·네이버·Apple 로그인 |
| `POST` | `/auth/token/refresh` | 토큰 갱신 |
| `POST` | `/auth/logout` | 로그아웃 |
| `POST` | `/auth/password/reset-request` | 비밀번호 재설정 메일 |
| `POST` | `/auth/password/reset-confirm` | 새 비밀번호 설정 |
| `PATCH` | `/users/me/password` | 로그인 상태 비밀번호 변경 |
| `PATCH` | `/users/me/phone` | 인증 후 휴대전화 변경 |
| `DELETE` | `/users/me` | 회원 탈퇴 |

### 프로필·아이

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/users/me` | 내 프로필 조회 |
| `PATCH` | `/users/me` | 프로필 편집 |
| `POST` | `/users/me/profile-photo` | 프로필 사진 등록·변경(업로드 방식 제안) |
| `DELETE` | `/users/me/profile-photo` | 프로필 사진 삭제 |
| `GET` | `/children` | 아이 목록 |
| `POST` | `/children` | 아이 등록 |
| `GET` | `/children/{child_id}` | 아이 상세 |
| `PATCH` | `/children/{child_id}` | 아이 정보 수정 |
| `DELETE` | `/children/{child_id}` | 아이 삭제 |
| `PUT` | `/users/me/active-child` | 현재 선택 아이 변경 |

### 홈·검색·추천

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/home` | 홈 콘텐츠 |
| `GET` | `/activities` | 활동지 목록·검색·필터·정렬 |
| `GET` | `/activities/{activity_id}` | 활동지 상세 |
| `GET` | `/activities/popular` | 인기 활동지 |
| `GET` | `/search/trending` | 인기 검색어 |
| `GET` | `/search/suggestions` | 검색 입력 중 자동완성 제안 |
| `GET` | `/search/recent` | 최근 검색어 |
| `POST` | `/search/recent` | 검색어 기록 |
| `DELETE` | `/search/recent` | 최근 검색어 전체 삭제 |
| `DELETE` | `/search/recent/{search_id}` | 최근 검색어 개별 삭제 |
| `POST` | `/recommendations/one-click` | 맞춤 놀이 조건 검색 |
| `GET` | `/activity-categories` | 놀이 카테고리 및 안내 |

### 활동지 파일·저장

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/activities/{activity_id}/preview` | 구매 전 미리보기 |
| `GET` | `/purchases/activities` | 구매한 활동지 |
| `POST` | `/activities/{activity_id}/download` | 구매 파일 다운로드 권한 발급 |
| `GET` | `/favorites` | 찜 목록 |
| `POST` | `/favorites` | 찜 추가 |
| `DELETE` | `/favorites/{activity_id}` | 찜 해제 |

### 장바구니·결제·카드

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/cart` | 장바구니 |
| `POST` | `/cart/items` | 장바구니 담기 |
| `DELETE` | `/cart/items/{activity_id}` | 장바구니에서 삭제 |
| `POST` | `/orders/quote` | 결제 예상 금액 산정 |
| `POST` | `/orders` | 주문 생성 |
| `POST` | `/payments/confirm` | PG 결제 검증 및 확정 |
| `POST` | `/payments/webhook` | PG 웹훅 수신 |
| `GET` | `/orders` | 결제 내역 |
| `GET` | `/orders/{order_id}` | 결제 상세 |
| `GET` | `/orders/{order_id}/receipt` | 영수증 |
| `POST` | `/orders/{order_id}/cancel` | 결제 취소 요청 |
| `GET` | `/payment-methods` | 등록 결제 수단 |
| `POST` | `/payment-methods` | 결제수단 토큰 등록 |
| `PATCH` | `/payment-methods/{method_id}` | 기본 카드 설정 |
| `DELETE` | `/payment-methods/{method_id}` | 결제수단 삭제 |

### 쿠폰·캐시·포인트 (우선 제외)

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/coupons` | 보유 쿠폰 — **우선 제외** |
| `POST` | `/coupons/redeem` | 쿠폰 코드 등록 — **우선 제외** |
| `GET` | `/coupons/{coupon_id}` | 쿠폰 상세 — **우선 제외** |
| `GET` | `/wallet/cash` | 캐시 잔액 — **우선 제외** |
| `GET` | `/wallet/cash/transactions` | 캐시 이용 내역 — **우선 제외** |
| `POST` | `/wallet/cash/topups` | 캐시 충전 주문 — **우선 제외** |
| `GET` | `/wallet/points` | 포인트 잔액 — **우선 제외** |
| `GET` | `/wallet/points/transactions` | 포인트 적립·사용 내역 — **우선 제외** |

### 활동 인증·리뷰·배지

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/activities/{activity_id}/reviews` | 활동지 리뷰 |
| `POST` | `/activities/{activity_id}/reviews` | 구매 후 리뷰 등록 |
| `DELETE` | `/reviews/{review_id}` | 리뷰 삭제 |
| `POST` | `/reviews/{review_id}/helpful` | 도움돼요 |
| `POST` | `/reviews/{review_id}/reports` | 리뷰 신고 |
| `GET` | `/activity-records` | 아이 활동 기록 |
| `POST` | `/activity-records` | 활동 인증·기록 |
| `PATCH` | `/activity-records/{record_id}` | 활동 기록 수정 — **우선 제외** |
| `DELETE` | `/activity-records/{record_id}` | 활동 기록 삭제 — **우선 제외** |
| `GET` | `/children/{child_id}/badges` | 만세도감 |
| `PATCH` | `/children/{child_id}/featured-badge` | 대표배지 설정 |
| `GET` | `/children/{child_id}/growth-report` | 성장 리포트 — **우선 제외** |

### 콘텐츠·알림·고객센터

| Method | Endpoint (`/api/v1` 뒤) | 설명 |
|---|---|---|
| `GET` | `/guides` | 부모님 가이드북 목록 |
| `GET` | `/guides/{guide_id}` | 가이드북 상세 |
| `GET` | `/events` | 이벤트 목록 |
| `GET` | `/events/{event_id}` | 이벤트 상세 |
| `POST` | `/events/{event_id}/participations` | 이벤트 참여 |
| `GET` | `/notifications` | 알림 목록 |
| `PATCH` | `/notifications/read-all` | 전체 읽음 |
| `PATCH` | `/notifications/{notification_id}/read` | 개별 알림 읽음(제안) |
| `DELETE` | `/notifications` | 전체 알림 삭제 |
| `GET` | `/users/me/notification-settings` | 알림 설정 |
| `PATCH` | `/users/me/notification-settings` | 알림 설정 변경 |
| `GET` | `/faqs` | FAQ 검색 |
| `GET` | `/notices` | 공지사항 |
| `GET` | `/notices/{notice_id}` | 공지 상세 |
| `GET` | `/inquiries` | 1:1 문의 내역 |
| `POST` | `/inquiries` | 1:1 문의 접수 |
| `GET` | `/inquiries/{inquiry_id}` | 문의 상세·답변 |
| `PATCH` | `/inquiries/{inquiry_id}` | 미답변 문의 수정 |
| `DELETE` | `/inquiries/{inquiry_id}` | 문의 삭제 |
| `GET` | `/policies/{policy_type}` | 약관·개인정보·환불정책 |
| `GET` | `/app/config` | 앱 버전·점검 상태·강제/선택 업데이트 판단 정보 |


## 3. API별 상세 명세

## 01. 이메일/전화번호 가입 여부 확인
**`POST /api/v1/auth/identifiers/check`**

기능: 이메일/전화번호 가입 여부 확인.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `identifier` | identifier 값 | string | Body / 필수 | X | `user@example.com` |

**Request Example**
```json
{
  "identifier": "user@example.com"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `registered` | registered 값 | boolean | 응답 / 필수 | X | `true` |
| `identifier_type` | identifier type 값 | string | 응답 / 필수 | X | `email` |

**Example**
```json
{
  "registered": true,
  "identifier_type": "email"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 02. 이메일/휴대전화 인증번호 발송(가입 방식별 정책 확정 필요)
**`POST /api/v1/auth/verification/send`**

**v1.5 확정:** 1차 가입 인증은 이메일로 발송합니다. 인증번호 확인은 필수이며 발송 제한·만료 시간은 별도 검토합니다.

기능: 이메일/휴대전화 인증번호 발송(가입 방식별 정책 확정 필요).

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `identifier` | identifier 값 | string | Body / 필수 | X | `user@example.com` |
| `purpose` | purpose 값 | string | Body / 필수 | X | `signup` |

**Request Example**
```json
{
  "identifier": "user@example.com",
  "purpose": "signup"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `verification_id` | verification id 값 | string | 응답 / 필수 | X | `ver_test_001` |
| `expires_in_seconds` | expires in seconds 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "verification_id": "ver_test_001",
  "expires_in_seconds": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 03. 실명 본인확인 시작(외부 인증사 연동 제안)
**`POST /api/v1/auth/identity/start`**

기능: 실명 본인확인 시작(외부 인증사 연동 제안).

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `purpose` | purpose 값 | string | Body / 필수 | X | `signup` |

**Request Example**
```json
{
  "purpose": "signup"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `verification_url` | verification url 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `transaction_id` | transaction id 값 | string | 응답 / 필수 | X | `txn_test_001` |

**Example**
```json
{
  "verification_url": "UNSPECIFIED",
  "transaction_id": "txn_test_001"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 04. 본인확인 결과 검증(인증사 연동 제안)
**`POST /api/v1/auth/identity/confirm`**

기능: 본인확인 결과 검증(인증사 연동 제안).

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `transaction_id` | transaction id 값 | string | Body / 필수 | X | `txn_test_001` |
| `provider_token` | provider token 값 | string | Body / 필수 | X | `provider_test_token` |

**Request Example**
```json
{
  "transaction_id": "txn_test_001",
  "provider_token": "provider_test_token"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `identity_verification_token` | identity verification token 값 | string | 응답 / 필수 | X | `identity_test_001` |
| `verified` | verified 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "identity_verification_token": "identity_test_001",
  "verified": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 05. 6자리 인증번호 검증
**`POST /api/v1/auth/verification/confirm`**

**v1.5 확정:** 이메일 인증번호 검증 성공 시 가입에 사용할 일회성 `verification_token`을 발급하고 재사용을 금지합니다.

기능: 6자리 인증번호 검증.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `verification_id` | verification id 값 | string | Body / 필수 | X | `ver_test_001` |
| `code` | code 값 | string | Body / 필수 | X | `123456` |

**Request Example**
```json
{
  "verification_id": "ver_test_001",
  "code": "123456"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `verification_token` | verification token 값 | string | 응답 / 필수 | X | `vtoken_test_001` |
| `verified` | verified 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "verification_token": "vtoken_test_001",
  "verified": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 06. 회원가입 완료
**`POST /api/v1/auth/signup`**

**v1.5 확정:** 이메일·비밀번호 가입만 우선 구현합니다. 이메일 인증 완료 `verification_token`이 필수이고, 이메일 가입에서 `password`는 **필수**입니다. 아래 기존 표의 `password 선택` 표기보다 이 규칙이 우선합니다.

기능: 회원가입 완료.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `identifier` | identifier 값 | string | Body / 필수 | X | `user@example.com` |
| `verification_token` | verification token 값 | string | Body / 필수 | X | `vtoken_test_001` |
| `agreements` | agreements 값 | object | Body / 필수 | X | `{}` |
| `password` | password 값 | string | Body / 선택 | O | `Password123` |

**Request Example**
```json
{
  "identifier": "user@example.com",
  "verification_token": "vtoken_test_001",
  "agreements": {},
  "password": "Password123"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `user_id` | user id 값 | integer | 응답 / 필수 | X | `1` |
| `access_token` | access token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `refresh_token` | refresh token 값 | string | 응답 / 필수 | X | `eyJ...` |

**Example**
```json
{
  "user_id": 1,
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 07. 이메일·비밀번호 로그인
**`POST /api/v1/auth/login`**

기능: 이메일·비밀번호 로그인.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `email` | email 값 | string | Body / 필수 | X | `user@example.com` |
| `password` | password 값 | string | Body / 필수 | X | `Password123` |

**Request Example**
```json
{
  "email": "user@example.com",
  "password": "Password123"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `access_token` | access token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `refresh_token` | refresh token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `user` | user 값 | object | 응답 / 필수 | X | `{}` |

**Example**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": {}
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 08. 카카오·네이버·Apple 로그인
**`POST /api/v1/auth/social/{provider}`**

기능: 카카오·네이버·Apple 로그인.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `provider` | provider 값 | string | Path / 필수 | X | `kakao` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `authorization_code` | authorization code 값 | string | Body / 필수 | X | `(미확정 예시)` |
| `redirect_uri` | redirect uri 값 | string | Body / 선택 | O | `(미확정 예시)` |

**Request Example**
```json
{
  "authorization_code": "UNSPECIFIED",
  "redirect_uri": "UNSPECIFIED"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `access_token` | access token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `refresh_token` | refresh token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `is_new_user` | is new user 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "is_new_user": true
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 09. 토큰 갱신
**`POST /api/v1/auth/token/refresh`**

기능: 토큰 갱신.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `refresh_token` | refresh token 값 | string | Body / 필수 | X | `eyJ...` |

**Request Example**
```json
{
  "refresh_token": "eyJ..."
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `access_token` | access token 값 | string | 응답 / 필수 | X | `eyJ...` |
| `refresh_token` | refresh token 값 | string | 응답 / 필수 | X | `eyJ...` |

**Example**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 10. 로그아웃
**`POST /api/v1/auth/logout`**

기능: 로그아웃.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `refresh_token` | refresh token 값 | string | Body / 선택 | O | `eyJ...` |

**Request Example**
```json
{
  "refresh_token": "eyJ..."
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 11. 비밀번호 재설정 메일
**`POST /api/v1/auth/password/reset-request`**

기능: 비밀번호 재설정 메일.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `email` | email 값 | string | Body / 필수 | X | `user@example.com` |

**Request Example**
```json
{
  "email": "user@example.com"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 12. 새 비밀번호 설정
**`POST /api/v1/auth/password/reset-confirm`**

기능: 새 비밀번호 설정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `reset_token` | reset token 값 | string | Body / 필수 | X | `reset_test_token` |
| `new_password` | new password 값 | string | Body / 필수 | X | `NewPassword123` |

**Request Example**
```json
{
  "reset_token": "reset_test_token",
  "new_password": "NewPassword123"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 429 | 인증 시도 횟수 초과 |
| 500 | 서버 내부 오류 |

---

## 13. 로그인 상태 비밀번호 변경
**`PATCH /api/v1/users/me/password`**

기능: 로그인 상태 비밀번호 변경.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `current_password` | current password 값 | string | Body / 필수 | X | `(미확정 예시)` |
| `new_password` | new password 값 | string | Body / 필수 | X | `NewPassword123` |

**Request Example**
```json
{
  "current_password": "UNSPECIFIED",
  "new_password": "NewPassword123"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 14. 인증 후 휴대전화 변경
**`PATCH /api/v1/users/me/phone`**

기능: 인증 후 휴대전화 변경.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `new_phone` | new phone 값 | string | Body / 필수 | X | `01012345678` |
| `verification_token` | verification token 값 | string | Body / 필수 | X | `vtoken_test_001` |

**Request Example**
```json
{
  "new_phone": "01012345678",
  "verification_token": "vtoken_test_001"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `phone` | phone 값 | string | 응답 / 필수 | X | `01012345678` |
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "phone": "01012345678",
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 15. 회원 탈퇴
**`DELETE /api/v1/users/me`**

기능: 회원 탈퇴.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 16. 내 프로필 조회
**`GET /api/v1/users/me`**

기능: 내 프로필 조회.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `email` | email 값 | string | 응답 / 필수 | X | `user@example.com` |
| `phone` | phone 값 | string | 응답 / 필수 | X | `01012345678` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |

**Example**
```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": "01012345678",
  "name": "아이 이름"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 17. 프로필 편집
**`PATCH /api/v1/users/me`**

기능: 프로필 편집.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `name` | name 값 | string | Body / 선택 | O | `아이 이름` |
| `nickname` | nickname 값 | string | Body / 선택 | O | `부모님` |

**Request Example**
```json
{
  "name": "아이 이름",
  "nickname": "부모님"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `email` | email 값 | string | 응답 / 필수 | X | `user@example.com` |
| `phone` | phone 값 | string | 응답 / 필수 | X | `01012345678` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |

**Example**
```json
{
  "id": 1,
  "email": "user@example.com",
  "phone": "01012345678",
  "name": "아이 이름"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 18. 프로필 사진 등록·변경(업로드 방식 제안)
**`POST /api/v1/users/me/profile-photo`**

기능: 프로필 사진 등록·변경(업로드 방식 제안).

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `photo_file` | photo file 값 | file | Body / 필수 | X | `<binary>` |

**Request Example**
```json
{
  "photo_file": "<binary>"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `profile_photo_url` | profile photo url 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "profile_photo_url": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 19. 프로필 사진 삭제
**`DELETE /api/v1/users/me/profile-photo`**

기능: 프로필 사진 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 20. 아이 목록
**`GET /api/v1/children`**

기능: 아이 목록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |
| `birth_date` | birth date 값 | date | 응답 / 필수 | X | `2022-05-01` |
| `gender` | gender 값 | string | 응답 / 필수 | X | `female` |
| `interests` | interests 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "id": 1,
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 21. 아이 등록
**`POST /api/v1/children`**

**v1.5 확정:** `interests`는 공통 카테고리 식별자의 배열이며 여러 개 선택할 수 있습니다. 식별자는 `GET /activity-categories`에서 제공하는 값과 동일해야 합니다. 아래 빈 배열 예시는 미선택 예시이며 카테고리 코드·ID 타입은 추후 확정합니다.

기능: 아이 등록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `name` | name 값 | string | Body / 필수 | X | `아이 이름` |
| `birth_date` | birth date 값 | date | Body / 필수 | X | `2022-05-01` |
| `gender` | gender 값 | string | Body / 선택 | O | `female` |
| `interests` | interests 값 | array | Body / 선택 | O | `[]` |

**Request Example**
```json
{
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |
| `birth_date` | birth date 값 | date | 응답 / 필수 | X | `2022-05-01` |
| `gender` | gender 값 | string | 응답 / 필수 | X | `female` |
| `interests` | interests 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "id": 1,
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 22. 아이 상세
**`GET /api/v1/children/{child_id}`**

기능: 아이 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |
| `birth_date` | birth date 값 | date | 응답 / 필수 | X | `2022-05-01` |
| `gender` | gender 값 | string | 응답 / 필수 | X | `female` |
| `interests` | interests 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "id": 1,
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 23. 아이 정보 수정
**`PATCH /api/v1/children/{child_id}`**

**v1.5 확정:** 아이 관심사 수정 시에도 등록과 동일한 공통 카테고리 목록을 사용하며, 중복 및 존재하지 않는 카테고리 식별자를 거부합니다.

기능: 아이 정보 수정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `name` | name 값 | string | Body / 선택 | O | `아이 이름` |
| `birth_date` | birth date 값 | date | Body / 선택 | O | `2022-05-01` |
| `gender` | gender 값 | string | Body / 선택 | O | `female` |
| `interests` | interests 값 | array | Body / 선택 | O | `[]` |

**Request Example**
```json
{
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `name` | name 값 | string | 응답 / 필수 | X | `아이 이름` |
| `birth_date` | birth date 값 | date | 응답 / 필수 | X | `2022-05-01` |
| `gender` | gender 값 | string | 응답 / 필수 | X | `female` |
| `interests` | interests 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "id": 1,
  "name": "아이 이름",
  "birth_date": "2022-05-01",
  "gender": "female",
  "interests": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 24. 아이 삭제
**`DELETE /api/v1/children/{child_id}`**

**v1.5 확정:** 본인 소유 아이 삭제 시 그 아이에 연결된 활동 기록을 함께 삭제합니다. 관련 사진 파일 정리도 필요하며 주문·결제 기록 삭제를 뜻하지 않습니다.

기능: 아이 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 25. 현재 선택 아이 변경
**`PUT /api/v1/users/me/active-child`**

기능: 현재 선택 아이 변경.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | Body / 필수 | X | `1` |

**Request Example**
```json
{
  "child_id": 1
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `active_child_id` | active child id 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "active_child_id": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 26. 홈 콘텐츠
**`GET /api/v1/home`**

기능: 홈 콘텐츠.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `popular_activities` | popular activities 값 | array | 응답 / 필수 | X | `[]` |
| `trending_keywords` | trending keywords 값 | array | 응답 / 필수 | X | `[]` |
| `guides` | guides 값 | array | 응답 / 필수 | X | `[]` |
| `continue_activity` | continue activity 값 | object | 응답 / 필수 | O | `{}` |

**Example**
```json
{
  "popular_activities": [],
  "trending_keywords": [],
  "guides": [],
  "continue_activity": {}
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 27. 활동지 목록·검색·필터·정렬
**`GET /api/v1/activities`**

기능: 활동지 목록·검색·필터·정렬.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `q` | q 값 | string | Query / 선택 | O | `자동차` |
| `category` | category 값 | string | Query / 선택 | O | `painting` |
| `age_years` | age years 값 | integer | Query / 선택 | O | `1` |
| `duration` | duration 값 | string | Query / 선택 | O | `5-10` |
| `difficulty` | difficulty 값 | string | Query / 선택 | O | `easy` |
| `price_min` | price min 값 | integer | Query / 선택 | O | `1` |
| `price_max` | price max 값 | integer | Query / 선택 | O | `1` |
| `sort` | sort 값 | string | Query / 선택 | O | `popular` |
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `count` | count 값 | integer | 응답 / 필수 | X | `1` |
| `next` | next 값 | string | 응답 / 필수 | O | `(미확정 예시)` |
| `previous` | previous 값 | string | 응답 / 필수 | O | `(미확정 예시)` |
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "count": 1,
  "next": "UNSPECIFIED",
  "previous": "UNSPECIFIED",
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 28. 활동지 상세
**`GET /api/v1/activities/{activity_id}`**

기능: 활동지 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `title` | title 값 | string | 응답 / 필수 | X | `활동지 제목` |
| `price` | price 값 | integer | 응답 / 필수 | X | `1900` |
| `sale_status` | sale status 값 | string | 응답 / 필수 | X | `on_sale` |
| `description` | description 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "title": "활동지 제목",
  "price": 1900,
  "sale_status": "on_sale",
  "description": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 29. 인기 활동지
**`GET /api/v1/activities/popular`**

기능: 인기 활동지.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `limit` | limit 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 30. 인기 검색어
**`GET /api/v1/search/trending`**

기능: 인기 검색어.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `updated_at` | updated at 값 | datetime | 응답 / 필수 | X | `2026-11-06T12:00:00Z` |
| `keywords` | keywords 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "updated_at": "2026-11-06T12:00:00Z",
  "keywords": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 31. 검색 입력 중 자동완성 제안
**`GET /api/v1/search/suggestions`**

기능: 검색 입력 중 자동완성 제안.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `q` | q 값 | string | Query / 필수 | X | `자동차` |
| `limit` | limit 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `query` | query 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `suggestions` | suggestions 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "query": "UNSPECIFIED",
  "suggestions": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 32. 최근 검색어
**`GET /api/v1/search/recent`**

기능: 최근 검색어.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `limit` | limit 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 33. 검색어 기록
**`POST /api/v1/search/recent`**

기능: 검색어 기록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `keyword` | keyword 값 | string | Body / 필수 | X | `자동차` |

**Request Example**
```json
{
  "keyword": "자동차"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `keyword` | keyword 값 | string | 응답 / 필수 | X | `자동차` |

**Example**
```json
{
  "id": 1,
  "keyword": "자동차"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 34. 최근 검색어 전체 삭제
**`DELETE /api/v1/search/recent`**

기능: 최근 검색어 전체 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 35. 최근 검색어 개별 삭제
**`DELETE /api/v1/search/recent/{search_id}`**

기능: 최근 검색어 개별 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `search_id` | search id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 36. 맞춤 놀이 조건 검색
**`POST /api/v1/recommendations/one-click`**

기능: 맞춤 놀이 조건 검색.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | Body / 필수 | X | `1` |
| `categories` | categories 값 | array | Body / 필수 | X | `[]` |
| `duration` | duration 값 | string | Body / 선택 | O | `5-10` |
| `place` | place 값 | string | Body / 선택 | O | `indoor` |
| `materials` | materials 값 | array | Body / 선택 | O | `[]` |

**Request Example**
```json
{
  "child_id": 1,
  "categories": [],
  "duration": "5-10",
  "place": "indoor",
  "materials": []
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | 응답 / 필수 | X | `1` |
| `total` | total 값 | integer | 응답 / 필수 | X | `1` |
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "child_id": 1,
  "total": 1,
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 37. 놀이 카테고리 및 안내
**`GET /api/v1/activity-categories`**

기능: 놀이 카테고리 및 안내.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 38. 구매 전 미리보기
**`GET /api/v1/activities/{activity_id}/preview`**

기능: 구매 전 미리보기.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `preview_urls` | preview urls 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "preview_urls": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 39. 구매한 활동지
**`GET /api/v1/purchases/activities`**

기능: 구매한 활동지.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `count` | count 값 | integer | 응답 / 필수 | X | `1` |
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "count": 1,
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 40. 구매 파일 다운로드 권한 발급
**`POST /api/v1/activities/{activity_id}/download`**

기능: 구매 파일 다운로드 권한 발급.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `download_url` | download url 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `expires_at` | expires at 값 | datetime | 응답 / 필수 | X | `2026-11-06T12:00:00Z` |
| `file_name` | file name 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "download_url": "UNSPECIFIED",
  "expires_at": "2026-11-06T12:00:00Z",
  "file_name": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 41. 찜 목록
**`GET /api/v1/favorites`**

기능: 찜 목록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 42. 찜 추가
**`POST /api/v1/favorites`**

기능: 찜 추가.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Body / 필수 | X | `101` |

**Request Example**
```json
{
  "activity_id": 101
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | 응답 / 필수 | X | `101` |
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "activity_id": 101,
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 43. 찜 해제
**`DELETE /api/v1/favorites/{activity_id}`**

기능: 찜 해제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 44. 장바구니
**`GET /api/v1/cart`**

기능: 장바구니.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `items` | items 값 | array | 응답 / 필수 | X | `[]` |
| `total_amount` | total amount 값 | integer | 응답 / 필수 | X | `2890` |

**Example**
```json
{
  "items": [],
  "total_amount": 2890
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 45. 장바구니 담기
**`POST /api/v1/cart/items`**

**v1.5 확정:** 이미 구매 권한이 있는 활동지는 장바구니에 추가할 수 없습니다. `409 ALREADY_PURCHASED` 응답을 제안합니다. 아래 Status 표는 이 규칙을 추가하여 해석합니다.

기능: 장바구니 담기.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Body / 필수 | X | `101` |

**Request Example**
```json
{
  "activity_id": 101
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | 응답 / 필수 | X | `101` |
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "activity_id": 101,
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 46. 장바구니에서 삭제
**`DELETE /api/v1/cart/items/{activity_id}`**

기능: 장바구니에서 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 47. 결제 예상 금액 산정
**`POST /api/v1/orders/quote`**

기능: 결제 예상 금액 산정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_ids` | activity ids 값 | array | Body / 필수 | X | `[]` |

**Request Example**
```json
{
  "activity_ids": []
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `subtotal` | subtotal 값 | integer | 응답 / 필수 | X | `2890` |
| `payable_amount` | payable amount 값 | integer | 응답 / 필수 | X | `2890` |
| `unavailable_activity_ids` | unavailable activity ids 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "subtotal": 2890,
  "payable_amount": 2890,
  "unavailable_activity_ids": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 48. 주문 생성
**`POST /api/v1/orders`**

기능: 주문 생성.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `activity_ids` | activity ids 값 | array | Body / 필수 | X | `[]` |
| `payment_method_id` | payment method id 값 | string | Body / 선택 | O | `pm_test_001` |
| `agreed_to_payment` | agreed to payment 값 | boolean | Body / 필수 | X | `true` |

**Request Example**
```json
{
  "activity_ids": [],
  "payment_method_id": "pm_test_001",
  "agreed_to_payment": true
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `order_id` | order id 값 | integer | 응답 / 필수 | X | `501` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `amount` | amount 값 | integer | 응답 / 필수 | X | `1900` |
| `payment_session_token` | payment session token 값 | string | 응답 / 필수 | O | `(미확정 예시)` |

**Example**
```json
{
  "order_id": 501,
  "status": "ACTIVE",
  "amount": 1900,
  "payment_session_token": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 49. PG 결제 검증 및 확정
**`POST /api/v1/payments/confirm`**

기능: PG 결제 검증 및 확정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `order_id` | order id 값 | integer | Body / 필수 | X | `501` |
| `pg_payment_key` | pg payment key 값 | string | Body / 필수 | X | `pg_test_key` |
| `pg_order_id` | pg order id 값 | string | Body / 필수 | X | `pg_order_501` |

**Request Example**
```json
{
  "order_id": 501,
  "pg_payment_key": "pg_test_key",
  "pg_order_id": "pg_order_501"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `order_id` | order id 값 | integer | 응답 / 필수 | X | `501` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `paid_amount` | paid amount 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "order_id": 501,
  "status": "ACTIVE",
  "paid_amount": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 50. PG 웹훅 수신
**`POST /api/v1/payments/webhook`**

기능: PG 웹훅 수신.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |
> PG 웹훅 서명 헤더는 결제사 문서에 맞춰 별도 정의해야 합니다.

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `provider_event_id` | provider event id 값 | string | Body / 필수 | X | `evt_123` |
| `event_type` | event type 값 | string | Body / 필수 | X | `payment.completed` |
| `data` | data 값 | object | Body / 필수 | X | `{}` |

**Request Example**
```json
{
  "provider_event_id": "evt_123",
  "event_type": "payment.completed",
  "data": {}
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `received` | received 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "received": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 51. 결제 내역
**`GET /api/v1/orders`**

기능: 결제 내역.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `order_id` | order id 값 | integer | 응답 / 필수 | X | `501` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `amount` | amount 값 | integer | 응답 / 필수 | X | `1900` |
| `payment_session_token` | payment session token 값 | string | 응답 / 필수 | O | `(미확정 예시)` |

**Example**
```json
{
  "order_id": 501,
  "status": "ACTIVE",
  "amount": 1900,
  "payment_session_token": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 52. 결제 상세
**`GET /api/v1/orders/{order_id}`**

기능: 결제 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `order_id` | order id 값 | integer | Path / 필수 | X | `501` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `items` | items 값 | array | 응답 / 필수 | X | `[]` |
| `total_amount` | total amount 값 | integer | 응답 / 필수 | X | `2890` |

**Example**
```json
{
  "id": 1,
  "status": "ACTIVE",
  "items": [],
  "total_amount": 2890
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 53. 영수증
**`GET /api/v1/orders/{order_id}/receipt`**

기능: 영수증.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `order_id` | order id 값 | integer | Path / 필수 | X | `501` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `receipt_url` | receipt url 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `order_id` | order id 값 | integer | 응답 / 필수 | X | `501` |

**Example**
```json
{
  "receipt_url": "UNSPECIFIED",
  "order_id": 501
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 54. 결제 취소 요청
**`POST /api/v1/orders/{order_id}/cancel`**

기능: 결제 취소 요청.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `order_id` | order id 값 | integer | Path / 필수 | X | `501` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `reason` | reason 값 | string | Body / 필수 | X | `changed_mind` |

**Request Example**
```json
{
  "reason": "changed_mind"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `order_id` | order id 값 | integer | 응답 / 필수 | X | `501` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `refund_amount` | refund amount 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "order_id": 501,
  "status": "ACTIVE",
  "refund_amount": 1
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 55. 등록 결제 수단
**`GET /api/v1/payment-methods`**

기능: 등록 결제 수단.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 56. 결제수단 토큰 등록
**`POST /api/v1/payment-methods`**

기능: 결제수단 토큰 등록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `billing_token` | billing token 값 | string | Body / 필수 | X | `bill_test_001` |
| `is_default` | is default 값 | boolean | Body / 선택 | O | `true` |

**Request Example**
```json
{
  "billing_token": "bill_test_001",
  "is_default": true
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `last4` | last4 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `brand` | brand 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `is_default` | is default 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "id": "UNSPECIFIED",
  "last4": "UNSPECIFIED",
  "brand": "UNSPECIFIED",
  "is_default": true
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 57. 기본 카드 설정
**`PATCH /api/v1/payment-methods/{method_id}`**

기능: 기본 카드 설정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `method_id` | method id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `is_default` | is default 값 | boolean | Body / 필수 | X | `true` |

**Request Example**
```json
{
  "is_default": true
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `is_default` | is default 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "id": "UNSPECIFIED",
  "is_default": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 58. 결제수단 삭제
**`DELETE /api/v1/payment-methods/{method_id}`**

기능: 결제수단 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `method_id` | method id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 59. 보유 쿠폰 — **우선 제외**
**`GET /api/v1/coupons`**

기능: 보유 쿠폰.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 60. 쿠폰 코드 등록 — **우선 제외**
**`POST /api/v1/coupons/redeem`**

기능: 쿠폰 코드 등록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `code` | code 값 | string | Body / 필수 | X | `123456` |

**Request Example**
```json
{
  "code": "123456"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `coupon_id` | coupon id 값 | integer | 응답 / 필수 | X | `1` |
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "coupon_id": 1,
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 61. 쿠폰 상세 — **우선 제외**
**`GET /api/v1/coupons/{coupon_id}`**

기능: 쿠폰 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `coupon_id` | coupon id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `code` | code 값 | string | 응답 / 필수 | X | `123456` |
| `expires_at` | expires at 값 | datetime | 응답 / 필수 | X | `2026-11-06T12:00:00Z` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |

**Example**
```json
{
  "id": 1,
  "code": "123456",
  "expires_at": "2026-11-06T12:00:00Z",
  "status": "ACTIVE"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 62. 캐시 잔액 — **우선 제외**
**`GET /api/v1/wallet/cash`**

기능: 캐시 잔액.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `balance` | balance 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "balance": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 63. 캐시 이용 내역 — **우선 제외**
**`GET /api/v1/wallet/cash/transactions`**

기능: 캐시 이용 내역.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 64. 캐시 충전 주문 — **우선 제외**
**`POST /api/v1/wallet/cash/topups`**

기능: 캐시 충전 주문.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `amount` | amount 값 | integer | Body / 필수 | X | `1900` |

**Request Example**
```json
{
  "amount": 1900
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `topup_id` | topup id 값 | integer | 응답 / 필수 | X | `1` |
| `payment_session_token` | payment session token 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "topup_id": 1,
  "payment_session_token": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 65. 포인트 잔액 — **우선 제외**
**`GET /api/v1/wallet/points`**

기능: 포인트 잔액.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `balance` | balance 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "balance": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 66. 포인트 적립·사용 내역 — **우선 제외**
**`GET /api/v1/wallet/points/transactions`**

기능: 포인트 적립·사용 내역.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 67. 활동지 리뷰
**`GET /api/v1/activities/{activity_id}/reviews`**

기능: 활동지 리뷰.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |
| `sort` | sort 값 | string | Query / 선택 | O | `popular` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 68. 구매 후 리뷰 등록
**`POST /api/v1/activities/{activity_id}/reviews`**

기능: 구매 후 리뷰 등록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `activity_id` | activity id 값 | integer | Path / 필수 | X | `101` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `rating` | rating 값 | integer | Body / 필수 | X | `5` |
| `content` | content 값 | string | Body / 필수 | X | `(미확정 예시)` |
| `child_id` | child id 값 | integer | Body / 선택 | O | `1` |

**Request Example**
```json
{
  "rating": 5,
  "content": "UNSPECIFIED",
  "child_id": 1
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `rating` | rating 값 | integer | 응답 / 필수 | X | `5` |
| `content` | content 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "rating": 5,
  "content": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 69. 리뷰 삭제
**`DELETE /api/v1/reviews/{review_id}`**

기능: 리뷰 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `review_id` | review id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 70. 도움돼요
**`POST /api/v1/reviews/{review_id}/helpful`**

기능: 도움돼요.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `review_id` | review id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `helpful_count` | helpful count 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "helpful_count": 1
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 71. 리뷰 신고
**`POST /api/v1/reviews/{review_id}/reports`**

기능: 리뷰 신고.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `review_id` | review id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `reason` | reason 값 | string | Body / 필수 | X | `changed_mind` |

**Request Example**
```json
{
  "reason": "changed_mind"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `report_id` | report id 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "report_id": 1
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 72. 아이 활동 기록
**`GET /api/v1/activity-records`**

기능: 아이 활동 기록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | Query / 선택 | O | `1` |
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `page_size` | page size 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 73. 활동 인증·기록
**`POST /api/v1/activity-records`**

기능: 활동 인증·기록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | Body / 필수 | X | `1` |
| `activity_id` | activity id 값 | integer | Body / 필수 | X | `101` |
| `reaction` | reaction 값 | string | Body / 선택 | O | `happy` |
| `memo` | memo 값 | string | Body / 선택 | O | `(미확정 예시)` |
| `photo_file` | photo file 값 | file | Body / 선택 | O | `<binary>` |

**Request Example**
```json
{
  "child_id": 1,
  "activity_id": 101,
  "reaction": "happy",
  "memo": "UNSPECIFIED",
  "photo_file": "<binary>"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `child_id` | child id 값 | integer | 응답 / 필수 | X | `1` |
| `activity_id` | activity id 값 | integer | 응답 / 필수 | X | `101` |

**Example**
```json
{
  "id": 1,
  "child_id": 1,
  "activity_id": 101
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 74. 활동 기록 수정 — **우선 제외**
**`PATCH /api/v1/activity-records/{record_id}`**

기능: 활동 기록 수정 — **우선 제외**.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `record_id` | record id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `reaction` | reaction 값 | string | Body / 선택 | O | `happy` |
| `memo` | memo 값 | string | Body / 선택 | O | `(미확정 예시)` |
| `photo_file` | photo file 값 | file | Body / 선택 | O | `<binary>` |

**Request Example**
```json
{
  "reaction": "happy",
  "memo": "UNSPECIFIED",
  "photo_file": "<binary>"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `message` | message 값 | string | 응답 / 필수 | X | `처리되었습니다.` |

**Example**
```json
{
  "message": "처리되었습니다."
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 75. 활동 기록 삭제 — **우선 제외**
**`DELETE /api/v1/activity-records/{record_id}`**

기능: 활동 기록 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `record_id` | record id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 76. 만세도감
**`GET /api/v1/children/{child_id}/badges`**

기능: 만세도감.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `featured_badge_id` | featured badge id 값 | integer | 응답 / 필수 | O | `1` |
| `badges` | badges 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "featured_badge_id": 1,
  "badges": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 77. 대표배지 설정
**`PATCH /api/v1/children/{child_id}/featured-badge`**

기능: 대표배지 설정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `badge_id` | badge id 값 | integer | Body / 필수 | X | `1` |

**Request Example**
```json
{
  "badge_id": 1
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `featured_badge_id` | featured badge id 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "featured_badge_id": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 78. 성장 리포트 — **우선 제외**
**`GET /api/v1/children/{child_id}/growth-report`**

기능: 성장 리포트 — **우선 제외**.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `child_id` | child id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `period` | period 값 | string | Query / 선택 | O | `month` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `child_id` | child id 값 | integer | 응답 / 필수 | X | `1` |
| `period` | period 값 | string | 응답 / 필수 | X | `month` |
| `is_available` | is available 값 | boolean | 응답 / 필수 | X | `true` |
| `domains` | domains 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "child_id": 1,
  "period": "month",
  "is_available": true,
  "domains": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

> 이 API는 향후 구현용이며 1차 개발 대상에서 제외합니다.

---

## 79. 부모님 가이드북 목록
**`GET /api/v1/guides`**

기능: 부모님 가이드북 목록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `category` | category 값 | string | Query / 선택 | O | `painting` |
| `page` | page 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 80. 가이드북 상세
**`GET /api/v1/guides/{guide_id}`**

기능: 가이드북 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `guide_id` | guide id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `title` | title 값 | string | 응답 / 필수 | X | `활동지 제목` |
| `body` | body 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "title": "활동지 제목",
  "body": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 81. 이벤트 목록
**`GET /api/v1/events`**

기능: 이벤트 목록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `status` | status 값 | string | Query / 선택 | O | `ACTIVE` |
| `page` | page 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 82. 이벤트 상세
**`GET /api/v1/events/{event_id}`**

기능: 이벤트 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `event_id` | event id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `title` | title 값 | string | 응답 / 필수 | X | `활동지 제목` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `content` | content 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "title": "활동지 제목",
  "status": "ACTIVE",
  "content": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 83. 이벤트 참여
**`POST /api/v1/events/{event_id}/participations`**

기능: 이벤트 참여.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `event_id` | event id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `participation_id` | participation id 값 | integer | 응답 / 필수 | X | `1` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |

**Example**
```json
{
  "participation_id": 1,
  "status": "ACTIVE"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 84. 알림 목록
**`GET /api/v1/notifications`**

기능: 알림 목록.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `type` | type 값 | string | Query / 선택 | O | `terms` |
| `page` | page 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |
| `unread_count` | unread count 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "results": [],
  "unread_count": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 85. 전체 읽음
**`PATCH /api/v1/notifications/read-all`**

기능: 전체 읽음.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `updated_count` | updated count 값 | integer | 응답 / 필수 | X | `1` |

**Example**
```json
{
  "updated_count": 1
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 86. 개별 알림 읽음(제안)
**`PATCH /api/v1/notifications/{notification_id}/read`**

기능: 개별 알림 읽음(제안).

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `notification_id` | notification id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `read` | read 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "read": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 87. 전체 알림 삭제
**`DELETE /api/v1/notifications`**

기능: 전체 알림 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 88. 알림 설정
**`GET /api/v1/users/me/notification-settings`**

기능: 알림 설정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `marketing_enabled` | marketing enabled 값 | boolean | 응답 / 필수 | X | `true` |
| `push_enabled` | push enabled 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "marketing_enabled": true,
  "push_enabled": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 89. 알림 설정 변경
**`PATCH /api/v1/users/me/notification-settings`**

기능: 알림 설정 변경.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `marketing_enabled` | marketing enabled 값 | boolean | Body / 선택 | O | `true` |
| `push_enabled` | push enabled 값 | boolean | Body / 선택 | O | `true` |

**Request Example**
```json
{
  "marketing_enabled": true,
  "push_enabled": true
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `marketing_enabled` | marketing enabled 값 | boolean | 응답 / 필수 | X | `true` |
| `push_enabled` | push enabled 값 | boolean | 응답 / 필수 | X | `true` |

**Example**
```json
{
  "marketing_enabled": true,
  "push_enabled": true
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 90. FAQ 검색
**`GET /api/v1/faqs`**

기능: FAQ 검색.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `q` | q 값 | string | Query / 선택 | O | `자동차` |
| `category` | category 값 | string | Query / 선택 | O | `painting` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 91. 공지사항
**`GET /api/v1/notices`**

기능: 공지사항.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---

## 92. 공지 상세
**`GET /api/v1/notices/{notice_id}`**

기능: 공지 상세.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `notice_id` | notice id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `title` | title 값 | string | 응답 / 필수 | X | `활동지 제목` |
| `body` | body 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `published_at` | published at 값 | datetime | 응답 / 필수 | X | `2026-11-06T12:00:00Z` |

**Example**
```json
{
  "id": 1,
  "title": "활동지 제목",
  "body": "UNSPECIFIED",
  "published_at": "2026-11-06T12:00:00Z"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 93. 1:1 문의 내역
**`GET /api/v1/inquiries`**

기능: 1:1 문의 내역.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `page` | page 값 | integer | Query / 선택 | O | `1` |
| `status` | status 값 | string | Query / 선택 | O | `ACTIVE` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `results` | results 값 | array | 응답 / 필수 | X | `[]` |

**Example**
```json
{
  "results": []
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 500 | 서버 내부 오류 |

---

## 94. 1:1 문의 접수
**`POST /api/v1/inquiries`**

기능: 1:1 문의 접수.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `category` | category 값 | string | Body / 필수 | X | `painting` |
| `title` | title 값 | string | Body / 필수 | X | `활동지 제목` |
| `body` | body 값 | string | Body / 필수 | X | `(미확정 예시)` |
| `attachments` | attachments 값 | array | Body / 선택 | O | `[]` |

**Request Example**
```json
{
  "category": "painting",
  "title": "활동지 제목",
  "body": "UNSPECIFIED",
  "attachments": []
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |

**Example**
```json
{
  "id": 1,
  "status": "ACTIVE"
}
```

### Status

| status | response content |
|---|---|
| 201 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 95. 문의 상세·답변
**`GET /api/v1/inquiries/{inquiry_id}`**

기능: 문의 상세·답변.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `inquiry_id` | inquiry id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `answer` | answer 값 | string | 응답 / 필수 | O | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "status": "ACTIVE",
  "answer": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 96. 미답변 문의 수정
**`PATCH /api/v1/inquiries/{inquiry_id}`**

기능: 미답변 문의 수정.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `inquiry_id` | inquiry id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `title` | title 값 | string | Body / 선택 | O | `활동지 제목` |
| `body` | body 값 | string | Body / 선택 | O | `(미확정 예시)` |

**Request Example**
```json
{
  "title": "활동지 제목",
  "body": "UNSPECIFIED"
}
```

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `id` | id 값 | integer | 응답 / 필수 | X | `1` |
| `status` | status 값 | string | 응답 / 필수 | X | `ACTIVE` |
| `answer` | answer 값 | string | 응답 / 필수 | O | `(미확정 예시)` |

**Example**
```json
{
  "id": 1,
  "status": "ACTIVE",
  "answer": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 97. 문의 삭제
**`DELETE /api/v1/inquiries/{inquiry_id}`**

기능: 문의 삭제.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `Authorization` | Authorization 값 | string | Header / 필수 | X | `(미확정 예시)` |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `inquiry_id` | inquiry id 값 | integer | Path / 필수 | X | `1` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Example:** 응답 본문 없음 (`204 No Content`).

### Status

| status | response content |
|---|---|
| 204 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 401 | 인증 토큰 누락 또는 만료 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 409 | 중복 요청 또는 처리 불가능한 상태 |
| 500 | 서버 내부 오류 |

---

## 98. 약관·개인정보·환불정책
**`GET /api/v1/policies/{policy_type}`**

기능: 약관·개인정보·환불정책.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Path parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| `policy_type` | policy type 값 | string | Path / 필수 | X | `terms` |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `type` | type 값 | string | 응답 / 필수 | X | `terms` |
| `version` | version 값 | string | 응답 / 필수 | X | `(미확정 예시)` |
| `body` | body 값 | string | 응답 / 필수 | X | `(미확정 예시)` |

**Example**
```json
{
  "type": "terms",
  "version": "UNSPECIFIED",
  "body": "UNSPECIFIED"
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 404 | 대상 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |

---

## 99. 앱 버전·점검 상태·강제/선택 업데이트 판단 정보
**`GET /api/v1/app/config`**

기능: 앱 버전·점검 상태·강제/선택 업데이트 판단 정보.

### Request

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

**Query parameter**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `platform` | platform 값 | string | Query / 필수 | X | `android` |
| `app_version` | app version 값 | string | Query / 필수 | X | `1.0.0` |

**Body**

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| 없음 | 별도 입력 없음 | - | - | - | - |

### Response

| key | 설명 | value 타입 | 옵션 | Nullable | 예시 |
|---|---|---|---|---|
| `maintenance` | maintenance 값 | object | 응답 / 필수 | X | `{}` |
| `update` | update 값 | object | 응답 / 필수 | X | `{}` |

**Example**
```json
{
  "maintenance": {},
  "update": {}
}
```

### Status

| status | response content |
|---|---|
| 200 | 정상 처리 |
| 400 | 요청 형식 또는 필수값 오류 |
| 500 | 서버 내부 오류 |

---



## 4. 데이터베이스 주요 테이블 (MySQL 제안)

| 테이블 | 주요 필드 | 관계 |
|---|---|---|
| `users` | id, email, phone, password_hash, name, salutation, status | 사용자 |
| `social_accounts` | id, user_id, provider, provider_user_id | users N:1 |
| `children` | id, user_id, name, birth_date, gender | users N:1 |
| `categories` | id, code, name, display_order, is_active | 아이 관심사·활동지 분류 공통 기준 |
| `child_interests` | child_id, category_id | children N:M categories; `(child_id, category_id)` unique |
| `activity_categories` | activity_id, category_id | activities N:M categories; `(activity_id, category_id)` unique |
| `activities` | id, title, description, price, duration_min, duration_max, difficulty, sale_status, image_key | 관리자 등록 활동지; 분류는 `activity_categories` 사용 |
| `activity_files` | id, activity_id, file_type, storage_key, preview_flag | activities N:1 |
| `activity_materials` | activity_id, material_id | N:M |
| `favorites` | user_id, activity_id | 유니크 쌍 |
| `recent_searches` | id, user_id, keyword, searched_at | users N:1 |
| `carts` / `cart_items` | id, user_id / cart_id, activity_id | 장바구니 |
| `orders` / `order_items` | id, user_id, status, totals / order_id, activity_id, unit_price | 주문 |
| `payments` / `refunds` | id, order_id, pg_ref, status / payment_id, amount, reason | 결제 (후속) |
| `purchase_entitlements` | id, user_id, activity_id, status, granted_at, revoked_at | 구매 권한; 장바구니 중복 구매 차단 근거 (제안) |
| `payment_methods` | id, user_id, pg_token, brand, last4, is_default | 카드 원문 저장 금지 |
| `coupons` / `user_coupons` | id, code, discount, expires_at / user_id, coupon_id, status | 쿠폰 (우선 제외) |
| `wallet_transactions` | id, user_id, currency_type, amount, reason, reference_id | 캐시·포인트 원장 (우선 제외) |
| `reviews` / `review_reports` | id, user_id, child_id, activity_id, rating, content / review_id, reason | 리뷰 |
| `activity_records` | id, user_id, child_id, activity_id, reaction, memo, photo_key | 아이 삭제 시 해당 아이 기록 삭제 |
| `badges` / `child_badges` | id, name, type / child_id, badge_id, earned_at | 배지 |
| `guides` / `events` | id, title, body, status, published_at | 콘텐츠 |
| `notifications` / `inquiries` | id, user_id, type, read_at / id, user_id, category, title, body, status | 알림·문의 |

**주의:** 위의 `categories.id`/`category_id` 방식은 공통 카테고리 연결을 위한 **v1.5 설계 제안**입니다. 기존 API의 `interest_code`와 타입을 아직 일괄 수정하지 않았으므로 프론트·백엔드가 실제 식별자 규격을 합의한 후 확정해야 합니다.

### 기존 데이터 모델 초안의 추가 검토 대상

| 모델 | 핵심 관계·제약 |
|---|---|
| User | 이메일·전화번호 유니크 정책, 계정 상태, 인증 수단 |
| Child | `user_id` FK, 생년월일; 여러 아이 허용, 삭제 시 해당 아이 활동 기록 삭제 **확정** |
| Activity / ActivityFile | 활동지, 가격, 판매 상태, 미리보기/구매 파일 |
| Category / ActivityCategory | 아이 관심사·활동지 공통 카테고리 **확정**; 활동지와 카테고리 다대다 |
| Favorite | (`user_id`, `activity_id`) unique |
| CartItem | (`user_id`, `activity_id`) unique; 이미 구매한 활동지는 담기 금지 **확정** |
| Order / OrderItem | 주문 금액 스냅샷, 결제 상태, 주문 항목 |
| Payment / PaymentEvent | PG 거래 ID unique, 웹훅 event ID unique, 멱등 처리 |
| PurchaseEntitlement | 사용자별 활동지 열람·다운로드 권한; 취소 시 정책 반영 |
| Review | 사용자·활동지·구매/기록 연결, 작성 정책별 unique |
| ActivityRecord | 아이·활동지·사진·작성자, 권한 검사; 아이 삭제 시 관련 기록 삭제 **확정** |
| Badge / ChildBadge | 배지 정의·획득 이력; 중복 발급 방지 |
| Guide / Event | 게시 콘텐츠·진행 상태 |
| Notification | 사용자·읽음·삭제 상태 |
| Inquiry | 작성자·상태·관리자 답변 |
| PolicyVersion / UserConsent | 약관 버전·동의 시점 증빙 |

## 5. 남은 결정 필요 사항 — API별

| 관련 API | 결정할 규칙 | 임시 개발 방식 |
|---|---|---|
| 01~08 가입/로그인 | **확정:** 이메일 가입 우선·이메일 인증번호 필수. **미정:** 소셜 연동 시 계정 연결·전화번호 가입 | 이메일 인증·가입 먼저 구현, 소셜·전화번호 가입은 후속 |
| 02·05 인증번호 | 발송 채널, 만료·재발송·시도 횟수, 재사용 금지 | 6자리/180초 테스트 설정; 운영 설정과 분리 |
| 03~04 실명 인증 | 인증사, callback/redirect, 결과 검증, 개인정보 보관 범위 | FakeIdentityProvider 사용; 주민등록번호 저장 금지 |
| 09~10 토큰 | refresh rotation, 로그아웃/다른 기기 로그인 처리 | 토큰 폐기 테이블 및 단위 테스트 우선 |
| 20~25 아이 | **확정:** 다중 아이·다중 관심사, 공통 카테고리, 아이 삭제 시 해당 아이 활동 기록 삭제. **미정:** 연령 범위·사진 정리 | 소유권 검사·관계 제약·기록 삭제 구현 |
| 27~36 검색/추천 | **확정:** 아이 관심사와 활동지 카테고리 공통. **미정:** 실제 카테고리 목록/식별자, 인기순, 추천 규칙 | 기본 키워드·카테고리 검색부터 구현; AI 추천이라고 가정 금지 |
| 38~40 PDF | 미리보기 범위, 구매 권한, 파일 저장소, 다운로드 URL 만료 | 테스트 파일과 임시 서명 URL 사용 |
| 44~50 장바구니/결제 | **확정:** 구매한 활동지 장바구니 담기 금지. **미정:** 판매 종료·가격 변경·PG·웹훅·멱등성 | 장바구니 구매 권한 검사 먼저 구현; 실제 PG는 후속 |
| 51~54 결제 취소 | 부분취소 가능 여부, 환불 기한, 다운로드 이후 취소, PG 취소 동기화 | 취소 불가/가능 상태만 모의 구현; 실환불 보류 |
| 55~58 카드 | PG 빌링키 사용 방식, 기본 카드 정책 | 카드번호/CVC 서버 저장 금지; PG 토큰만 저장 |
| 67~78 리뷰·기록·배지 | 기록 삭제 범위, 배지 발급 기준, 중복 지급, 대표배지 조건 | 트랜잭션+중복 방지 제약 필요 |
| 81~83 이벤트 | 참여 횟수·자격·종료시각 | 정책 확정 전 참여 기능 mock |
| 84~89 알림 | 알림 채널, 읽음·삭제 정책, 푸시 토큰 관리 | 인앱 알림부터 구현 |
| 93~97 문의 | 수정·삭제 가능 상태, 첨부 제한, 관리자 답변 방식 | 사용자/관리자 권한 분리 |
| 99 앱 설정 | 앱/웹 여부, 버전 비교, 강제 업데이트 URL | 정적 설정값으로 시작 |

## 6. 팀 공유 및 구현 시 유의사항

1. 이 문서는 **99개 API의 전체 설계 목록과 1차 개발 범위를 함께 담은 팀 공유용 기준 문서**입니다. 모든 API가 1차 구현 대상은 아닙니다.
2. **0절 확정 정책이 우선**하며, 기존 상세 표에 남은 제안/선택/예시는 구현 전에 정합성을 점검해야 합니다. 특히 이메일 가입 비밀번호 필수 여부와 카테고리 식별자 타입을 주의합니다.
3. 미확정: 인증번호 만료·재전송·시도 제한, 카테고리 실제 목록·식별자 타입, JWT refresh 정책, 아이 삭제 사진 파일 정리 방식, 관리자 입력 UI, PG·환불 정책, 기타 5절 항목.
4. 실제 결제·외부 실명 인증은 Mock/인터페이스와 실운영 연동을 명확히 분리합니다.
5. 프론트엔드와 백엔드 개발자는 **엔드포인트·필드·응답 구조를 합의한 뒤** 구현하며, 변경 시 문서 버전을 올립니다.
