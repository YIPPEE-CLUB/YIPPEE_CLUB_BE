"""Back up, import private, verify, and publish exactly four supplied activities."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import re
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify_api(root, ids, public):
    from django.test import RequestFactory
    from activities.sample_import import SAMPLES, preflight
    from activities.views import ActivityListView, ActivityDetailView, ActivityFileView
    from scripts.prepare_activity_deploy import require
    import hashlib
    factory = RequestFactory(HTTP_HOST="localhost")
    expected = preflight(root)
    response = ActivityListView.as_view()(factory.get("/api/v1/activities"))
    require(response.status_code == 200 and response.data["count"] == (4 if public else 0), "Unexpected API list")
    result = {"public": public, "list_status": 200, "count": response.data["count"], "activities": []}
    for pk, sample in zip(ids, SAMPLES):
        response = ActivityDetailView.as_view()(factory.get(f"/api/v1/activities/{pk}"), activity_id=pk)
        require(response.status_code == (200 if public else 404), "Unexpected API detail access")
        if public:
            require(response.data["price"] == 0 and response.data["age_min_months"] == 60 and
                    response.data["age_max_months"] == 65 and response.data["title"] == sample[0], "Unexpected detail metadata")
        entry = {"id": pk, "detail": response.status_code}
        for kind, filename in (("pdf", sample[4]), ("image", sample[5])):
            response = ActivityFileView.as_view()(factory.get(f"/api/v1/activities/{pk}/files/{kind}"), activity_id=pk, kind=kind)
            require(response.status_code == (200 if public else 404), "Unexpected file access")
            entry[kind] = response.status_code
            if public:
                try:
                    digest = hashlib.sha256()
                    for chunk in response.streaming_content:
                        digest.update(chunk)
                    require(digest.hexdigest() == expected[filename]["sha256"], "API file differs from supplied bytes")
                    require(response["Cache-Control"] == "private, no-store" and response["X-Content-Type-Options"] == "nosniff", "File security headers missing")
                    entry[kind + "_sha256"] = digest.hexdigest()
                finally:
                    # RequestFactory has no request lifecycle; close the stream only.
                    response.file_to_stream.close()
        result["activities"].append(entry)
    if public:
        from activities.sample_import import sample_categories
        queries = [({"q": "징검다리"}, 1), ({"q": "숫자 놀이"}, 1), ({"q": "콩 놀이"}, 1),
                   ({"q": "공 놀이"}, 1), ({"age_years": 5}, 4), ({"age_years": 4}, 0),
                   ({"difficulty": "easy"}, 1), ({"difficulty": "hard"}, 3),
                   ({"duration": "15-15"}, 1), ({"price_min": 1}, 0)]
        queries += [({"category": c.pk}, 4) for c in sample_categories()]
        for query, count in queries:
            response = ActivityListView.as_view()(factory.get("/api/v1/activities", query))
            require(response.status_code == 200 and response.data["count"] == count, "API filter failed")
        result["filter_checks"] = len(queries)
    response = ActivityDetailView.as_view()(factory.get("/api/v1/activities/999999999"), activity_id=999999999)
    require(response.status_code == 404, "Missing ID did not return 404")
    result["missing_id"] = 404
    return result


def verify_admin_rows(ids):
    """Read-only rendering with an unsaved principal; not a real admin login."""
    from django.contrib import admin
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory
    from activities.models import Activity
    from scripts.prepare_activity_deploy import require
    model_admin = admin.site._registry[Activity]
    factory = RequestFactory()
    principal = get_user_model()(is_active=True, is_staff=True, is_superuser=True)
    statuses = {}
    for pk in [None, *ids]:
        path = "/admin/activities/activity/" + ("add/" if pk is None else f"{pk}/change/")
        request = factory.get(path, HTTP_HOST="localhost")
        request.user, request.session = principal, {}
        response = model_admin.add_view(request) if pk is None else model_admin.change_view(request, str(pk))
        response.render()
        require(response.status_code == 200, "Admin form render failed")
        form = response.context_data["adminform"].form
        require(form.fields["age_min_months"].label == "최소 개월 수" and
                form.fields["age_max_months"].label == "최대 개월 수" and "price" not in form.fields, "Admin labels/price changed")
        statuses["add" if pk is None else str(pk)] = 200
    return {"read_only_form_statuses": statuses, "actual_login_tested": False}


def verify_http(root, ids, public):
    """Real GET requests through Django middleware on a temporary loopback server."""
    import hashlib
    import threading
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    from django.core.wsgi import get_wsgi_application
    from django.db import connection, connections
    from activities.sample_import import SAMPLES, preflight
    from scripts.prepare_activity_deploy import guard_source, require
    originals = preflight(root)
    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass
    server = make_server("127.0.0.1", 0, get_wsgi_application(), handler_class=QuietHandler)
    base = "http://127.0.0.1:" + str(server.server_port)
    def serve():
        try:
            with connection.execute_wrapper(guard_source):
                server.serve_forever(poll_interval=0.1)
        finally:
            connections.close_all()
    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    result = {"base_url": base, "public": public, "files": [], "server_stopped": False}
    try:
        with urlopen(base + "/api/v1/activities", timeout=15) as response:
            listing = json.load(response)
            require(response.status == 200 and listing["count"] == (4 if public else 0), "HTTP list mismatch")
            result["count"] = listing["count"]
        for pk, sample in zip(ids, SAMPLES):
            routes = [(f"/api/v1/activities/{pk}", None)]
            routes += [(f"/api/v1/activities/{pk}/files/{kind}", filename) for kind, filename in (("pdf", sample[4]), ("image", sample[5]))]
            for route, filename in routes:
                try:
                    with urlopen(base + route, timeout=15) as response:
                        require(public and response.status == 200, "Private HTTP route exposed")
                        if filename:
                            h = hashlib.sha256()
                            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                                h.update(chunk)
                            require(h.hexdigest() == originals[filename]["sha256"], "HTTP download bytes differ")
                            result["files"].append({"source": filename, "status": 200, "sha256": h.hexdigest()})
                        else:
                            detail = json.load(response)
                            require(detail["id"] == pk and detail["title"] == sample[0] and detail["price"] == 0, "HTTP detail mismatch")
                except HTTPError as error:
                    require(not public and error.code == 404, "Unexpected HTTP error")
                    error.close()
        result["detail_statuses"] = [200 if public else 404] * 4
        result["file_statuses"] = [200 if public else 404] * 8
    finally:
        server.shutdown()
        worker.join(timeout=10)
        server.server_close()
        result["server_stopped"] = not worker.is_alive()
    require(result["server_stopped"], "Temporary HTTP server did not stop")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", help="Resume verification of this attempt's exact private batch, without uploading again")
    args = parser.parse_args()
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.db import connection, transaction
    from activities.models import Activity
    from activities.sample_import import register_private, verify_rows, preflight
    from scripts.prepare_activity_deploy import config, state, extra_source_info, guard_source, require, plan
    from scripts.prepare_sample_activities import file_inventory
    from scripts.run_mysql_rehearsal import BIN, digest
    root = ROOT / "sample_activities"
    originals = preflight(root)
    if args.resume:
        run = Path(args.resume).resolve()
        require(run.parent == (ROOT / ".mysql-rehearsal").resolve() and run.name.startswith("sample-import-"), "Resume path rejected")
        report = json.loads((run / "report.json").read_text(encoding="utf-8"))
        require(not report["success"] and len(report.get("ids", [])) == 4, "No interrupted private batch to resume")
        require(report["originals"] == originals, "Supplied files changed since import")
        backup = Path(report["backup"]["path"]).resolve()
        require(backup.parent == run and digest(backup.read_bytes()) == report["backup"]["sha256"], "Backup changed")
        before, inventory = report["before"], report["private_files_before"]
        # Reject changed metadata, bytes, unrelated DB data, or extra files before publishing.
        verify_rows(root, report["ids"], public=False, expected_sources=originals)
        preserved(before, state(), inventory)
        report_path = run / ("resume-" + uuid.uuid4().hex[:12] + ".json")
    else:
        before, inventory = state(), file_inventory()
        require(before["tables"]["activities"]["count"] == 0 and before["tables"]["activity_categories"]["count"] == 0, "Existing activities found; refusing duplicate import")
        run = ROOT / ".mysql-rehearsal" / ("sample-import-" + uuid.uuid4().hex[:12])
        run.mkdir(exist_ok=False)
        user = subprocess.check_output(["whoami"], text=True).strip()
        subprocess.run(["icacls", str(run), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F",
                        "*S-1-5-18:(OI)(CI)F"], capture_output=True, check=True)
        report = {"success": False, "before": before, "source": extra_source_info(), "originals": originals,
                  "private_files_before": inventory, "actual_admin_login_tested": False}
        report_path = run / "report.json"
    require((len(before["tables"]), len(before["migrations"])) == (22, 25) and plan() == [], "Unexpected DB/migration state")
    print("ARTIFACTS=" + str(run), flush=True)
    def journal(event):
        with (run / "journal.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    try:
        c = config()
        def option(value):
            return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'
        if not args.resume:
            client = run / "source-client.cnf"
            client.write_text("[client]\n" + "\n".join(key + "=" + option(c[key.upper()]) for key in ("host", "port", "user", "password")) + "\n", encoding="utf-8")
            backup = run / "yippee_club_db.sql"
            completed = subprocess.run([str(BIN / "mysqldump.exe"), "--defaults-file=" + str(client), "--protocol=TCP",
                "--single-transaction", "--skip-lock-tables", "--no-tablespaces", "--set-gtid-purged=OFF",
                "--skip-add-drop-table", "--skip-add-locks", "--skip-disable-keys", "--hex-blob",
                "--default-character-set=utf8mb4", "--result-file=" + str(backup), c["NAME"]], capture_output=True)
            require(completed.returncode == 0 and backup.stat().st_size > 0, "Fresh backup failed")
            report["backup"] = {"path": str(backup), "bytes": backup.stat().st_size, "sha256": digest(backup.read_bytes())}
            require(state() == before and file_inventory() == inventory and preflight(root) == originals, "Source changed during backup")
        with connection.execute_wrapper(guard_source):
            ids = report["ids"] if args.resume else register_private(root, journal)
            report["ids"] = ids
            report["private_rows"] = verify_rows(root, ids, public=False)
            report["private_api"] = verify_api(root, ids, False)
            report["private_http"] = verify_http(root, ids, False)
            print("Private import, metadata, source bytes and blocked API/file access: PASS", flush=True)
            # Inspect exact private metadata again under row locks before publishing.
            with transaction.atomic():
                list(Activity.objects.select_for_update().filter(pk__in=ids))
                verify_rows(root, ids, public=False, expected_sources=originals)
                require(Activity.objects.filter(pk__in=ids, is_public=False).update(is_public=True) == 4, "Publish target changed")
            journal({"event": "published", "ids": ids})
            try:
                report["public_rows"] = verify_rows(root, ids, public=True)
                report["public_api"] = verify_api(root, ids, True)
                report["public_http"] = verify_http(root, ids, True)
                report["admin"] = verify_admin_rows(ids)
            except BaseException:
                Activity.objects.filter(pk__in=ids).update(is_public=False)
                journal({"event": "reverted_private_after_public_check_failure", "ids": ids})
                raise
        after = state()
        preserved(before, after, inventory)
        require(preflight(root) == originals, "Input files changed")
        report.update(success=True, after=after, original_files_preserved=True, source_files_preserved=True)
        print(json.dumps({"activities": report["public_rows"], "list_count": report["public_api"]["count"],
                          "file_byte_checks": 8, "filter_checks": report["public_api"]["filter_checks"],
                          "original_private_files_preserved": len(inventory)}, ensure_ascii=True, indent=2))
    finally:
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        print("REPORT=" + str(report_path), flush=True)


def preserved(before, after, inventory):
    from scripts.prepare_activity_deploy import require
    from scripts.prepare_sample_activities import file_inventory
    require(after["migrations"] == before["migrations"] and after["foreign_keys"] == before["foreign_keys"] and
            set(after["tables"]) == set(before["tables"]), "Existing migrations/FKs/tables changed")
    for name, old in before["tables"].items():
        new = after["tables"][name]
        if name in ("activities", "activity_categories"):
            require(new["columns"] == old["columns"] and re.sub(r" AUTO_INCREMENT=\d+", "", new["schema"]) == re.sub(r" AUTO_INCREMENT=\d+", "", old["schema"]), "Activity schema changed")
            require(set(old["row_hashes"]) <= set(new["row_hashes"]) and new["count"] == (4 if name == "activities" else 8), "Unexpected imported count")
        else:
            require(new == old, "Original table data/schema changed: " + name)
    final_files = file_inventory()
    require(all(final_files.get(name) == value for name, value in inventory.items()) and
            len(final_files) == len(inventory) + 8, "Original private files changed or extra files found")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"))
        sys.exit(1)
