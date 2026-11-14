from unittest import skipUnless

from django.conf import settings
from django.test import TestCase


@skipUnless(getattr(settings, "IS_USER_MODEL_REHEARSAL", False), "Dedicated MySQL rehearsal only.")
class UserMySQLIntegrationTests(TestCase):
    # A skipped TestCase still makes DiscoverRunner prepare its databases.
    # Keep offline invocations from entering database setup at all.
    databases = {"default"} if getattr(settings, "IS_USER_MODEL_REHEARSAL", False) else set()

    def test_admin_jwt_and_email_against_mysql(self):
        from scripts.rehearsal_checks import run_smoke

        run_smoke()
