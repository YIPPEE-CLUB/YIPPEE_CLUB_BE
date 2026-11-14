"""Apply only the explicitly approved favorite migration against its exact rehearsal."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVIDENCE = ROOT / ".mysql-rehearsal/favorites-deploy-b36bb56183fa"
BACKUP_SHA = "35c1da37880452c8a236485379e0f128857ee4f52c34a8f269e2e9c48405ec53"


def preflight():
    from scripts.prepare_favorites_deploy import inspect_source, fingerprints
    from scripts.prepare_activity_deploy import require
    from scripts.run_mysql_rehearsal import digest
    prepared = json.loads((EVIDENCE / "report.json").read_text(encoding="utf-8"))
    require(prepared["success"] and prepared["isolated_server_shutdown"], "Rehearsal was not completed")
    backup = Path(prepared["backup"]["path"]).resolve()
    require(backup == (EVIDENCE / "yippee_club_db.sql").resolve() and
            digest(backup.read_bytes()) == prepared["backup"]["sha256"] == BACKUP_SHA, "Approved backup differs")
    require(fingerprints() == prepared["code_hashes"], "Prepared code or migration hash differs; STOP")
    actual = inspect_source()
    require(actual == prepared["before"] == prepared["after"], "Source DB/API/files differ from the rehearsal; STOP")
    print("PREFLIGHT PASS: exact approved backup/code/DB/FK/files; sole plan favorites.0001_initial", flush=True)
    return prepared, actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply the one explicitly approved migration after exact checks")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    prepared, before = preflight()
    if not args.apply:
        return
    from django.core.management import call_command
    from django.db import connection
    from scripts.prepare_activity_deploy import require, guard_source, normalized
    from scripts.prepare_favorites_deploy import source_plan, fingerprints, preserved
    from scripts.check_favorite_source import capture
    from scripts.register_sample_activities import verify_api, verify_http
    from scripts.run_mysql_rehearsal import digest
    run = ROOT / ".mysql-rehearsal" / ("favorites-apply-" + uuid.uuid4().hex[:12])
    run.mkdir(exist_ok=False)
    user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    print("ARTIFACTS=" + str(run), flush=True)
    report = {"success": False, "approved_target": ["favorites", "0001_initial"], "before": before,
              "backup_sha256": BACKUP_SHA, "preparation": str(EVIDENCE),
              "apply_script_sha256": digest(Path(__file__).read_bytes()), "mutations": []}
    # Pin the sole new ContentType ID before any writes to constrain metadata inserts.
    with connection.execute_wrapper(guard_source), connection.cursor() as cursor:
        cursor.execute("SELECT AUTO_INCREMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='django_content_type'")
        content_type_id = cursor.fetchone()[0]

    def guarded_mutation(execute, sql, params, many, context):
        compact = " ".join(sql.split())
        upper = compact.upper()
        allowed = upper.startswith(("SELECT ", "SHOW ", "SET ", "SAVEPOINT ", "RELEASE SAVEPOINT ", "ROLLBACK TO SAVEPOINT "))
        action = None
        if re.match(r"^CREATE TABLE `favorites` \(", compact):
            allowed, action = True, "create_favorites"
        elif re.match(r"^ALTER TABLE `favorites` ADD CONSTRAINT ", compact):
            allowed, action = True, "favorite_constraint"
        elif compact.startswith("INSERT INTO `django_migrations`"):
            allowed = not many and tuple(params[:2]) == ("favorites", "0001_initial") and len(params) == 3
            action = "migration_record"
        elif compact.startswith("INSERT INTO `django_content_type`"):
            allowed = not many and tuple(params) == ("favorites", "favorite")
            action = "favorite_content_type"
        elif compact.startswith("INSERT INTO `auth_permission`"):
            triples = [params[i:i + 3] for i in range(0, len(params), 3)]
            expected = {"add_favorite", "change_favorite", "delete_favorite", "view_favorite"}
            allowed = not many and len(params) == 12 and {t[2] for t in triples} == expected and all(t[1] == content_type_id for t in triples)
            action = "favorite_permissions"
        require(allowed, "Unexpected SQL blocked before execution")
        result = guard_source(execute, sql, params, many, context)
        if action:
            report["mutations"].append(action)
        return result

    def save():
        (run / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    save()
    output = StringIO()
    try:
        # Recheck immediately before DDL; never apply after a state/code change.
        require(normalized(capture()) == before and fingerprints() == prepared["code_hashes"] and
                source_plan() == [("favorites", "0001_initial", False)], "Final apply state differs")
        with (run / "apply-started.json").open("x", encoding="utf-8") as marker:
            json.dump({"target": ["favorites", "0001_initial"], "source": before["identity"]["identity"]}, marker)
        with connection.execute_wrapper(guarded_mutation), redirect_stdout(output), redirect_stderr(output):
            call_command("migrate", "favorites", "0001_initial", interactive=False, stdout=output, stderr=output)
        report["after"] = normalized(capture())
        after = report["after"]
        preserved(before["database"], after["database"])
        expected = prepared["restores"]["test_yippee_migration_fresh"]["upgraded"]
        require(after["database"]["foreign_keys"] == expected["foreign_keys"], "Final FK set differs from rehearsal")
        for name, table in after["database"]["tables"].items():
            require(table["schema"] == expected["tables"][name]["schema"] and table["columns"] == expected["tables"][name]["columns"], "Final schema differs: " + name)
            if name != "django_migrations":
                require(table == expected["tables"][name], "Final row data differs from rehearsal: " + name)
        for key in ("identity", "private_files", "sample_files", "activity_api", "migration_hashes"):
            require(after[key] == before[key], "Original source changed: " + key)
        require(source_plan() == [], "Unexpected pending migration")
        with connection.execute_wrapper(guard_source), connection.cursor() as cursor:
            cursor.execute("SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='favorites' AND INDEX_NAME='unique_user_activity_favorite' AND NON_UNIQUE=0 ORDER BY SEQ_IN_INDEX")
            require([r[0] for r in cursor.fetchall()] == ["user_id", "activity_id"], "Favorite UNIQUE mismatch")
        logs = StringIO()
        with connection.execute_wrapper(guard_source), redirect_stdout(logs), redirect_stderr(logs):
            call_command("check", databases=["default"], stdout=logs, stderr=logs)
            call_command("makemigrations", check=True, dry_run=True, stdout=logs, stderr=logs)
            call_command("showmigrations", "favorites", stdout=logs, stderr=logs)
        (run / "checks.txt").write_text(logs.getvalue(), encoding="utf-8")
        root = ROOT / "sample_activities"
        report["public_api"] = verify_api(root, [1, 2, 3, 4], True)
        report["public_http"] = verify_http(root, [1, 2, 3, 4], True)
        require(normalized(capture()) == after, "Read-only public checks changed source data")
        report.update(success=True, authenticated_writes_tested=False, test_accounts_created=False,
                      favorites_count=0, original_data_and_files_preserved=True)
        print("APPLY PASS: favorites.0001_initial only; tables=23 migrations=26 favorites=0; original data/files unchanged", flush=True)
    finally:
        (run / "migrate.txt").write_text(output.getvalue(), encoding="utf-8")
        save()
        print("REPORT=" + str(run / "report.json"), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"), flush=True)
        sys.exit(1)
