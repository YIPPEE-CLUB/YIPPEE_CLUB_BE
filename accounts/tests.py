from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django.conf import settings
from unittest import skipUnless

from .managers import UserManager
from .apps import block_preview_sql
if apps.is_installed("accounts"):
    from .models import User


@skipUnless(apps.is_installed("accounts"), "Custom User is staged and inactive in the current settings.")
class UserDesignTests(SimpleTestCase):
    """Offline design checks; no account is saved and no DB is accessed."""

    def test_email_identifier_has_database_uniqueness(self):
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertTrue(User._meta.get_field("email").unique)
        self.assertEqual(User.REQUIRED_FIELDS, [])
        self.assertNotIn("username", [field.name for field in User._meta.fields])

    def test_email_normalization(self):
        self.assertEqual(UserManager.normalize_email(" Parent@Example.COM "), "parent@example.com")

    def test_password_is_hashed_and_unusable_password_supported(self):
        user = User(email="parent@example.com")
        user.set_password("ExamplePassword921!")
        self.assertNotEqual(user.password, "ExamplePassword921!")
        self.assertTrue(user.check_password("ExamplePassword921!"))
        self.assertFalse(user.check_password("wrong"))
        user.set_unusable_password()
        self.assertFalse(user.has_usable_password())

    def test_invalid_manager_inputs_fail_before_database_access(self):
        for email in (None, "", "not-an-email"):
            with self.assertRaises((ValueError, ValidationError)):
                User.objects.create_user(email=email)
        for flags in ({"is_staff": False}, {"is_superuser": False}, {"is_active": False}):
            with self.assertRaises(ValueError):
                User.objects.create_superuser("admin@example.com", "ExamplePassword921!", **flags)

    def test_preview_selects_configured_user(self):
        self.assertEqual(get_user_model()._meta.label, settings.AUTH_USER_MODEL)

    def test_initial_migration_and_admin_dependencies_offline(self):
        loader = MigrationLoader(None)
        user = loader.project_state([("accounts", "0001_initial")]).apps.get_model("accounts", "User")
        self.assertEqual(user._meta.get_field("email").unique, True)
        plan = loader.graph.forwards_plan(("admin", "0001_initial"))
        if settings.AUTH_USER_MODEL == "accounts.User":
            self.assertLess(plan.index(("accounts", "0001_initial")), plan.index(("admin", "0001_initial")))
        else:
            self.assertNotIn(("accounts", "0001_initial"), plan)
        bridge_plan = loader.graph.forwards_plan(("accounts", "0002_bridge_admin_user"))
        self.assertLess(bridge_plan.index(("accounts", "0001_initial")), bridge_plan.index(("accounts", "0002_bridge_admin_user")))
        self.assertLess(bridge_plan.index(("admin", "0003_logentry_add_action_flag_choices")), bridge_plan.index(("accounts", "0002_bridge_admin_user")))

    @skipUnless(getattr(settings, "USER_MODEL_OFFLINE_PREVIEW", False), "SQL blocker is preview-only.")
    def test_preview_blocks_new_default_and_test_creation_connections(self):
        from django.core.exceptions import ImproperlyConfigured
        from config.offline_mysql.base import DatabaseWrapper
        from unittest.mock import patch

        # Test the connection factory directly: no real socket can be opened.
        from django.db.backends.mysql.base import Database
        with patch.object(Database, "connect") as connect:
            for alias in ("default", "__no_db__"):
                wrapper = DatabaseWrapper(settings.DATABASES["default"], alias=alias)
                with self.assertRaises(ImproperlyConfigured):
                    wrapper.get_new_connection({})
            connect.assert_not_called()

    @skipUnless(getattr(settings, "USER_MODEL_OFFLINE_PREVIEW", False), "SQL blocker is preview-only.")
    def test_preview_rejects_database_execution(self):
        from django.core.exceptions import ImproperlyConfigured
        from django.db import connection

        self.assertIn(block_preview_sql, connection.execute_wrappers)
        with self.assertRaises(ImproperlyConfigured):
            block_preview_sql(None, "CREATE TABLE forbidden (id INT)", None, False, {})
