import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from .errors import AuthError
from .models import EmailVerification
from .security import consume_limit, digest


@sensitive_variables("code")
def send_verification(email):
    # Separate persistent limits are committed before mail delivery so an SMTP
    # failure cannot be used to bypass the cooldown or flood the provider.
    consume_limit("send:cooldown", email, 1, settings.AUTH_SEND_COOLDOWN_SECONDS)
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = EmailVerification(
        email=email,
        expires_at=timezone.now() + timedelta(seconds=settings.AUTH_CODE_TTL_SECONDS),
    )
    challenge.code_digest = digest(f"{challenge.pk}:{code}", "email_verification.code")
    with transaction.atomic():
        challenge.save(force_insert=True)
        try:
            delivered = send_mail(
                "YIPPEE CLUB 이메일 인증",
                f"인증번호: {code}\n유효 시간: {settings.AUTH_CODE_TTL_SECONDS}초",
                settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False,
            )
            if delivered != 1:
                raise RuntimeError("Email not sent")
        except Exception:
            # Do not print mail exceptions: providers can include body/credentials.
            raise AuthError("인증 메일 발송에 실패했습니다.", status=503,
                            code="SERVICE_UNAVAILABLE") from None
    return challenge


@sensitive_variables("code", "token")
def confirm_verification(verification_id, code):
    error = None
    token = None
    now = timezone.now()
    with transaction.atomic():
        challenge = EmailVerification.objects.select_for_update().filter(pk=verification_id).first()
        if challenge is None or challenge.purpose != "signup":
            error = AuthError("인증 요청을 확인해 주세요.")
        elif challenge.verified_at or challenge.consumed_at:
            error = AuthError("이미 사용한 인증 요청입니다.", status=409, code="INVALID_STATE")
        elif challenge.expires_at <= now:
            error = AuthError("인증번호가 만료되었습니다.")
        elif challenge.attempts >= settings.AUTH_CODE_MAX_ATTEMPTS:
            error = AuthError("인증 시도 횟수를 초과했습니다.", status=429, code="RATE_LIMITED")
        else:
            challenge.attempts += 1
            if not constant_time_compare(
                challenge.code_digest, digest(f"{challenge.pk}:{code}", "email_verification.code")
            ):
                error = AuthError("인증번호가 올바르지 않습니다.")
            else:
                token = secrets.token_urlsafe(32)
                challenge.verified_at = now
                challenge.token_digest = digest(token, "email_verification.verification-token")
                challenge.token_expires_at = now + timedelta(seconds=settings.AUTH_VERIFICATION_TOKEN_TTL_SECONDS)
                challenge.code_digest = ""
            challenge.save()
    # Raising outside atomic preserves failed-attempt counters.
    if error:
        raise error
    return token
