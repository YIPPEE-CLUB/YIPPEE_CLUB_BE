import importlib
import os
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from scripts import rehearsal_target


class ManualToolSafetyTests(unittest.TestCase):
    def test_wrong_server_rejected_before_mutation(self):
        with patch.object(rehearsal_target, "_admin_sql", return_value="1\t3306") as transport:
            with self.assertRaises(RuntimeError):
                rehearsal_target.admin_sql("CREATE DATABASE forbidden;")
            self.assertEqual(transport.call_count, 1)
            self.assertNotIn("CREATE", transport.call_args.args[0])

    def test_verified_server_uses_only_isolated_port(self):
        with patch.object(rehearsal_target, "_admin_sql", side_effect=["9133307\t33307", "ok"]) as transport:
            self.assertEqual(rehearsal_target.admin_sql("SELECT 1"), "ok")
            self.assertTrue(all(call.kwargs == {"port": 33307} for call in transport.call_args_list))


class SettingsSafetyTests(unittest.TestCase):
    def test_rehearsal_guard_blocks_wrong_database_and_wrong_server(self):
        with patch.dict(os.environ, {
            "YIPPEE_REHEARSAL_DATABASE": "test_yippee_migration_legacy",
            "YIPPEE_REHEARSAL_PORT": "33307", "YIPPEE_REHEARSAL_PASSWORD": "unit-test-only",
        }):
            module = importlib.import_module("config.user_model_rehearsal")
        target = dict(module.DATABASES["default"])
        raw = MagicMock()
        raw.fetchone.return_value = (1, 3306)
        wrapper = SimpleNamespace(settings_dict=target, connection=SimpleNamespace(cursor=lambda: raw))
        execute = MagicMock()
        from django.core.exceptions import ImproperlyConfigured
        with self.assertRaises(ImproperlyConfigured):
            module.guard_rehearsal_sql(execute, "ALTER TABLE x", None, False, {"connection": wrapper})
        execute.assert_not_called()
        target["NAME"] = "yippee_club_db"
        raw.reset_mock()
        with self.assertRaises(ImproperlyConfigured):
            module.guard_rehearsal_sql(execute, "ALTER TABLE x", None, False, {"connection": wrapper})
        raw.execute.assert_not_called()
        execute.assert_not_called()
