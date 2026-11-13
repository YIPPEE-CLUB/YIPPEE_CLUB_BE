"""Real ORM/Admin/JWT/email checks, restricted to the dedicated instance."""
import re

from django.conf import settings
from django.core import mail
from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer


def run_smoke():
    if not getattr(settings, "IS_USER_MODEL_REHEARSAL", False):
        raise RuntimeError("Smoke checks require isolated rehearsal settings.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@server_id, @@port, DATABASE()")
        identity = cursor.fetchone()
    if identity[:2] != (9133307, 33307) or identity[2] not in (
        "test_yippee_migration_legacy", "test_yippee_migration_fresh",
        "test_yippee_migration_suite",
    ):
        raise RuntimeError("Smoke checks target rejected.")
    with transaction.atomic(), override_settings(ALLOWED_HOSTS=["testserver"]):
        User = get_user_model()
        assert User._meta.label == "accounts.User"
        password = "RehearsalPwd!729384"
        user = User.objects.create_superuser(" Admin@Example.COM ", password)
        assert user.email == "admin@example.com" and user.check_password(password)
        client = Client()
        response = client.post(reverse("admin:login"), {
            "username": user.email, "password": password, "next": reverse("admin:index"),
        })
        assert response.status_code == 302
        assert client.get(reverse("admin:index")).status_code == 200
        assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
        response = client.post(reverse("admin:accounts_user_add"), {
            "email": "Created@Example.com", "password1": password, "password2": password,
            "_save": "Save",
        })
        assert response.status_code == 302, response.status_code
        created = User.objects.get(email="created@example.com")
        assert created.check_password(password)
        new_password = "ChangedRehearsalPwd!87342"
        response = client.post(reverse("admin:auth_user_password_change", args=[created.pk]), {
            "password1": new_password, "password2": new_password,
        })
        assert response.status_code == 302, response.status_code
        created.refresh_from_db()
        assert created.check_password(new_password)
        assert LogEntry.objects.filter(user_id=user.pk, object_id=str(created.pk)).exists()
        # Explicit FK insertion proves the physical relation accepts accounts PKs.
        LogEntry.objects.create(
            user=user, content_type=ContentType.objects.get_for_model(User),
            object_id=str(user.pk), object_repr=user.email, action_flag=ADDITION,
        )
        serializer = TokenObtainPairSerializer(data={"email": user.email, "password": password})
        serializer.is_valid(raise_exception=True)
        authentication = JWTAuthentication()
        token = authentication.get_validated_token(serializer.validated_data["access"])
        assert authentication.get_user(token).pk == user.pk
        refresh = TokenRefreshSerializer(data={"refresh": serializer.validated_data["refresh"]})
        refresh.is_valid(raise_exception=True)
        assert "access" in refresh.validated_data
        api = APIClient()
        response = api.post(reverse("email_verification:identifier-check"), {
            "identifier": user.email,
        }, format="json")
        assert response.status_code == 200 and response.json()["registered"]
        response = api.post(reverse("email_verification:verification-send"), {
            "identifier": user.email, "purpose": "signup",
        }, format="json")
        assert response.status_code == 409
        response = api.post(reverse("email_verification:verification-send"), {
            "identifier": "signup-rehearsal@example.com", "purpose": "signup",
        }, format="json")
        assert response.status_code == 200
        verification_id = response.json()["verification_id"]
        code = re.search(r"인증번호: ([0-9]{6})", mail.outbox[-1].body).group(1)
        payload = {"verification_id": verification_id, "code": code}
        response = api.post(reverse("email_verification:verification-confirm"), payload, format="json")
        assert response.status_code == 200 and response.json()["verified"]
        from email_verification.models import EmailVerification
        challenge = EmailVerification.objects.get(pk=verification_id)
        assert challenge.code_digest == "" and challenge.token_digest != response.json()["verification_token"]
        assert api.post(reverse("email_verification:verification-confirm"), payload, format="json").status_code == 409
        user.is_active = False
        user.save(update_fields=["is_active"])
        try:
            authentication.get_user(token)
        except AuthenticationFailed:
            pass
        else:
            raise AssertionError("Inactive JWT user accepted")
        transaction.set_rollback(True)  # Preserve all restored source records.
    print("Real MySQL Admin create/login/password/log, JWT obtain/refresh/user lookup, email send/confirm/reuse: OK")
