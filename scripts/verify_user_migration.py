"""Read-only bridged/final verification with one evidenced index-name exception."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

import MySQLdb

ROOT = Path(__file__).resolve().parents[1]
ACTUAL_INDEX = "django_admin_log_user_id_fk_accounts_user"
REHEARSAL_INDEX = "django_admin_log_user_id_c564eba6_fk_auth_user_id"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("bridged", "final"))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.conf import settings
    from scripts.run_mysql_rehearsal import digest, migration_hashes, snapshot

    evidence_dir = ROOT / ".mysql-rehearsal/20261113-181637-5c83f13f"
    report = json.loads((evidence_dir / "report.json").read_text(encoding="utf-8"))
    evidence = json.loads((evidence_dir / "index_equivalence.json").read_text(encoding="utf-8"))
    require(report["success"] and report["isolated_server_shutdown"], "Rehearsal incomplete")
    require(digest(Path(report["backup"]["path"]).read_bytes()) == report["backup"]["sha256"], "Backup hash changed")
    require(migration_hashes() == report["migration_hashes_before"], "Migration files changed")
    require(evidence["status"] == "PASS" and evidence["only_allowed_name_pair"] == [ACTUAL_INDEX, REHEARSAL_INDEX], "Unapproved index exception")
    actual_evidence, rehearsal_evidence = evidence["comparisons"]
    require((actual_evidence["schema"], actual_evidence["index_name"]) == ("yippee_club_db", ACTUAL_INDEX), "Wrong actual index evidence")
    require((rehearsal_evidence["schema"], rehearsal_evidence["index_name"]) == ("test_yippee_migration_legacy", REHEARSAL_INDEX), "Wrong rehearsal index evidence")
    for key in ("statistics", "foreign_key", "foreign_key_columns"):
        require(actual_evidence[key] == rehearsal_evidence[key] and len(actual_evidence[key]) == 1, "Index/FK evidence differs: " + key)
    expected_index = {
        "NON_UNIQUE": 1, "SEQ_IN_INDEX": 1, "COLUMN_NAME": "user_id", "COLLATION": "A",
        "CARDINALITY": 0, "SUB_PART": None, "PACKED": None, "NULLABLE": "",
        "INDEX_TYPE": "BTREE", "COMMENT": "", "INDEX_COMMENT": "", "IS_VISIBLE": "YES", "EXPRESSION": None,
    }
    require(actual_evidence["statistics"] == [expected_index], "Unexpected evidenced index properties")
    config = settings.DATABASES["default"]
    require((config["NAME"], int(config["PORT"]), config["USER"]) == ("yippee_club_db", 3306, "yippee_app"), "Configured target rejected")
    db = MySQLdb.connect(host=config["HOST"], port=int(config["PORT"]), user=config["USER"],
                         passwd=config["PASSWORD"], db=config["NAME"], charset="utf8mb4", connect_timeout=5)
    try:
        with db.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SELECT DATABASE(),CURRENT_USER(),@@server_uuid,@@port")
            identity = cursor.fetchone()
            require(identity == ("yippee_club_db", "yippee_app@localhost", "5491c807-5688-11f1-a0bf-c86e08e6aa63", 3306), "Actual server identity rejected")
        with db.cursor(MySQLdb.cursors.DictCursor) as cursor:
            cursor.execute("SELECT NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,COLLATION,CARDINALITY,SUB_PART,"
                           "PACKED,NULLABLE,INDEX_TYPE,COMMENT,INDEX_COMMENT,IS_VISIBLE,EXPRESSION "
                           "FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() "
                           "AND TABLE_NAME='django_admin_log' AND INDEX_NAME=%s ORDER BY SEQ_IN_INDEX", (ACTUAL_INDEX,))
            require(list(cursor.fetchall()) == actual_evidence["statistics"], "Live index structure changed")
            cursor.execute("SELECT CONSTRAINT_NAME,UNIQUE_CONSTRAINT_NAME,MATCH_OPTION,UPDATE_RULE,DELETE_RULE,"
                           "TABLE_NAME,REFERENCED_TABLE_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
                           "WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_NAME=%s", (ACTUAL_INDEX,))
            require(list(cursor.fetchall()) == actual_evidence["foreign_key"], "Live FK rules changed")
            cursor.execute("SELECT ORDINAL_POSITION,POSITION_IN_UNIQUE_CONSTRAINT,COLUMN_NAME,"
                           "REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                           "WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='django_admin_log' "
                           "AND CONSTRAINT_NAME=%s AND REFERENCED_TABLE_SCHEMA=DATABASE() ORDER BY ORDINAL_POSITION", (ACTUAL_INDEX,))
            require(list(cursor.fetchall()) == actual_evidence["foreign_key_columns"], "Live FK target changed")
        actual = json.loads(json.dumps(snapshot(db), default=str))
    finally:
        db.rollback()
        db.close()

    expected = report["legacy_after_0002" if args.stage == "bridged" else "legacy_final"]
    require(actual["migrations"] == expected["migrations"], "Unexpected migration set")
    require(actual["foreign_keys"] == expected["foreign_keys"], "Unexpected FK change")
    require(actual["tables"].keys() == expected["tables"].keys(), "Unexpected table set")
    for table, current in actual["tables"].items():
        target = expected["tables"][table]
        require(current["columns"] == target["columns"], "Column mismatch: " + table)
        expected_schema = target["schema"]
        if table == "django_admin_log":
            old = "KEY `" + REHEARSAL_INDEX + "` (`user_id`)"
            new = "KEY `" + ACTUAL_INDEX + "` (`user_id`)"
            require(expected_schema.count(old) == 1 and current["schema"].count(new) == 1, "Index name pair no longer matches")
            # One exact KEY definition only; never rewrite FK names or other indexes.
            expected_schema = expected_schema.replace(old, new, 1)
        # Preserve the original verifier's treatment of rehearsal smoke-test
        # auto-increment counters; all column definitions remain exact above.
        normalize = lambda sql: re.sub(r" AUTO_INCREMENT=\d+", "", sql)
        require(normalize(current["schema"]) == normalize(expected_schema), "Schema mismatch: " + table)
        require(current["count"] == target["count"], "Row count mismatch: " + table)
    for table, original in report["source_before"]["tables"].items():
        require(set(original["row_hashes"]) <= set(actual["tables"][table]["row_hashes"]), "Original rows changed: " + table)
    count = 20 if args.stage == "bridged" else 21
    require(len(actual["migrations"]) == count and len(actual["tables"]) == (13 if count == 20 else 15), "Stage counts differ")
    result = {"status": "PASS", "stage": args.stage, "identity": identity,
              "table_count": len(actual["tables"]), "migration_count": len(actual["migrations"]),
              "index_properties_and_fk_match_evidence": True, "original_rows_preserved": True,
              "only_index_name_exception": [ACTUAL_INDEX, REHEARSAL_INDEX], "state": actual}
    # A new writable directory; original evidence and protected verifier stay intact.
    output = ROOT / ".mysql-rehearsal/application-validation"
    output.mkdir(exist_ok=True)
    (output / (args.stage + ".json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "state"}))


if __name__ == "__main__":
    main()
