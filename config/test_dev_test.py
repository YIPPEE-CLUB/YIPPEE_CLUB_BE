import importlib
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import Resolver404, clear_url_caches, resolve


class LocalDevPageTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        root = self.base / "local_dev"
        root.mkdir()
        (root / "index.html").write_text('<html><body data-database="{{ database_name }}">Local harness</body></html>', encoding="utf-8")
        (root / "app.js").write_text('"use strict";', encoding="utf-8")
        (root / "app.css").write_text("body {color: black}", encoding="utf-8")
        (root / ".env").write_text("PRIVATE_FIXTURE_VALUE", encoding="utf-8")
        self.overrides = override_settings(DEBUG=True, BASE_DIR=self.base,
            ALLOWED_HOSTS=["localhost", "127.0.0.1", "[::1]", "attacker.example"])
        self.overrides.enable()
        self.addCleanup(self.restore)
        self.reload_urls()

    def reload_urls(self):
        import config.urls

        importlib.reload(config.urls)
        clear_url_caches()

    def restore(self):
        self.overrides.disable()
        self.reload_urls()

    def get(self, path="/dev-test/", **kwargs):
        return self.client.get(path, HTTP_HOST=kwargs.pop("HTTP_HOST", "127.0.0.1:8000"), **kwargs)

    def test_loopback_page_and_fixed_assets_without_database(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, settings.DATABASES["default"]["NAME"])
        for file, mime in (("app.js", "text/javascript"), ("app.css", "text/css")):
            result = self.get("/dev-test/" + file)
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result["Content-Type"].startswith(mime))

    def test_no_cache_no_embedding_and_same_origin_only(self):
        for path in ("/dev-test/", "/dev-test/app.js", "/dev-test/app.css"):
            response = self.get(path)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response["X-Frame-Options"], "DENY")
            self.assertIn("connect-src 'self'", response["Content-Security-Policy"])
            self.assertEqual(response["Referrer-Policy"], "no-referrer")

    def test_remote_peer_and_forwarded_loopback_are_rejected(self):
        for path in ("/dev-test/", "/dev-test/app.js"):
            self.assertEqual(self.get(path, REMOTE_ADDR="203.0.113.10", HTTP_X_FORWARDED_FOR="127.0.0.1").status_code, 404)

    def test_non_loopback_host_is_rejected_even_when_globally_allowed(self):
        self.assertEqual(self.get(HTTP_HOST="attacker.example").status_code, 404)

    def test_ipv6_loopback_and_localhost(self):
        self.assertEqual(self.get(HTTP_HOST="localhost:8000").status_code, 200)
        self.assertEqual(self.get(HTTP_HOST="[::1]:8000", REMOTE_ADDR="::1").status_code, 200)

    def test_no_arbitrary_file_routes(self):
        for name in (".env", "settings.py", "README.md", "../.env"):
            response = self.get("/dev-test/" + name)
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, "PRIVATE_FIXTURE_VALUE", status_code=404)

    def test_missing_personal_assets_return_404(self):
        (self.base / "local_dev/index.html").unlink()
        self.assertEqual(self.get().status_code, 404)

    def test_page_is_read_only(self):
        self.assertEqual(self.client.post("/dev-test/", {}, HTTP_HOST="127.0.0.1").status_code, 405)

    def test_runtime_debug_guard_and_production_url_absence(self):
        with override_settings(DEBUG=False):
            self.assertEqual(self.get().status_code, 404)
            self.reload_urls()
            for path in ("/dev-test/", "/dev-test/app.js", "/dev-test/app.css"):
                with self.assertRaises(Resolver404):
                    resolve(path)
        self.reload_urls()
