"""Read-only before/after proof that favorite development did not touch source DB/files."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def capture():
    from scripts.prepare_activity_deploy import state, extra_source_info
    from scripts.prepare_sample_activities import file_inventory
    from scripts.run_mysql_rehearsal import digest
    from activities.sample_import import preflight
    from activities.views import ActivityListView
    from django.test import RequestFactory
    response = ActivityListView.as_view()(RequestFactory(HTTP_HOST="localhost").get("/api/v1/activities"))
    if response.status_code != 200 or response.data["count"] != 4:
        raise RuntimeError("Expected four published source activities")
    return {"database": state(), "identity": extra_source_info(), "private_files": file_inventory(),
            "sample_files": preflight(ROOT / "sample_activities"), "activity_api": response.data,
            "migration_hashes": {str(p.relative_to(ROOT)): digest(p.read_bytes())
                for p in ROOT.glob("*/migrations/*.py")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--evidence")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    actual = capture()
    if args.phase == "before":
        directory = ROOT / ".mysql-rehearsal" / ("favorites-validation-" + uuid.uuid4().hex[:12])
        directory.mkdir(exist_ok=False)
        user = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                        "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
    else:
        directory = Path(args.evidence).resolve()
        if directory.parent != (ROOT / ".mysql-rehearsal").resolve() or not directory.name.startswith("favorites-validation-"):
            raise RuntimeError("Evidence path rejected")
        before = json.loads((directory / "before.json").read_text(encoding="utf-8"))
        for key, value in before.items():
            if key == "migration_hashes":
                if any(actual[key].get(path) != sha for path, sha in value.items()):
                    raise RuntimeError("An existing migration changed")
            elif actual[key] != value:
                raise RuntimeError("Development source changed: " + key)
    target = directory / (args.phase + ".json")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(actual, stream, indent=2, default=str)
    print("EVIDENCE=" + str(directory))
    print("PASS: source tables=%s migrations=%s activities=4 private_files=%s" % (
        len(actual["database"]["tables"]), len(actual["database"]["migrations"]), len(actual["private_files"])))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; details suppressed"))
        sys.exit(1)
