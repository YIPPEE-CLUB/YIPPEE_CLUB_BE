"""오프라인 테스트: MySQL 프로세스·DB 접속·자격정보 파일을 사용하지 않는다."""
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import grant_mysql_rehearsal as target
from scripts import setup_mysql_dev as transport


USAGE = "GRANT USAGE ON *.* TO `yippee_rehearsal`@`localhost`"
# MySQL 8.0 문서 및 로컬 8.0.46 SHOW GRANTS의 출력 형태를 따른 합성 fixture.
# 실제 전용 계정의 권한을 변경하거나 그 계정의 비밀정보를 읽지 않는다.
SCOPES = (r"test\_yippee\_migration\_legacy", r"test\_yippee\_migration\_fresh")
ORDER = "SELECT, INSERT, UPDATE, DELETE, CREATE, REFERENCES, INDEX, ALTER"


def grant(scope, privileges=ORDER):
    return f"GRANT {privileges} ON `{scope}`.* TO `yippee_rehearsal`@`localhost`"


class GrantSqlTests(unittest.TestCase):
    def test_exact_mysql_sql_and_one_backslash_per_underscore(self):
        expected = (
            r"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `test\_yippee\_migration\_legacy`.* TO 'yippee_rehearsal'@'localhost';" + "\n" +
            r"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `test\_yippee\_migration\_fresh`.* TO 'yippee_rehearsal'@'localhost';" + "\n"
        )
        self.assertEqual(target.build_grant_sql(), expected)
        for name, scope in zip(target.DATABASES, SCOPES):
            self.assertEqual(target.database_scope(name), scope)
            self.assertEqual(scope.count("\\"), name.count("_"))
            self.assertNotIn("\\\\", scope)
        self.assertNotIn(r"\*", expected)
        self.assertNotIn(r"\`", expected)

    def test_unknown_database_rejected(self):
        with self.assertRaises(ValueError):
            target.database_scope("unapproved_database")

    def test_sql_delivered_unchanged_through_stdin_not_shell_or_arguments(self):
        class CaptureInput(io.BytesIO):
            def close(self):
                self.payload = self.getvalue()
                super().close()

        stdin = CaptureInput()
        process = SimpleNamespace(
            stdin=stdin, stdout=io.BytesIO(b""), stderr=io.BytesIO(b""),
            returncode=0, wait=lambda: 0,
        )
        sql = target.build_grant_sql()
        with patch.object(transport.subprocess, "Popen", return_value=process) as popen, patch("builtins.print"):
            transport.admin_sql(sql)
        self.assertEqual(stdin.payload, sql.encode("utf-8"))
        self.assertNotIn(sql, popen.call_args.args[0])
        self.assertFalse(popen.call_args.kwargs.get("shell", False))
        self.assertIn("--raw", popen.call_args.args[0])


class ShowGrantsTests(unittest.TestCase):
    def test_mysql8_usage_and_schema_grants(self):
        target.validate_grants([USAGE, *map(grant, SCOPES)], complete=True)

    def test_privilege_order_and_comma_whitespace_do_not_matter(self):
        order = ",".join(reversed(target.PRIVILEGE_ORDER))
        target.validate_grants([grant(scope, order) for scope in reversed(SCOPES)], complete=True)

    def test_usage_alone_allowed_only_before_grant(self):
        target.validate_grants([USAGE])
        with self.assertRaises(RuntimeError):
            target.validate_grants([USAGE], complete=True)

    def test_empty_output_rejected(self):
        with self.assertRaises(RuntimeError):
            target.validate_grants([])

    def test_unescaped_underscore_rejected(self):
        for name in target.DATABASES:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                target.validate_grants([grant(name)])

    def test_doubled_actual_backslashes_rejected_not_normalized(self):
        for scope in SCOPES:
            with self.subTest(scope=scope), self.assertRaises(RuntimeError):
                target.validate_grants([grant(scope.replace("\\", "\\\\"))])

    def test_partial_or_percent_wildcard_escapes_rejected(self):
        for scope in (SCOPES[0].replace(r"\_", "_", 1), "yippee%", "*", "other_db"):
            with self.subTest(scope=scope), self.assertRaises(RuntimeError):
                target.validate_grants([grant(scope)])

    def test_repr_is_not_accepted_as_server_output(self):
        with self.assertRaises(RuntimeError):
            target.validate_grants([repr(grant(SCOPES[0]))])

    def test_global_privileges_roles_grant_option_and_revokes_rejected(self):
        invalid = (
            "GRANT SELECT ON *.* TO `yippee_rehearsal`@`localhost`",
            "GRANT `role_name`@`%` TO `yippee_rehearsal`@`localhost`",
            grant(SCOPES[0]) + " WITH GRANT OPTION",
            "REVOKE SELECT ON `other`.* FROM `yippee_rehearsal`@`localhost`",
            grant(SCOPES[0], "ALL PRIVILEGES"),
            grant(SCOPES[0], ORDER + ", DROP"),
        )
        for line in invalid:
            with self.subTest(line=line), self.assertRaises(RuntimeError):
                target.validate_grants([line])

    def test_account_host_and_table_scope_must_match(self):
        invalid = (
            grant(SCOPES[0]).replace("`localhost`", "`%`"),
            grant(SCOPES[0]).replace("`yippee_rehearsal`", "`other_user`"),
            grant(SCOPES[0]).replace("`.* TO", "`.`some_table` TO"),
        )
        for line in invalid:
            with self.subTest(line=line), self.assertRaises(RuntimeError):
                target.validate_grants([line])

    def test_complete_requires_both_scopes_and_all_privileges(self):
        for lines in ([grant(SCOPES[0])], [grant(SCOPES[0]), grant(SCOPES[1], "SELECT")]):
            with self.assertRaises(RuntimeError):
                target.validate_grants(lines, complete=True)

    def test_duplicate_or_malformed_privilege_tokens_rejected(self):
        for privileges in ("SELECT, SELECT", "SELECT,", ",SELECT", "SELECT,,INSERT"):
            with self.subTest(privileges=privileges), self.assertRaises(RuntimeError):
                target.validate_grants([grant(SCOPES[0], privileges)])

    def test_unexpected_suffix_or_extra_statement_rejected(self):
        for suffix in (";", "; SELECT 1", " /* comment */"):
            with self.subTest(suffix=suffix), self.assertRaises(RuntimeError):
                target.validate_grants([grant(SCOPES[0]) + suffix])


if __name__ == "__main__":
    unittest.main()
