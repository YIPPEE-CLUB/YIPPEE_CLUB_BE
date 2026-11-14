"""Real HTTP login/JWT/favorites checks only on the dedicated HTTP restore copy."""
import json
import secrets
import threading
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server


def run():
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.wsgi import get_wsgi_application
    from django.db import connection, connections
    from django.test import override_settings
    from activities.models import Activity
    from activities.serializers import ActivitySerializer
    from favorites.models import Favorite
    from config.user_model_rehearsal import guard_rehearsal_sql
    if (settings.SETTINGS_MODULE != "config.favorites_deploy_rehearsal" or
            connection.settings_dict["NAME"] != "test_yippee_migration_legacy"):
        raise RuntimeError("HTTP validation requires the fresh isolated HTTP copy")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@server_id,@@port,DATABASE(),@@server_uuid")
        identity = cursor.fetchone()
    if identity[:3] != (9133307, 33307, "test_yippee_migration_legacy"):
        raise RuntimeError("HTTP database identity rejected")
    row = Activity.objects.filter(is_public=True).order_by("id").first()
    if row is None or row.price != 0 or Favorite.objects.exists():
        raise RuntimeError("Unexpected HTTP fixture baseline")
    # Random credentials exist only in this isolated process and are never logged.
    password = secrets.token_urlsafe(32)
    suffix = secrets.token_hex(12)
    a = get_user_model().objects.create_user("http-a-" + suffix + "@example.com", password)
    b = get_user_model().objects.create_user("http-b-" + suffix + "@example.com", password)
    hidden = Activity(title="Isolated HTTP hidden fixture", description="Isolated only", age_min_months=60,
        age_max_months=65, difficulty="easy", duration_min=5, duration_max=5, price=0, is_public=False,
        pdf=row.pdf.name, image=row.image.name)
    Activity.objects.bulk_create([hidden])
    hidden = Activity.objects.get(title="Isolated HTTP hidden fixture")
    checks = []
    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass
    with override_settings(ALLOWED_HOSTS=["127.0.0.1"]):
        application = get_wsgi_application()
        def buffered_application(environ, start_response):
            # Consume the controlled request payload even when JWT rejection
            # happens before DRF parses it. Unread body bytes can cause Windows
            # to reset a closing single-request wsgiref socket instead of 401.
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length:
                environ["wsgi.input"] = BytesIO(environ["wsgi.input"].read(length))
            return application(environ, start_response)
        server = make_server("127.0.0.1", 0, buffered_application, handler_class=QuietHandler)
        def serve():
            try:
                with connection.execute_wrapper(guard_rehearsal_sql):
                    server.serve_forever(poll_interval=0.1)
            finally:
                connections.close_all()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        def request(method, path, expected, body=None, token=None):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            req = Request("http://127.0.0.1:" + str(server.server_port) + "/api/v1" + path,
                data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
            try:
                response = urlopen(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                payload = response.read()
                status = response.status
            if status != expected or (expected == 204 and payload):
                raise RuntimeError(f"HTTP contract failed: {method} {path}, expected {expected}, got {status}")
            result = json.loads(payload) if payload else None
            if expected >= 400 and set(result) != {"code", "message", "details", "request_id"}:
                raise RuntimeError("Common HTTP error contract changed")
            checks.append({"method": method, "path": path, "status": status})
            return result

        def listing(token, ids):
            data = request("GET", "/favorites", 200, token=token)
            if set(data) != {"results"} or [r["id"] for r in data["results"]] != ids:
                raise RuntimeError("HTTP list scope/JSON contract mismatch")
            for item in data["results"]:
                if set(item) != set(ActivitySerializer.Meta.fields) or item["price"] != 0:
                    raise RuntimeError("HTTP activity item contract mismatch")

        try:
            token_a = request("POST", "/auth/login", 200, {"email": a.email, "password": password})["access_token"]
            token_b = request("POST", "/auth/login", 200, {"email": b.email, "password": password})["access_token"]
            for token in (None, "not-a-valid-jwt"):
                request("GET", "/favorites", 401, token=token)
                request("POST", "/favorites", 401, {"activity_id": row.pk}, token)
                request("DELETE", f"/favorites/{row.pk}", 401, token=token)
            added = request("POST", "/favorites", 201, {"activity_id": row.pk}, token_a)
            if added != {"activity_id": row.pk, "message": "처리되었습니다."}:
                raise RuntimeError("HTTP create JSON contract mismatch")
            listing(token_a, [row.pk])
            listing(token_b, [])
            request("POST", "/favorites", 409, {"activity_id": row.pk}, token_a)
            request("DELETE", f"/favorites/{row.pk}", 404, token=token_b)
            listing(token_a, [row.pk])
            request("POST", "/favorites", 201, {"activity_id": row.pk}, token_b)
            request("POST", "/favorites", 400, {"activity_id": row.pk, "user_id": b.pk}, token_a)
            request("DELETE", f"/favorites/{row.pk}", 204, token=token_a)
            listing(token_a, [])
            listing(token_b, [row.pk])
            request("DELETE", f"/favorites/{row.pk}", 404, token=token_a)
            request("POST", "/favorites", 400, {"activity_id": hidden.pk}, token_a)
            request("GET", f"/activities/{hidden.pk}", 404)
            request("GET", f"/activities/{hidden.pk}/files/pdf", 404)
            Favorite.objects.create(user=a, activity=hidden)
            listing(token_a, [])
            request("DELETE", f"/favorites/{hidden.pk}", 204, token=token_a)
            request("POST", "/favorites", 400, {"activity_id": 999999999}, token_a)
            request("DELETE", f"/favorites/{row.pk}", 204, token=token_b)
            listing(token_b, [])
            if Favorite.objects.exists():
                raise RuntimeError("HTTP fixture favorites were not removed")
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
        if thread.is_alive():
            raise RuntimeError("HTTP server did not stop")
    print(json.dumps({"success": True, "transport": "TCP/WSGI", "database": "fresh-isolated-http-copy",
                      "passed": len(checks), "checks": checks, "http_server_stopped": True,
                      "development_accounts_created": False, "credentials_printed": False}))
