"""Prepare only the two shared sample categories; never fabricate sample files.

Default is inspection. --prepare-categories creates/reuses names after a fresh
read-only backup and preservation checks. Activity registration requires the
eight user-supplied files and is deliberately not performed by this script.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import os
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATEGORY_NAMES = ("신체운동·건강", "자연탐구")
FILES = ("01_징검다리_모험.pdf", "01_징검다리_표지.png", "02_숫자_놀이.pdf", "02_숫자_표지.png",
         "03_콩_놀이.pdf", "03_콩_표지.png", "04_공_놀이.pdf", "04_공_표지.png")


def ensure_categories():
    """Use a named MySQL lock because Category.name has no unique constraint."""
    from django.db import connection, transaction
    from django.core.management.base import CommandError
    from categories.models import Category
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK('yippee_sample_categories',0)")
        if cursor.fetchone()[0] != 1:
            raise CommandError("다른 카테고리 준비 작업이 실행 중입니다.")
    try:
        with transaction.atomic():
            existing = list(Category.objects.select_for_update().order_by("pk"))
            matches = {name: [row for row in existing if row.name == name] for name in CATEGORY_NAMES}
            if any(len(rows) > 1 for rows in matches.values()):
                raise CommandError("같은 이름의 카테고리가 여러 개입니다. 기존 데이터는 변경하지 않습니다.")
            result = []
            for name in CATEGORY_NAMES:
                # Collation-equivalent variants also require review, not a new row.
                if Category.objects.filter(name=name).count() != len(matches[name]):
                    raise CommandError("동일하게 비교되는 다른 카테고리 이름을 먼저 확인해 주세요.")
                row = matches[name][0] if matches[name] else Category.objects.create(name=name)
                result.append({"id": row.pk, "name": row.name, "created": not bool(matches[name])})
            return result
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK('yippee_sample_categories')")


def file_inventory():
    from scripts.run_mysql_rehearsal import digest
    root = ROOT / "private_uploads"
    return {str(path.relative_to(root)): {"bytes": path.stat().st_size, "sha256": digest(path.read_bytes())}
            for path in sorted(root.rglob("*")) if path.is_file()}


def sample_files():
    from django.core.files import File
    from activities.validators import validate_pdf, validate_cover
    result = []
    for name in FILES:
        path = ROOT / "sample_activities" / name
        item = {"name": name, "exists": path.is_file()}
        if path.is_file():
            with path.open("rb") as stream:
                (validate_pdf if name.endswith(".pdf") else validate_cover)(File(stream, name=name))
            item["validated"] = True
        result.append(item)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-categories", action="store_true")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.db import connection
    from scripts.prepare_activity_deploy import config, state, extra_source_info, guard_source, require, plan
    from scripts.run_mysql_rehearsal import BIN, digest
    before, inventory = state(), file_inventory()
    require((len(before["tables"]), len(before["migrations"])) == (22, 25) and plan() == [], "예상한 DB/migration 상태와 다릅니다.")
    require(before["tables"]["activities"]["count"] == 0 and before["tables"]["activity_categories"]["count"] == 0,
            "기존 활동지가 있습니다. 덮어쓰지 않고 중단합니다.")
    report = {"before": before, "source": extra_source_info(), "sample_files": sample_files(),
              "private_files_before": inventory, "activities_registered": [], "admin_login_tested": False}
    if not args.prepare_categories:
        print(json.dumps({"source": report["source"], "sample_files": report["sample_files"],
                          "private_file_count": len(inventory)}, ensure_ascii=True, indent=2))
        return
    directory = ROOT / ".mysql-rehearsal" / ("sample-registration-" + uuid.uuid4().hex[:12])
    directory.mkdir(exist_ok=False)
    user = subprocess.check_output(["whoami"], text=True).strip()
    subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    print("ARTIFACTS=" + str(directory), flush=True)
    report["success"] = False
    try:
        c = config()
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        client = directory / "source-client.cnf"
        client.write_text("[client]\n" + "\n".join(key + "=" + option(c[key.upper()]) for key in ("host", "port", "user", "password")) + "\n", encoding="utf-8")
        backup = directory / "yippee_club_db.sql"
        result = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(client), "--protocol=TCP",
            "--single-transaction", "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF",
            "--skip-add-drop-table", "--skip-add-locks", "--skip-disable-keys", "--hex-blob",
            "--default-character-set=utf8mb4", "--result-file=" + str(backup), c["NAME"]], capture_output=True)
        require(result.returncode == 0 and backup.stat().st_size > 0, "백업에 실패했습니다. DB는 변경하지 않았습니다.")
        report["backup"] = {"path": str(backup), "bytes": backup.stat().st_size, "sha256": digest(backup.read_bytes())}
        require(state() == before and file_inventory() == inventory, "준비 중 DB 또는 파일이 변경되어 중단합니다.")
        with connection.execute_wrapper(guard_source):
            report["categories"] = ensure_categories()
        after = state()
        require(after["migrations"] == before["migrations"] and after["foreign_keys"] == before["foreign_keys"], "Migration/FK changed unexpectedly")
        require(set(after["tables"]) == set(before["tables"]), "Table set changed unexpectedly")
        for name, old in before["tables"].items():
            new = after["tables"][name]
            if name == "categories":
                import re
                require(new["columns"] == old["columns"] and re.sub(r" AUTO_INCREMENT=\d+", "", new["schema"]) == re.sub(r" AUTO_INCREMENT=\d+", "", old["schema"]), "Category structure changed")
                require(set(old["row_hashes"]) <= set(new["row_hashes"]) and
                        new["count"] == old["count"] + sum(row["created"] for row in report["categories"]), "Category data changed unexpectedly")
            else:
                require(new == old, "Existing table changed unexpectedly: " + name)
        require(file_inventory() == inventory, "Private file inventory changed")
        report.update(success=True, after=after, private_files_preserved=True)
        print(json.dumps({"categories": report["categories"], "activities_registered": 0,
                          "private_files_preserved": len(inventory), "tables": len(after["tables"]),
                          "migrations": len(after["migrations"])}, ensure_ascii=True, indent=2))
    finally:
        (directory / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("REPORT=" + str(directory / "report.json"), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"))
        sys.exit(1)
