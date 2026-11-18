import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient


class HealthTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_is_public_and_returns_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Content-Type"], "application/json")

    def test_health_does_not_require_valid_credentials(self):
        response = self.client.get(
            reverse("health"), HTTP_AUTHORIZATION="Bearer invalid-token"
        )
        self.assertEqual(response.status_code, 200)

    def test_health_rejects_post(self):
        response = self.client.post(reverse("health"), {}, format="json")
        self.assertEqual(response.status_code, 405)


class ActivityFileNegotiationTests(SimpleTestCase):
    def test_binary_only_accept_returns_the_documented_error(self):
        url = reverse("activities:file", args=[1, "pdf"])
        response = APIClient().get(url, HTTP_ACCEPT="application/pdf")
        self.assertEqual(response.status_code, 406)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")
        self.assertEqual(response.json()["code"], "INVALID_STATE")


class DeploymentSecuritySettingsTests(SimpleTestCase):
    def load_settings(self, **overrides):
        environment = {"SECRET_KEY": "test-only", "MYSQL_DATABASE": "unused", "MYSQL_USER": "unused",
                       "MYSQL_PASSWORD": "unused", "MYSQL_HOST": "localhost", "MYSQL_PORT": "3306"}
        with patch.dict(os.environ, {**environment, **overrides}, clear=True), patch("environ.Env.read_env"):
            return runpy.run_path(str(Path(__file__).with_name("settings.py")))

    def test_local_http_defaults_do_not_trust_proxy_headers(self):
        config = self.load_settings()
        for setting in ("SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE",
                        "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD"):
            self.assertFalse(config[setting], setting)
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(config["CSRF_TRUSTED_ORIGINS"], [])
        self.assertIsNone(config.get("SECURE_PROXY_SSL_HEADER"))

    def test_security_options_can_be_enabled_independently_of_proxy_trust(self):
        config = self.load_settings(
            SECURE_SSL_REDIRECT="True", SESSION_COOKIE_SECURE="True", CSRF_COOKIE_SECURE="True",
            SECURE_HSTS_SECONDS="300", SECURE_HSTS_INCLUDE_SUBDOMAINS="True", SECURE_HSTS_PRELOAD="True",
            CSRF_TRUSTED_ORIGINS="https://admin.example.test,https://ops.example.test",
            SECURE_PROXY_SSL_HEADER="HTTP_X_FORWARDED_PROTO,https",
        )
        for setting in ("SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE",
                        "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD"):
            self.assertTrue(config[setting], setting)
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 300)
        self.assertEqual(config["CSRF_TRUSTED_ORIGINS"],
                         ["https://admin.example.test", "https://ops.example.test"])
        self.assertIsNone(config.get("SECURE_PROXY_SSL_HEADER"))
