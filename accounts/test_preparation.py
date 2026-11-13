"""Database-free transition/Admin tests; no migration is applied here."""
import importlib
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.migrations.exceptions import InconsistentMigrationHistory
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.state import ProjectState
from django.test import RequestFactory, SimpleTestCase
from django.utils import translation


@skipUnless(apps.is_installed("accounts"), "Run with a SQL-blocked User preview configuration.")
class PreparationTests(SimpleTestCase):
    def test_models_match_existing_migrations_without_database_access(self):
        loader = MigrationLoader(None)
        # Match makemigrations' no_translations behavior for lazy field labels.
        with translation.override(None):
            changes = MigrationAutodetector(
                loader.project_state(), ProjectState.from_apps(apps)
            ).changes(graph=loader.graph)
        self.assertEqual(changes, {})

    def test_jwt_uses_active_user_model_and_email_identifier(self):
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
        from rest_framework_simplejwt.settings import api_settings
        from rest_framework_simplejwt.tokens import AccessToken

        user_model = get_user_model()
        user = user_model(pk=17, email="parent@example.com", is_active=True)
        user.set_password("ExamplePwd!38926")
        authentication = JWTAuthentication()
        self.assertIs(authentication.user_model, user_model)
        self.assertEqual(TokenObtainPairSerializer.username_field, user_model.USERNAME_FIELD)
        token = AccessToken.for_user(user)
        validated = authentication.get_validated_token(str(token))
        with patch.object(user_model.objects, "get", return_value=user) as lookup:
            self.assertIs(authentication.get_user(validated), user)
        lookup.assert_called_once_with(**{api_settings.USER_ID_FIELD: str(user.pk)})
        user.is_active = False
        from rest_framework.exceptions import AuthenticationFailed
        with patch.object(user_model.objects, "get", return_value=user):
            with self.assertRaises(AuthenticationFailed):
                authentication.get_user(validated)

    def test_admin_registers_only_the_active_user(self):
        from .models import User
        self.assertTrue(admin.site.is_registered(get_user_model()))
        self.assertEqual(admin.site.is_registered(User), settings.AUTH_USER_MODEL == "accounts.User")

    def test_creation_and_change_forms_have_no_username_dependency(self):
        from .admin import EmailUserAdmin
        from .forms import EmailUserChangeForm
        from .models import User
        request = RequestFactory().get("/")
        request.user = User(is_active=True, is_staff=True, is_superuser=True)
        user_admin = EmailUserAdmin(User, admin.AdminSite())
        form = user_admin.get_form(request)()
        self.assertEqual(set(form.fields), {"email", "password1", "password2"})
        self.assertTrue(form.fields["password1"].required)
        self.assertTrue(EmailUserChangeForm().fields["password"].disabled)
        self.assertEqual(user_admin.check(), [])

    def test_admin_creation_normalizes_email_and_hashes_password_without_saving(self):
        from .forms import EmailUserCreationForm
        from .models import User
        form = EmailUserCreationForm(data={
            "email": " Parent@Example.COM ", "password1": "ExamplePwd!38926",
            "password2": "ExamplePwd!38926",
        })
        with patch.object(User, "validate_unique"):
            self.assertTrue(form.is_valid(), list(form.errors))
        user = form.save(commit=False)
        self.assertIsNone(user.pk)
        self.assertEqual(user.email, "parent@example.com")
        self.assertTrue(user.check_password("ExamplePwd!38926"))

    def test_admin_creation_rejects_mismatched_passwords(self):
        from .forms import EmailUserCreationForm
        from .models import User
        with patch.object(User, "validate_unique"):
            form = EmailUserCreationForm(data={"email": "parent@example.com", "password1": "ExamplePwd!38926", "password2": "different"})
            self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_legacy_history_is_consistent_until_user_setting_changes(self):
        loader = MigrationLoader(None)
        existing = {key: None for key in loader.graph.nodes if key[0] in {"auth", "admin", "contenttypes", "sessions"}}
        with patch("django.db.migrations.loader.MigrationRecorder") as recorder:
            recorder.return_value.applied_migrations.return_value = existing
            if settings.AUTH_USER_MODEL == "accounts.User":
                with self.assertRaises(InconsistentMigrationHistory):
                    loader.check_consistent_history(SimpleNamespace(alias="offline"))
                existing[("accounts", "0001_initial")] = None
            loader.check_consistent_history(SimpleNamespace(alias="offline"))

    def fake_bridge(self, target="auth_user", count=0, database="test_yippee_rehearsal"):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (count,)
        cursor.fetchall.return_value = [("django_admin_log", "int"), ("accounts_user", "int")]
        introspection = MagicMock()
        introspection.table_names.return_value = ["accounts_user", "django_admin_log", "auth_user", "auth_user_groups", "auth_user_user_permissions"]
        old = {"actual_legacy_constraint": {"columns": ["user_id"], "foreign_key": (target, "id")}}
        new = {"django_admin_log_user_id_fk_accounts_user": {"columns": ["user_id"], "foreign_key": ("accounts_user", "id")}}
        introspection.get_constraints.side_effect = [old, new]
        connection = SimpleNamespace(vendor="mysql", settings_dict={"NAME": database}, cursor=MagicMock(return_value=cursor), introspection=introspection)
        editor = SimpleNamespace(connection=connection, quote_name=lambda name: '`' + name.replace('`', '``') + '`', execute=MagicMock())
        bridge = importlib.import_module("accounts.migrations.0002_bridge_admin_user").bridge_admin_user
        return bridge, editor, cursor

    def test_empty_legacy_bridge_uses_actual_fk_and_never_changes_table_data(self):
        bridge, editor, cursor = self.fake_bridge()
        bridge(None, editor)
        editor.execute.assert_called_once()
        sql = editor.execute.call_args.args[0]
        self.assertIn("DROP FOREIGN KEY `actual_legacy_constraint`", sql)
        self.assertIn("REFERENCES `accounts_user` (`id`)", sql)
        for forbidden in ("DROP TABLE", "DELETE ", "TRUNCATE ", "django_migrations"):
            self.assertNotIn(forbidden, sql)
        self.assertTrue(all(call.args[0].lstrip().startswith("SELECT") for call in cursor.execute.call_args_list))

    def test_fresh_install_with_custom_user_fk_is_noop_even_with_user_data(self):
        bridge, editor, cursor = self.fake_bridge(target="accounts_user", count=3)
        bridge(None, editor)
        editor.execute.assert_not_called()
        cursor.execute.assert_not_called()

    def test_existing_user_data_blocks_bridge_before_ddl(self):
        bridge, editor, _ = self.fake_bridge(count=1)
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.execute.assert_not_called()

    def test_unknown_fk_target_blocks_bridge(self):
        bridge, editor, _ = self.fake_bridge(target="unexpected_users")
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.execute.assert_not_called()

    def test_other_database_is_rejected_without_even_opening_cursor(self):
        bridge, editor, _ = self.fake_bridge(database="unapproved_database")
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.connection.cursor.assert_not_called()
        editor.execute.assert_not_called()

    def test_key_type_mismatch_blocks_bridge(self):
        bridge, editor, cursor = self.fake_bridge()
        cursor.fetchall.return_value = [("django_admin_log", "int"), ("accounts_user", "bigint")]
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.execute.assert_not_called()

    def test_legacy_user_group_permissions_block_bridge(self):
        bridge, editor, cursor = self.fake_bridge()
        cursor.fetchone.side_effect = [(0,)] * 5 + [(1,)]
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.execute.assert_not_called()

    def test_missing_or_ambiguous_admin_fk_blocks_bridge(self):
        for constraints in ({}, {
            "one": {"columns": ["user_id"], "foreign_key": ("auth_user", "id")},
            "two": {"columns": ["user_id"], "foreign_key": ("accounts_user", "id")},
        }):
            bridge, editor, _ = self.fake_bridge()
            editor.connection.introspection.get_constraints.side_effect = None
            editor.connection.introspection.get_constraints.return_value = constraints
            with self.assertRaises(RuntimeError):
                bridge(None, editor)
            editor.execute.assert_not_called()

    def test_failed_postcheck_stops_instead_of_replaying_ddl(self):
        bridge, editor, _ = self.fake_bridge()
        editor.connection.introspection.get_constraints.side_effect = [
            {"legacy": {"columns": ["user_id"], "foreign_key": ("auth_user", "id")}}, {},
        ]
        with self.assertRaises(RuntimeError):
            bridge(None, editor)
        editor.execute.assert_called_once()

    def test_bridge_cannot_be_blindly_reversed(self):
        migration = importlib.import_module("accounts.migrations.0002_bridge_admin_user").Migration
        self.assertFalse(migration.operations[0].reversible)
