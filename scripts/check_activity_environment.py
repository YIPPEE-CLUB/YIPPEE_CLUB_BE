"""Read-only development Admin/API/schema checks plus a temporary storage probe.

Never creates users, categories, sessions or activities in the development DB.
Admin form rendering uses an unsaved permission principal, not a real login.
"""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.prepare_activity_deploy import guard_source, require, extra_source_info, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    require(output.parent.parent == (ROOT / ".mysql-rehearsal").resolve() and
            output.parent.name.startswith(("activity-deploy-", "sample-registration-")) and not output.exists(), "Output path rejected")
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings
    from django.contrib import admin
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import AnonymousUser
    from django.core.exceptions import PermissionDenied
    from django.core.management import call_command
    from django.db import connection
    from django.test import RequestFactory
    from django.urls import resolve, Resolver404
    from activities.models import Activity
    from activities.admin import ActivityForm
    from activities.views import ActivityListView, ActivityDetailView, ActivityFileView

    before = state()
    info = extra_source_info()
    checks = {"source": info, "actual_admin_login_tested": False, "development_test_rows_created": False}
    with connection.execute_wrapper(guard_source):
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("SELECT CONSTRAINT_NAME,ENFORCED FROM information_schema.TABLE_CONSTRAINTS "
                           "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='activities' AND CONSTRAINT_TYPE='CHECK'")
            constraints = dict(cursor.fetchall())
            require(all(constraints.get(name) == "YES" for name in (
                "activity_price_zero", "activity_age_range", "activity_duration_range", "activity_difficulty")), "Activity CHECK constraints missing or not enforced")
            checks["enforced_checks"] = constraints
        require(Activity in admin.site._registry, "Activity Admin menu not registered")
        model_admin = admin.site._registry[Activity]
        factory = RequestFactory()
        request = factory.get("/admin/activities/activity/add/", HTTP_HOST="localhost")
        request.user = AnonymousUser()
        request.session = {}
        require(not admin.site.has_permission(request) and not model_admin.has_add_permission(request), "Anonymous Admin access allowed")
        request.user = SimpleNamespace(is_staff=False, is_active=True, is_superuser=False,
                                       has_perm=lambda *args: False)
        require(not admin.site.has_permission(request) and not model_admin.has_add_permission(request), "Member Admin access allowed")
        try:
            model_admin.add_view(request)
        except PermissionDenied:
            pass
        else:
            raise RuntimeError("Member add form did not reject access")
        request.user = get_user_model()(is_staff=True, is_active=True, is_superuser=True)
        require(admin.site.has_permission(request) and model_admin.has_add_permission(request), "Admin principal lacks permission")
        apps = admin.site.get_app_list(request)
        require(any(m["object_name"] == "Activity" for app in apps for m in app["models"]), "Activity missing from Admin app list")
        response = model_admin.add_view(request)
        response.render()
        require(response.status_code == 200, "Activity add form failed to render")
        form = response.context_data["adminform"].form
        required = {"title", "description", "age_min_months", "age_max_months", "difficulty",
                    "duration_min", "duration_max", "categories", "pdf", "image", "is_public"}
        require(required <= form.fields.keys(), "Activity form fields missing")
        require("price" not in form.fields and "price_in_won" in model_admin.readonly_fields and form.instance.price == 0, "Price is not fixed at zero")
        require(form.fields["categories"].required, "Categories must be selected")
        require(form.fields["categories"].queryset.count() == len(info["categories"]), "Category options mismatch")
        labels = {"age_min_months": "최소 개월 수", "age_max_months": "최대 개월 수",
                  "duration_min": "최소 소요 시간(분)", "duration_max": "최대 소요 시간(분)"}
        require(all(form.fields[name].label == label for name, label in labels.items()), "Activity labels changed unexpectedly")
        require(model_admin.price_in_won.short_description == "가격(원)", "Price label is incorrect")
        checks["admin"] = {"activity_menu": True, "anonymous_and_member_denied": True,
                           "unsaved_admin_principal_add_form_http_status": response.status_code,
                           "fields": sorted(form.fields), "price_readonly_zero": True,
                           "labels": labels, "price_label": "가격(원)",
                           "categories_required": True, "actual_admin_count": info["active_superusers"],
                           "actual_development_update_not_tested": True}
        response = ActivityListView.as_view()(factory.get("/api/v1/activities"))
        require(response.status_code == 200 and response.data["count"] == 0, "Public activity list is not empty")
        checks["public_list"] = {"status": response.status_code, "count": response.data["count"]}
        missing = factory.get("/api/v1/activities/999999999")
        require(ActivityDetailView.as_view()(missing, activity_id=999999999).status_code == 404, "Missing activity detail was not blocked")
        for kind in ("pdf", "image"):
            require(ActivityFileView.as_view()(factory.get("/api/v1/activities/999999999/files/" + kind),
                    activity_id=999999999, kind=kind).status_code == 404, "Missing activity file was not blocked")
        checks["missing_detail_pdf_image"] = 404
        logs = StringIO()
        with redirect_stdout(logs), redirect_stderr(logs):
            call_command("check", databases=["default"], stdout=logs, stderr=logs)
            call_command("makemigrations", check=True, dry_run=True, stdout=logs, stderr=logs)
            call_command("showmigrations", "activities", stdout=logs, stderr=logs)
        checks["django_checks"] = logs.getvalue()

    storage = Activity._meta.get_field("pdf").storage
    root = Path(settings.ACTIVITY_PRIVATE_ROOT).resolve()
    require(root == (ROOT / "private_uploads").resolve() and root.is_relative_to(ROOT.resolve()), "Unexpected private storage root")
    root.mkdir(exist_ok=True)
    directory = root / "activities"
    directory.mkdir(exist_ok=True)
    require(directory.resolve().parent == root, "Private storage path escaped root")
    with tempfile.NamedTemporaryFile(prefix=".activity-write-probe-", dir=directory, delete=True) as probe:
        probe.write(b"YIPPEE temporary storage permission probe")
        probe.flush()
        probe.seek(0)
        require(probe.read() == b"YIPPEE temporary storage permission probe", "Private storage read/write probe failed")
    try:
        storage.url("activities/not-a-real-file.pdf")
    except ValueError:
        pass
    else:
        raise RuntimeError("Storage exposes a direct public URL")
    for path in ("/private_uploads/activities/not-a-real-file.pdf", "/media/activities/not-a-real-file.pdf"):
        try:
            resolve(path)
        except Resolver404:
            pass
        else:
            raise RuntimeError("A direct media URL resolves unexpectedly")
    require(settings.ACTIVITY_PDF_MAX_BYTES == 20 * 1024 * 1024 and
            settings.ACTIVITY_IMAGE_MAX_BYTES == 5 * 1024 * 1024, "Upload limits changed")
    checks["storage"] = {"root": str(root), "upload_directory": str(directory), "read_write_probe": True,
                         "probe_removed": not Path(probe.name).exists(), "direct_url_blocked": True,
                         "pdf_max_bytes": settings.ACTIVITY_PDF_MAX_BYTES,
                         "image_max_bytes": settings.ACTIVITY_IMAGE_MAX_BYTES}
    require(state() == before, "Environment checks changed development data/schema")
    checks["development_unchanged"] = True
    output.write_text(json.dumps(checks, indent=2, default=str), encoding="utf-8")
    print(json.dumps(checks, indent=2, ensure_ascii=True, default=str))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("STOP: " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + "; sensitive details suppressed"))
        sys.exit(1)
