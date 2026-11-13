import io
import re
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from .errors import auth_exception_handler
from .mail import RedactedConsoleBackend
from .models import AuthRateLimit, EmailVerification
from .security import digest
from .serializers import ConfirmSerializer, IdentifierSerializer, SendSerializer

@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AUTH_IP_LIMIT=1000, AUTH_EMAIL_LIMIT=1000,
)
class AuthAPITests(TestCase):
    email = "parent@example.com"

    def setUp(self):
        self.client = APIClient()

    def post(self, name, data):
        return self.client.post(reverse(f"email_verification:{name}"), data, format="json")

    def challenge(self, email=None):
        email = email or self.email
        response = self.post("verification-send", {"identifier": email, "purpose": "signup"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"verification_id", "expires_in_seconds"})
        code = re.search(r"인증번호: ([0-9]{6})", mail.outbox[-1].body).group(1)
        return response.json()["verification_id"], code

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(set(response.json()), {"code", "message", "details", "request_id"})

    def test_verification_secrets_are_not_stored_in_plaintext(self):
        identifier, code = self.challenge()
        challenge = EmailVerification.objects.get(pk=identifier)
        self.assertNotEqual(challenge.code_digest, code)
        response = self.post("verification-confirm", {"verification_id": identifier, "code": code})
        token = response.json()["verification_token"]
        challenge.refresh_from_db()
        self.assertEqual(challenge.code_digest, "")
        self.assertNotEqual(challenge.token_digest, token)
        self.assertEqual(challenge.token_digest, digest(token, "email_verification.verification-token"))

    def test_incorrect_code_increments_counter_without_rollback(self):
        identifier, code = self.challenge()
        wrong = "000000" if code != "000000" else "000001"
        self.assert_error(self.post("verification-confirm", {
            "verification_id": identifier, "code": wrong,
        }), 400)
        self.assertEqual(EmailVerification.objects.get(pk=identifier).attempts, 1)

    def test_code_attempt_limit(self):
        identifier, code = self.challenge()
        wrong = "000000" if code != "000000" else "000001"
        with override_settings(AUTH_CODE_MAX_ATTEMPTS=2):
            for _ in range(2):
                self.assert_error(self.post("verification-confirm", {
                    "verification_id": identifier, "code": wrong,
                }), 400)
            self.assert_error(self.post("verification-confirm", {
                "verification_id": identifier, "code": code,
            }), 429)

    def test_expired_code(self):
        identifier, code = self.challenge()
        EmailVerification.objects.filter(pk=identifier).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assert_error(self.post("verification-confirm", {
            "verification_id": identifier, "code": code,
        }), 400)

    def test_code_cannot_be_confirmed_twice(self):
        identifier, code = self.challenge()
        payload = {"verification_id": identifier, "code": code}
        self.assertEqual(self.post("verification-confirm", payload).status_code, 200)
        self.assert_error(self.post("verification-confirm", payload), 409)

    def test_resend_cooldown(self):
        self.challenge()
        self.assert_error(self.post("verification-send", {"identifier": self.email, "purpose": "signup"}), 429)

    def test_request_limit_is_persisted(self):
        with override_settings(AUTH_IP_LIMIT=1):
            self.assertEqual(self.post("identifier-check", {"identifier": self.email}).status_code, 200)
            self.assert_error(self.post("identifier-check", {"identifier": "another@example.com"}), 429)
        self.assertTrue(AuthRateLimit.objects.exists())

    def test_mail_failure_rolls_back_challenge_and_redacts_error(self):
        with patch("email_verification.verification.send_mail", side_effect=RuntimeError("secret-mail-body")):
            response = self.post("verification-send", {"identifier": self.email, "purpose": "signup"})
        self.assert_error(response, 503)
        self.assertNotIn("secret-mail-body", response.content.decode())
        self.assertFalse(EmailVerification.objects.exists())

    def test_unknown_purpose_and_phone_are_not_implemented(self):
        for data in (
            {"identifier": self.email, "purpose": "password_reset"},
            {"identifier": "01012345678", "purpose": "signup"},
        ):
            self.assert_error(self.post("verification-send", data), 400)

class AuthUnitTests(SimpleTestCase):
    def test_identifier_and_send_use_configured_user_model(self):
        from django.contrib.auth import get_user_model
        from .errors import AuthError
        from .views import IdentifierCheckView, VerificationSendView

        user_model = get_user_model()
        data = {"identifier": "parent@example.com", "purpose": "signup"}
        with patch.object(user_model.objects, "filter") as lookup:
            lookup.return_value.exists.return_value = True
            self.assertTrue(IdentifierCheckView().perform(data).data["registered"])
            with patch("email_verification.verification.send_verification") as send:
                with self.assertRaises(AuthError) as error:
                    VerificationSendView().perform(data)
                self.assertEqual(error.exception.status_code, 409)
                send.assert_not_called()
            lookup.assert_called_with(email__iexact=data["identifier"])
            lookup.return_value.exists.return_value = False
            self.assertFalse(IdentifierCheckView().perform(data).data["registered"])

    def test_console_backend_never_prints_email_secrets(self):
        message = mail.EmailMessage("secret subject", "123456", "sender@example.com", ["private@example.com"])
        output = io.StringIO()
        with patch("sys.stdout", output):
            self.assertEqual(RedactedConsoleBackend().send_messages([message]), 1)
        for secret in ("123456", "private@example.com", "secret subject"):
            self.assertNotIn(secret, output.getvalue())

    def test_identifier_accepts_only_email_and_normalizes_case(self):
        serializer = IdentifierSerializer(data={"identifier": "Parent@Example.com"})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["identifier"], "parent@example.com")
        self.assertFalse(IdentifierSerializer(data={"identifier": "01012345678"}).is_valid())

    def test_confirmation_requires_six_ascii_digits_as_string(self):
        for code in ("000001", "123456"):
            self.assertTrue(ConfirmSerializer(data={"verification_id": "ver_test", "code": code}).is_valid())
        for code in ("12345", "1234567", "１２３４５６", "abcdef", " 123456", None, 123456):
            self.assertFalse(ConfirmSerializer(data={"verification_id": "ver_test", "code": code}).is_valid())

    def test_only_signup_purpose_is_implemented(self):
        for purpose in ("password_reset", "phone_change", None):
            self.assertFalse(SendSerializer(data={"identifier": "user@example.com", "purpose": purpose}).is_valid())

    def test_error_envelope_does_not_echo_submitted_values_or_exception(self):
        secret = "private-code-and-token"
        response = auth_exception_handler(ValidationError({"code": [secret]}), {})
        self.assertNotIn(secret, str(response.data))
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})
        response = auth_exception_handler(RuntimeError(secret), {})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(secret, str(response.data))
