from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

from email_verification.errors import AuthError
from email_verification.models import EmailVerification
from email_verification.security import digest

from .models import RefreshSession
from .serializers import check_new_password

RESET_SALT = "accounts.password-reset"


def _token_digest(raw):
    return digest(raw, "accounts.refresh-session")


@sensitive_variables()
def issue_tokens(user):
    token = RefreshToken.for_user(user)
    raw = str(token)
    RefreshSession.objects.create(
        user=user, token_digest=_token_digest(raw),
        expires_at=datetime.fromtimestamp(token["exp"], tz=datetime_timezone.utc),
    )
    return {"access_token": str(token.access_token), "refresh_token": raw}


@sensitive_variables()
def signup(data):
    User = get_user_model()
    with transaction.atomic():
        proof = EmailVerification.objects.select_for_update().filter(
            token_digest=digest(data["verification_token"], "email_verification.verification-token")
        ).first()
        now = timezone.now()
        if (proof is None or proof.email != data["identifier"] or proof.purpose != "signup" or
                proof.verified_at is None or proof.token_expires_at is None or proof.token_expires_at <= now):
            raise AuthError("이메일 인증을 완료해 주세요.")
        if proof.consumed_at is not None:
            raise AuthError("이미 사용한 인증입니다.", status=409, code="INVALID_STATE")
        if User.objects.filter(email__iexact=data["identifier"]).exists():
            raise AuthError("이미 가입한 이메일입니다.", status=409, code="ALREADY_EXISTS")
        try:
            with transaction.atomic():
                user = User.objects.create_user(data["identifier"], data["password"], agreements=data["agreements"])
        except IntegrityError:
            if User.objects.filter(email__iexact=data["identifier"]).exists():
                raise AuthError("이미 가입한 이메일입니다.", status=409, code="ALREADY_EXISTS") from None
            raise
        proof.consumed_at = now
        proof.save(update_fields=["consumed_at"])
        return {"user_id": user.pk, **issue_tokens(user)}


@sensitive_variables()
def login(email, password):
    User = get_user_model()
    with transaction.atomic():
        user = User.objects.select_for_update().filter(email__iexact=email).first()
        if user is None:
            User().set_password(password)  # Match the password-hash cost for unknown users.
            raise AuthError("이메일 또는 비밀번호를 확인해 주세요.")
        if not user.check_password(password) or not user.is_active:
            raise AuthError("이메일 또는 비밀번호를 확인해 주세요.")
        return user, issue_tokens(user)


@sensitive_variables()
def _locked_refresh(raw):
    try:
        token = RefreshToken(raw)
        user = get_user_model().objects.select_for_update().filter(
            pk=token[api_settings.USER_ID_CLAIM], is_active=True
        ).first()
    except (TokenError, KeyError, TypeError, ValueError, OverflowError):
        raise AuthError("토큰을 확인해 주세요.") from None
    if user is None or (api_settings.CHECK_REVOKE_TOKEN and
            token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password)):
        raise AuthError("토큰을 확인해 주세요.")
    session = RefreshSession.objects.select_for_update().filter(user=user, token_digest=_token_digest(raw)).first()
    if session is None or session.expires_at <= timezone.now():
        raise AuthError("토큰을 확인해 주세요.")
    return token, session


@sensitive_variables()
def refresh(raw):
    with transaction.atomic():
        token, session = _locked_refresh(raw)
        if session.revoked_at is not None:
            raise AuthError("토큰을 확인해 주세요.")
        # No implicit rotation/extension: v1.5 has not fixed a rotation policy.
        return {"access_token": str(token.access_token), "refresh_token": raw}


@sensitive_variables()
def logout(raw):
    if raw is None:
        return  # No supplied credential means no server-side revocation target.
    with transaction.atomic():
        _, session = _locked_refresh(raw)
        if session.revoked_at is None:
            session.revoked_at = timezone.now()
            session.save(update_fields=["revoked_at"])


@sensitive_variables()
def change_password(user_id, current_password, new_password):
    with transaction.atomic():
        user = get_user_model().objects.select_for_update().get(pk=user_id)
        if not user.check_password(current_password):
            raise AuthError("현재 비밀번호를 확인해 주세요.")
        _set_password(user, new_password)


@sensitive_variables()
def _set_password(user, password):
    check_new_password(password, user)
    user.set_password(password)
    user.save(update_fields=["password"])
    RefreshSession.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())


@sensitive_variables()
def request_password_reset(email):
    user = get_user_model().objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        return
    token = signing.dumps({"uid": user.pk, "proof": default_token_generator.make_token(user)}, salt=RESET_SALT)
    try:
        sent = send_mail("YIPPEE CLUB 비밀번호 재설정", "비밀번호 재설정 토큰: " + token,
                         settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        if sent != 1:
            raise RuntimeError("Mail not delivered")
    except Exception:
        raise AuthError("메일 발송에 실패했습니다.", status=500, code="INTERNAL_SERVER_ERROR") from None


@sensitive_variables()
def confirm_password_reset(raw, new_password):
    try:
        payload = signing.loads(raw, salt=RESET_SALT, max_age=settings.PASSWORD_RESET_TIMEOUT)
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().filter(pk=payload["uid"], is_active=True).first()
            if user is None or not default_token_generator.check_token(user, payload["proof"]):
                raise AuthError("재설정 토큰을 확인해 주세요.")
            _set_password(user, new_password)
    except (signing.BadSignature, KeyError, TypeError, ValueError, OverflowError):
        raise AuthError("재설정 토큰을 확인해 주세요.") from None
