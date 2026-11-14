"""Real TCP HTTP auth checks against the restored, upgraded isolated schema only."""
import json
import re
import secrets
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from wsgiref.simple_server import WSGIRequestHandler, make_server

from django.conf import settings
from django.core import mail
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.test import override_settings


def run():
    if (not getattr(settings, "IS_USER_MODEL_REHEARSAL", False) or
            connection.settings_dict["NAME"] != "test_yippee_migration_fresh"):
        raise RuntimeError("HTTP checks require the isolated restored schema")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@server_id,@@port,DATABASE()")
        if cursor.fetchone() != (9133307, 33307, "test_yippee_migration_fresh"):
            raise RuntimeError("HTTP test database identity rejected")

    class QuietHandler(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    checks = []
    with override_settings(ALLOWED_HOSTS=["127.0.0.1"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
        server = make_server("127.0.0.1", 0, get_wsgi_application(), handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, path, body=None, token=None, expected=200):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            req = Request("http://127.0.0.1:" + str(server.server_port) + "/api/v1" + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers=headers, method=method)
            try:
                response = urlopen(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                result = json.loads(response.read())
            if status != expected:
                raise RuntimeError(f"HTTP {method} {path}: expected {expected}, got {status}")
            checks.append({"method": method, "path": path, "status": status})
            return result

        try:
            email = "http-" + secrets.token_hex(8) + "@example.com"
            password = "HttpSecurePwd!839274"
            request("POST", "/auth/signup", {"identifier": email, "password": password,
                                               "agreements": {}, "verification_token": "not-verified"}, expected=400)
            sent = request("POST", "/auth/verification/send", {"identifier": email, "purpose": "signup"})
            code = re.search(r"인증번호: ([0-9]{6})", mail.outbox[-1].body).group(1)
            proof = request("POST", "/auth/verification/confirm", {"verification_id": sent["verification_id"], "code": code})
            signup_body = {"identifier": email, "password": password, "agreements": {},
                           "verification_token": proof["verification_token"]}
            created = request("POST", "/auth/signup", signup_body, expected=201)
            request("POST", "/auth/signup", signup_body, expected=409)
            request("GET", "/users/me", expected=401)
            profile = request("GET", "/users/me", token=created["access_token"])
            if set(profile) != {"id", "email", "phone", "name"} or profile["id"] != created["user_id"]:
                raise RuntimeError("Unexpected profile JSON contract")
            request("PATCH", "/users/me", {"name": "HTTP profile", "nickname": "HTTP"}, token=created["access_token"])
            request("PATCH", "/users/me", {"is_staff": True}, token=created["access_token"], expected=400)
            request("POST", "/auth/login", {"email": email, "password": "wrong"}, expected=400)
            logged = request("POST", "/auth/login", {"email": email, "password": password})
            request("POST", "/auth/token/refresh", {"refresh_token": logged["refresh_token"]})
            request("POST", "/auth/logout", {"refresh_token": logged["refresh_token"]})
            request("POST", "/auth/token/refresh", {"refresh_token": logged["refresh_token"]}, expected=400)
            next_password = "HttpChangedPwd!839274"
            request("PATCH", "/users/me/password", {"current_password": password, "new_password": next_password},
                    token=created["access_token"])
            request("GET", "/users/me", token=created["access_token"], expected=401)
            request("POST", "/auth/password/reset-request", {"email": email})
            reset_token = mail.outbox[-1].body.split(": ", 1)[1]
            reset_body = {"reset_token": reset_token, "new_password": "HttpResetPwd!839274"}
            request("POST", "/auth/password/reset-confirm", reset_body)
            request("POST", "/auth/password/reset-confirm", reset_body, expected=400)
            request("POST", "/auth/login", {"email": email, "password": reset_body["new_password"]})
            print(json.dumps({"http_transport": "TCP/WSGI", "database": "isolated-restored-upgrade",
                              "passed": len(checks), "checks": checks}))
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
