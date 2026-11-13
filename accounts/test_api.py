import re
import secrets
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from email_verification.models import EmailVerification
from email_verification.security import digest

from .models import RefreshSession

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False) and settings.AUTH_USER_MODEL == "accounts.User"


@skipUnless(ISOLATED, "Account API data tests require the isolated MySQL instance.")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", AUTH_IP_LIMIT=1000, AUTH_EMAIL_LIMIT=1000)
class AccountAPITests(TestCase):
    databases = {"default"} if ISOLATED else set()
    password = "SecureAccountPwd!83927"
    email = "parent@example.com"

    def setUp(self):
        self.client = APIClient()

    def post(self, name, body):
        return self.client.post(reverse("accounts:" + name), body, format="json")

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})

    def proof(self, email=None, **overrides):
        email = email or self.email
        token = secrets.token_urlsafe(32)
        now = timezone.now()
        values = dict(email=email.strip().lower(), code_digest="", expires_at=now + timedelta(minutes=3), verified_at=now,
                      token_digest=digest(token, "email_verification.verification-token"), token_expires_at=now + timedelta(minutes=10))
        values.update(overrides)
        return token, EmailVerification.objects.create(**values)

    def signup(self, email=None, **overrides):
        token, _ = self.proof(email)
        body = {"identifier": email or self.email, "verification_token": token,
                "password": self.password, "agreements": {"supplied_key": True}}
        body.update(overrides)
        return self.post("signup", body)

    def login(self, email=None, password=None):
        return self.post("login", {"email": email or self.email, "password": password or self.password})

    def authenticated(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201, response.data)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + response.data["access_token"])
        return response.data

    def test_full_email_verification_then_signup(self):
        sent = self.client.post(reverse("email_verification:verification-send"), {
            "identifier": " Parent@Example.COM ", "purpose": "signup",
        }, format="json")
        self.assertEqual(sent.status_code, 200)
        code = re.search(r"인증번호: ([0-9]{6})", mail.outbox[-1].body).group(1)
        confirmed = self.client.post(reverse("email_verification:verification-confirm"), {
            "verification_id": sent.data["verification_id"], "code": code,
        }, format="json")
        result = self.post("signup", {"identifier": self.email, "verification_token": confirmed.data["verification_token"],
                                      "password": self.password, "agreements": {}})
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(set(result.data), {"user_id", "access_token", "refresh_token"})
        user = get_user_model().objects.get(pk=result.data["user_id"])
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))
        self.assertIsNotNone(EmailVerification.objects.get(pk=sent.data["verification_id"]).consumed_at)
        self.assertEqual(RefreshSession.objects.count(), 1)
        session = RefreshSession.objects.get(user=user)
        self.assertNotEqual(session.token_digest, result.data["refresh_token"])

    def test_unverified_or_unknown_proof_rejected(self):
        for overrides in ({"verified_at": None}, {"purpose": "password_reset"},
                          {"token_expires_at": timezone.now() - timedelta(seconds=1)}):
            token, proof = self.proof(**overrides)
            response = self.post("signup", {"identifier": self.email, "password": self.password,
                                            "verification_token": token, "agreements": {}})
            self.assert_error(response, 400)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_missing_null_and_unknown_signup_fields_rejected(self):
        body = {"identifier": self.email, "password": self.password, "verification_token": "unknown", "agreements": {}}
        for field in body:
            values = body.copy()
            del values[field]
            self.assert_error(self.post("signup", values), 400)
            self.assert_error(self.post("signup", {**body, field: None}), 400)
        self.assert_error(self.post("signup", {**body, "is_staff": True}), 400)
        self.assert_error(self.post("signup", {**body, "agreements": []}), 400)

    def test_proof_bound_to_email(self):
        token, _ = self.proof("another@example.com")
        self.assert_error(self.signup(verification_token=token), 400)

    def test_consumed_proof_cannot_be_reused(self):
        token, proof = self.proof()
        body = {"identifier": self.email, "password": self.password, "verification_token": token, "agreements": {}}
        self.assertEqual(self.post("signup", body).status_code, 201)
        self.assert_error(self.post("signup", body), 409)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_duplicate_case_insensitive_email_rejected(self):
        self.assertEqual(self.signup().status_code, 201)
        self.assert_error(self.signup("Parent@Example.COM"), 409)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_signup_rolls_back_user_and_proof_if_token_issue_fails(self):
        token, proof = self.proof()
        with patch("accounts.services.issue_tokens", side_effect=RuntimeError("private-secret")):
            response = self.post("signup", {"identifier": self.email, "password": self.password,
                                            "verification_token": token, "agreements": {}})
        self.assert_error(response, 500)
        self.assertNotIn("private-secret", str(response.data))
        self.assertFalse(get_user_model().objects.exists())
        proof.refresh_from_db()
        self.assertIsNone(proof.consumed_at)

    def test_password_policy(self):
        for password in ("short1", "onlyletterslong", "123456789", "password123", 12345678):
            self.assert_error(self.signup(password=password), 400)
        self.assertFalse(get_user_model().objects.exists())

    def test_password_whitespace_is_preserved(self):
        password = " SecurePass!829341 "
        self.assertEqual(self.signup(password=password).status_code, 201)
        self.assertEqual(self.login(password=password).status_code, 200)
        self.assert_error(self.login(password=password.strip()), 400)

    def test_login_success_and_profile_contract(self):
        self.signup()
        response = self.login(email="PARENT@EXAMPLE.COM")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"access_token", "refresh_token", "user"})
        self.assertEqual(set(response.data["user"]), {"id", "email", "phone", "name"})
        self.assertNotIn("password", str(response.data))

    def test_login_bad_password_unknown_and_inactive(self):
        self.signup()
        for data in ({"email": self.email, "password": "incorrect"},
                     {"email": "unknown@example.com", "password": self.password}):
            self.assert_error(self.post("login", data), 400)
        get_user_model().objects.update(is_active=False)
        self.assert_error(self.login(), 400)

    def test_access_and_refresh(self):
        tokens = self.authenticated()
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        response = self.post("refresh", {"refresh_token": tokens["refresh_token"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"access_token", "refresh_token"})
        self.assertEqual(response.data["refresh_token"], tokens["refresh_token"])

    def test_invalid_expired_wrong_type_and_untracked_refresh(self):
        self.signup()
        user = get_user_model().objects.get()
        for token in ("invalid", str(AccessToken.for_user(user)), str(RefreshToken.for_user(user))):
            self.assert_error(self.post("refresh", {"refresh_token": token}), 400)
        tokens = self.login().data
        token = RefreshToken(tokens["refresh_token"])
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.assert_error(self.post("refresh", {"refresh_token": str(token)}), 400)

    def test_inactive_and_deleted_user_refresh_rejected(self):
        tokens = self.signup().data
        user = get_user_model().objects.get()
        user.is_active = False
        user.save()
        self.assert_error(self.post("refresh", {"refresh_token": tokens["refresh_token"]}), 400)
        user.delete()
        self.assert_error(self.post("refresh", {"refresh_token": tokens["refresh_token"]}), 400)

    def test_session_expiry_is_checked_in_addition_to_jwt_expiry(self):
        tokens = self.signup().data
        RefreshSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_error(self.post("refresh", {"refresh_token": tokens["refresh_token"]}), 400)

    def test_logout_invalidates_refresh_and_is_idempotent(self):
        tokens = self.signup().data
        body = {"refresh_token": tokens["refresh_token"]}
        self.assertEqual(self.post("logout", body).data, {"message": "처리되었습니다."})
        self.assertEqual(self.post("logout", body).status_code, 200)
        self.assert_error(self.post("refresh", body), 400)

    def test_logout_only_revokes_supplied_session(self):
        first = self.signup().data
        second = self.login().data
        self.post("logout", {"refresh_token": first["refresh_token"]})
        self.assertEqual(self.post("refresh", {"refresh_token": second["refresh_token"]}).status_code, 200)

    def test_logout_optional_null_and_invalid_token(self):
        self.assertEqual(self.post("logout", {}).status_code, 200)
        self.assertEqual(self.post("logout", {"refresh_token": None}).status_code, 200)
        self.assert_error(self.post("logout", {"refresh_token": "invalid"}), 400)

    def test_profile_requires_valid_authentication(self):
        self.assert_error(self.client.get(reverse("accounts:profile")), 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assert_error(self.client.patch(reverse("accounts:profile"), {"name": "private"}, format="json"), 401)

    def test_profile_update_and_null_clear(self):
        self.authenticated()
        response = self.client.patch(reverse("accounts:profile"), {"name": "부모", "nickname": "닉네임"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "부모")
        user = get_user_model().objects.get()
        self.assertEqual(user.nickname, "닉네임")
        response = self.client.patch(reverse("accounts:profile"), {"name": None, "nickname": None}, format="json")
        self.assertEqual(response.data["name"], "")
        self.assertEqual(self.client.patch(reverse("accounts:profile"), {}, format="json").status_code, 200)

    def test_other_users_data_and_privileged_fields_cannot_be_modified(self):
        tokens = self.authenticated()
        other = get_user_model().objects.create_user("other@example.com", self.password, name="Other")
        for key, value in (("user_id", other.pk), ("id", other.pk), ("email", other.email),
                           ("phone", "01000000000"), ("is_staff", True), ("password", "attack")):
            self.assert_error(self.client.patch(reverse("accounts:profile"), {key: value}, format="json"), 400)
        response = self.client.patch(reverse("accounts:profile"), {"name": "Only me"}, format="json")
        self.assertEqual(response.data["id"], tokens["user_id"])
        other.refresh_from_db()
        self.assertEqual(other.name, "Other")
        self.assertEqual(self.client.get(f"/api/v1/users/{other.pk}").status_code, 404)

    def test_password_change_revokes_old_credentials(self):
        tokens = self.authenticated()
        response = self.client.patch(reverse("accounts:password-change"), {
            "current_password": self.password, "new_password": "NewAccountPwd!382927",
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assert_error(self.client.get(reverse("accounts:profile")), 401)
        self.assert_error(self.post("refresh", {"refresh_token": tokens["refresh_token"]}), 400)
        self.assert_error(self.login(), 400)
        self.assertEqual(self.login(password="NewAccountPwd!382927").status_code, 200)

    def test_password_change_checks_current_and_new_password(self):
        self.authenticated()
        for current, new in (("wrong", "NewAccountPwd!382927"), (self.password, "short")):
            self.assert_error(self.client.patch(reverse("accounts:password-change"), {
                "current_password": current, "new_password": new,
            }, format="json"), 400)
        self.assertTrue(get_user_model().objects.get().check_password(self.password))

    def test_password_reset_mail_confirm_and_reuse(self):
        tokens = self.signup().data
        response = self.post("password-reset-request", {"email": self.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"message"})
        token = mail.outbox[-1].body.split(": ", 1)[1]
        body = {"reset_token": token, "new_password": "ResetSecurePwd!823948"}
        self.assertEqual(self.post("password-reset-confirm", body).status_code, 200)
        self.assert_error(self.post("password-reset-confirm", body), 400)
        self.assert_error(self.post("refresh", {"refresh_token": tokens["refresh_token"]}), 400)
        self.assertEqual(self.login(password=body["new_password"]).status_code, 200)

    def test_reset_unknown_email_invalid_token_and_mail_error(self):
        self.assertEqual(self.post("password-reset-request", {"email": "unknown@example.com"}).status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assert_error(self.post("password-reset-confirm", {"reset_token": "invalid", "new_password": self.password}), 400)
        self.signup()
        with patch("accounts.services.send_mail", side_effect=RuntimeError("private-token-secret")):
            response = self.post("password-reset-request", {"email": self.email})
        self.assert_error(response, 500)
        self.assertNotIn("private-token-secret", str(response.data))

    def test_reset_expiry_and_weak_password_do_not_change_password(self):
        self.signup()
        self.post("password-reset-request", {"email": self.email})
        token = mail.outbox[-1].body.split(": ", 1)[1]
        body = {"reset_token": token, "new_password": "AnotherSecurePwd!82934"}
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            self.assert_error(self.post("password-reset-confirm", body), 400)
        self.assert_error(self.post("password-reset-confirm", {**body, "new_password": "weak"}), 400)
        self.assertTrue(get_user_model().objects.get().check_password(self.password))
        self.assertEqual(self.post("password-reset-confirm", body).status_code, 200)

    def test_login_rate_limit(self):
        with override_settings(AUTH_IP_LIMIT=1):
            self.assert_error(self.login(), 400)
            self.assert_error(self.login(), 429)

    def test_urls_and_methods_follow_contract(self):
        self.assertEqual(reverse("accounts:signup"), "/api/v1/auth/signup")
        self.assertEqual(reverse("accounts:profile"), "/api/v1/users/me")
        self.assertEqual(self.client.get(reverse("accounts:signup")).status_code, 405)
        self.assertEqual(self.client.get(reverse("accounts:signup") + "/").status_code, 404)
