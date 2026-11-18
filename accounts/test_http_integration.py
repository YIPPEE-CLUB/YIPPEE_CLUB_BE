"""Real loopback HTTP flows; enabled only on the isolated MySQL rehearsal.

HTTP_AUDIT_DIR optionally retains metadata only (never bodies or credentials).
"""
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest import skipUnless
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files import File
from django.db.backends.signals import connection_created
from django.test import LiveServerTestCase, override_settings

from activities.models import Activity
from activities.tests import image, pdf
from categories.models import Category


ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


@skipUnless(ISOLATED, "Real HTTP data flows require isolated MySQL.")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   PASSWORD_RESET_FRONTEND_URL="https://frontend.example.com/password/reset",
                   AUTH_IP_LIMIT=1000, AUTH_EMAIL_LIMIT=1000)
class CoreHTTPIntegrationTests(LiveServerTestCase):
    databases = {"default"} if ISOLATED else set()
    host = "127.0.0.1"

    @classmethod
    def setUpClass(cls):
        # Django connections are thread local. Guard HTTP worker SQL too.
        from config.user_model_rehearsal import guard_rehearsal_sql

        def guard_connection(sender, connection, **kwargs):
            if guard_rehearsal_sql not in connection.execute_wrappers:
                connection.execute_wrappers.append(guard_rehearsal_sql)

        cls.guard_connection = staticmethod(guard_connection)
        connection_created.connect(guard_connection, weak=False)
        cls.addClassCleanup(connection_created.disconnect, guard_connection)
        super().setUpClass()

    def setUp(self):
        self.requests = []
        self.token = None
        self.opener = build_opener(ProxyHandler({}))
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(ACTIVITY_PRIVATE_ROOT=directory.name)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(self.save_audit)
        self.category = Category.objects.create(name="HTTP category")

    def save_audit(self):
        if os.environ.get("HTTP_AUDIT_DIR"):
            path = Path(os.environ["HTTP_AUDIT_DIR"]) / (self._testMethodName + ".json")
            path.write_text(json.dumps(self.requests, indent=2), encoding="utf-8")

    def http(self, method, path, expected=200, body=None, binary=False):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.live_server_url + "/api/v1/" + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            result = raw if binary else (json.loads(raw) if raw and "application/json" in content_type else None)
            self.requests.append({"method": method, "path": path, "expected": expected,
                                  "actual": status, "passed": status == expected,
                                  "content_type": content_type, "bytes": len(raw)})
            self.assertEqual(status, expected, f"{method} {path}: unexpected HTTP status {status}")
            if path.split("/", 1)[0] in {"auth", "users", "children", "favorites", "cart"}:
                directives = {part.strip() for part in response.headers.get("Cache-Control", "").split(",")}
                self.assertTrue({"private", "no-store"} <= directives, path)
            if binary:
                self.assertIn("attachment;", response.headers.get("Content-Disposition", ""))
                self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
                self.assertEqual(response.headers.get("Cache-Control"), "private, no-store")
            elif status == 204:
                self.assertEqual(raw, b"")
            else:
                self.assertIn("application/json", content_type)
                self.assertIsInstance(result, dict)
                if status >= 400:
                    self.assertEqual(set(result), {"code", "message", "details", "request_id"})
            return result

    def keys(self, data, keys):
        self.assertEqual(set(data), set(keys.split()))

    def signup(self, email):
        self.assertFalse(self.http("POST", "auth/identifiers/check", body={"identifier": email})["registered"])
        challenge = self.http("POST", "auth/verification/send", body={"identifier": email, "purpose": "signup"})
        self.keys(challenge, "verification_id expires_in_seconds")
        self.assertEqual(mail.outbox[-1].to, [email])
        code = re.search(r"(?<!\d)\d{6}(?!\d)", mail.outbox[-1].body).group()
        self.http("POST", "auth/verification/confirm", 400,
                  {"verification_id": challenge["verification_id"], "code": "bad"})
        proof = self.http("POST", "auth/verification/confirm", body={
            "verification_id": challenge["verification_id"], "code": code})
        self.keys(proof, "verification_token verified")
        self.assertTrue(proof["verified"])
        account = self.http("POST", "auth/signup", 201, {"identifier": email,
            "verification_token": proof["verification_token"], "password": "HttpPassword!83927", "agreements": {}})
        self.keys(account, "user_id access_token refresh_token")
        self.assertTrue(self.http("POST", "auth/identifiers/check", body={"identifier": email})["registered"])
        return self.login(email, "HttpPassword!83927")

    def login(self, email, password):
        result = self.http("POST", "auth/login", body={"email": email, "password": password})
        self.keys(result, "access_token refresh_token user")
        self.keys(result["user"], "id email phone name nickname")
        self.token = result["access_token"]
        return result

    def profile(self, selected):
        result = self.http("GET", "users/me")
        self.keys(result, "id email phone name nickname active_child_id")
        self.assertEqual(result["active_child_id"], selected)
        return result

    def activity(self, title, public=True):
        row = Activity.objects.create(title=title, description="HTTP fixture", age_min_months=60,
            age_max_months=65, difficulty="easy", duration_min=5, duration_max=10,
            is_public=public, pdf=pdf(), image=image())
        row.categories.add(self.category)
        return row

    def test_auth_children_and_account_lifecycle(self):
        self.http("GET", "users/me", 401)
        self.http("PATCH", "users/me", 401, {"nickname": "Unauthenticated"})
        self.token = "invalid"
        self.http("GET", "users/me", 401)
        self.token = None
        owner = self.signup("http-owner@example.com")
        self.assertEqual(self.profile(None), {**owner["user"], "active_child_id": None})
        self.assertEqual(owner["user"]["nickname"], "")
        refresh = self.http("POST", "auth/token/refresh", body={"refresh_token": owner["refresh_token"]})
        self.keys(refresh, "access_token refresh_token")
        self.token = refresh["access_token"]
        self.profile(None)
        result = self.http("PATCH", "users/me", body={"nickname": "HTTP Nickname"})
        self.keys(result, "id email phone name nickname")
        self.assertEqual(result["nickname"], "HTTP Nickname")
        self.assertEqual(self.profile(None), {**result, "active_child_id": None})
        result = self.http("PATCH", "users/me", body={"name": "HTTP Parent"})
        self.assertEqual(result["name"], "HTTP Parent")
        self.assertEqual(result["nickname"], "HTTP Nickname")
        saved_profile = result
        children = []
        for name in ("A", "B"):
            child = self.http("POST", "children", 201, {"name": name, "birth_date": "2022-05-01",
                                                        "interests": [self.category.pk]})
            self.keys(child, "id name birth_date gender interests")
            self.assertEqual(child["interests"], [self.category.pk])
            children.append(child["id"])
        result = self.http("GET", "children")
        self.keys(result, "results")
        self.assertEqual([r["id"] for r in result["results"]], children)
        self.http("PATCH", f"children/{children[0]}", body={"name": "A updated"})
        child = self.http("GET", f"children/{children[0]}")
        self.assertEqual(child["name"], "A updated")
        self.assertEqual(child["interests"], [self.category.pk])
        for pk in children:
            self.assertEqual(self.http("PUT", "users/me/active-child", body={"child_id": pk}), {"active_child_id": pk})
            self.profile(pk)
        self.opener = build_opener(ProxyHandler({}))
        login = self.login("http-owner@example.com", "HttpPassword!83927")
        self.assertEqual(login["user"], saved_profile)
        self.assertEqual(self.profile(children[1]), {**saved_profile, "active_child_id": children[1]})
        other = self.signup("http-other@example.com")
        self.assertEqual(self.profile(None), {**other["user"], "active_child_id": None})
        self.assertEqual(other["user"]["nickname"], "")
        self.http("PATCH", "users/me", 400, {"id": owner["user"]["id"], "nickname": "Other"})
        self.assertEqual(self.http("GET", "children"), {"results": []})
        for method in ("GET", "PATCH", "DELETE"):
            self.http(method, f"children/{children[1]}", 404, {} if method == "PATCH" else None)
        self.http("PUT", "users/me/active-child", 400, {"child_id": children[1]})
        self.assertNotEqual(owner["user"]["id"], other["user"]["id"])
        self.login("http-owner@example.com", "HttpPassword!83927")
        self.assertEqual(self.profile(children[1])["nickname"], "HTTP Nickname")
        cleared = self.http("PATCH", "users/me", body={"nickname": None})
        self.assertEqual(cleared, {**saved_profile, "nickname": ""})
        self.assertEqual(self.profile(children[1]), {**cleared, "active_child_id": children[1]})
        self.assertEqual(get_user_model().objects.get(pk=owner["user"]["id"]).nickname, "")
        self.http("DELETE", f"children/{children[0]}", 204)
        self.profile(children[1])
        self.http("DELETE", f"children/{children[1]}", 204)
        self.profile(None)
        self.http("PATCH", "users/me/password", 400,
                  {"current_password": "wrong", "new_password": "ChangedHttpPwd!73921"})
        self.http("PATCH", "users/me/password", body={
            "current_password": "HttpPassword!83927", "new_password": "ChangedHttpPwd!73921"})
        self.http("POST", "auth/token/refresh", 400, {"refresh_token": owner["refresh_token"]})
        self.http("POST", "auth/login", 400, {"email": "http-owner@example.com", "password": "HttpPassword!83927"})
        current = self.login("http-owner@example.com", "ChangedHttpPwd!73921")
        self.http("POST", "auth/logout", body={"refresh_token": current["refresh_token"]})
        self.http("POST", "auth/token/refresh", 400, {"refresh_token": current["refresh_token"]})
        self.http("POST", "auth/password/reset-request", body={"email": "http-owner@example.com"})
        url = re.search(r"https://frontend\.example\.com/password/reset#[^\s]+", mail.outbox[-1].body).group()
        token = parse_qs(urlsplit(url).fragment)["reset_token"][0]
        reset = {"reset_token": token, "new_password": "ResetHttpPwd!83928"}
        self.http("POST", "auth/password/reset-confirm", body=reset)
        self.http("POST", "auth/password/reset-confirm", 400, reset)
        self.http("POST", "auth/login", 400, {"email": "http-owner@example.com", "password": "ChangedHttpPwd!73921"})
        self.login("http-owner@example.com", "ResetHttpPwd!83928")
        self.profile(None)

    def test_catalogue_sample_downloads_favorites_and_cart(self):
        # Read supplied samples, writing copies only to isolated storage.
        rows = []
        sources = Path(settings.BASE_DIR) / "sample_activities"
        for index in range(1, 5):
            row = self.activity(f"Sample {index}")
            for kind, suffix in (("pdf", ".pdf"), ("image", ".png")):
                source = next(sources.glob(f"{index:02d}_*{suffix}"))
                with source.open("rb") as stream:
                    getattr(row, kind).save(source.name, File(stream), save=True)
                received = self.http("GET", f"activities/{row.pk}/files/{kind}", binary=True)
                self.assertEqual(hashlib.sha256(received).digest(), hashlib.sha256(source.read_bytes()).digest())
            rows.append(row)
        hidden = self.activity("Hidden", public=False)
        self.assertEqual(self.http("GET", "activity-categories"), {
            "results": [{"id": self.category.pk, "name": self.category.name}]})
        listing = self.http("GET", "activities")
        self.keys(listing, "count next previous results")
        self.assertEqual(listing["count"], 4)
        detail = self.http("GET", f"activities/{rows[0].pk}")
        self.assertEqual(detail["id"], rows[0].pk)
        self.assertEqual(detail["price"], 0)
        for query, count in (({"q": "Sample 1"}, 1), ({"q": "absent"}, 0),
                             ({"category": self.category.pk}, 4), ({"age_years": 5}, 4),
                             ({"age_years": 4}, 0), ({"difficulty": "easy"}, 4),
                             ({"difficulty": "hard"}, 0), ({"duration": "5-10"}, 4),
                             ({"duration": "20-30"}, 0)):
            result = self.http("GET", "activities?" + urlencode(query))
            self.assertEqual(result["count"], count)
            self.assertNotIn(hidden.pk, [r["id"] for r in result["results"]])
        for sort in ("title", "oldest", "latest", "price_asc", "price_desc"):
            result = self.http("GET", "activities?" + urlencode({"sort": sort}))
            expected = rows if sort in ("title", "oldest", "price_asc", "price_desc") else rows[::-1]
            self.assertEqual([r["id"] for r in result["results"]], [r.pk for r in expected])
        first = self.http("GET", "activities?page_size=2&sort=oldest")
        second = self.http("GET", "activities?page_size=2&sort=oldest&page=2")
        self.assertIsNotNone(first["next"])
        self.assertIsNotNone(second["previous"])
        self.assertIsNone(second["next"])
        self.assertEqual([r["id"] for r in first["results"] + second["results"]], [r.pk for r in rows])
        self.http("GET", "activities?difficulty=medium", 400)
        self.http("GET", "activities?page=999", 404)
        for tail in ("", "/files/pdf", "/files/image"):
            self.http("GET", f"activities/{hidden.pk}{tail}", 404)
        self.http("GET", f"activities/{rows[0].pk}/files/unknown", 404)
        for path in ("favorites", "cart"):
            self.http("GET", path, 401)
        owner = self.signup("http-saved@example.com")
        pk = rows[0].pk
        for path in ("favorites", "cart/items"):
            result = self.http("POST", path, 201, {"activity_id": pk})
            self.keys(result, "activity_id message")
            self.http("POST", path, 409, {"activity_id": pk})
            self.http("POST", path, 400, {"activity_id": hidden.pk})
        self.assertEqual([r["id"] for r in self.http("GET", "favorites")["results"]], [pk])
        cart = self.http("GET", "cart")
        self.keys(cart, "items total_amount")
        self.assertEqual(cart["total_amount"], 0)
        self.assertEqual([r["id"] for r in cart["items"]], [pk])
        self.signup("http-isolated@example.com")
        self.assertEqual(self.http("GET", "favorites"), {"results": []})
        self.assertEqual(self.http("GET", "cart"), {"items": [], "total_amount": 0})
        self.http("DELETE", f"favorites/{pk}", 404)
        self.http("DELETE", f"cart/items/{pk}", 404)
        self.token = owner["access_token"]
        self.assertEqual(len(self.http("GET", "favorites")["results"]), 1)
        self.assertEqual(len(self.http("GET", "cart")["items"]), 1)
        self.http("DELETE", f"favorites/{pk}", 204)
        self.http("DELETE", f"cart/items/{pk}", 204)
        self.assertEqual(self.http("GET", "favorites"), {"results": []})
        self.assertEqual(self.http("GET", "cart"), {"items": [], "total_amount": 0})
