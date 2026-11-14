from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .errors import AuthError


def digest(value, namespace):
    return salted_hmac(namespace, value, algorithm="sha256").hexdigest()


def consume_limit(scope, identity, limit, seconds):
    from .models import AuthRateLimit

    key = digest(f"{scope}:{identity}", "email_verification.rate")
    now = timezone.now()
    blocked = False
    with transaction.atomic():
        row, _ = AuthRateLimit.objects.select_for_update().get_or_create(
            key=key, defaults={"window_start": now, "count": 0}
        )
        if (now - row.window_start).total_seconds() >= seconds:
            row.window_start = now
            row.count = 0
        if row.count >= limit:
            blocked = True
        else:
            row.count += 1
            row.save(update_fields=["window_start", "count"])
    if blocked:
        raise AuthError("잠시 후 다시 시도해 주세요.", status=429, code="RATE_LIMITED")


def limit_request(request, scope, identifier=None):
    # Do not trust client-supplied X-Forwarded-For. Configure the trusted proxy
    # to provide REMOTE_ADDR before deployment.
    consume_limit(
        f"{scope}:ip", request.META.get("REMOTE_ADDR", "unknown"),
        settings.AUTH_IP_LIMIT, settings.AUTH_RATE_WINDOW_SECONDS,
    )
    if identifier:
        consume_limit(
            f"{scope}:email", identifier,
            settings.AUTH_EMAIL_LIMIT, settings.AUTH_RATE_WINDOW_SECONDS,
        )
