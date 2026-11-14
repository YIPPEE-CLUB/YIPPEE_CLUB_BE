from io import BytesIO
from tempfile import TemporaryDirectory
from unittest import skipUnless

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from categories.models import Category
from .admin import ActivityForm
from .models import Activity
from .validators import validate_pdf, validate_cover

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


def pdf(name="play.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF", content_type="application/pdf")


def image():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), "white").save(buffer, "PNG")
    return SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")


@skipUnless(ISOLATED, "Activity tests require the isolated MySQL instance.")
class ActivityTests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(ACTIVITY_PRIVATE_ROOT=directory.name)
        override.enable()
        self.addCleanup(override.disable)
        self.category = Category.objects.create(name="Test category")
        self.client = APIClient()
        self.row = self.create()

    def values(self, **extra):
        return dict(title="징검다리", description="놀이 설명", age_min_months=60,
                    age_max_months=65, difficulty="easy", duration_min=5, duration_max=5,
                    is_public=True, **extra)

    def create(self):
        row = Activity.objects.create(**self.values(), pdf=pdf(), image=image())
        row.categories.add(self.category)
        return row

    def test_model_and_category(self):
        self.assertEqual(self.row.price, 0)
        self.assertEqual(list(self.row.categories.all()), [self.category])
        self.assertNotIn("play.pdf", self.row.pdf.name)
        with self.assertRaises(ValueError):
            _ = self.row.pdf.url

    def test_invalid_models(self):
        for changes in ({"price": 1}, {"age_max_months": 59}, {"duration_min": 0},
                        {"duration_max": 4}, {"title": ""}, {"difficulty": "unknown"}, {"pdf": ""}):
            row = Activity.objects.get(pk=self.row.pk)
            for key, value in changes.items():
                setattr(row, key, value)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                row.save()

    def test_database_constraints_prevent_bulk_bypass(self):
        for changes in ({"price": 10}, {"age_max_months": 1}, {"duration_min": 0}, {"difficulty": "unknown"}):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                Activity.objects.filter(pk=self.row.pk).update(**changes)

    def test_upload_validation(self):
        validate_pdf(pdf())
        validate_cover(image())
        for value, validator in [(pdf("bad.exe"), validate_pdf),
                                 (SimpleUploadedFile("bad.pdf", b"not a PDF"), validate_pdf),
                                 (SimpleUploadedFile("bad.png", b"not an image"), validate_cover)]:
            with self.assertRaises(ValidationError):
                validator(value)
        with override_settings(ACTIVITY_PDF_MAX_BYTES=1), self.assertRaises(ValidationError):
            validate_pdf(pdf())
        with override_settings(ACTIVITY_IMAGE_MAX_BYTES=1), self.assertRaises(ValidationError):
            validate_cover(image())

    def test_list_detail_and_public_auth_contract(self):
        response = self.client.get("/api/v1/activities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        response = self.client.get(f"/api/v1/activities/{self.row.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue({"id", "title", "price", "sale_status", "description"} <= response.data.keys())
        self.assertEqual(response.data["price"], 0)
        self.assertNotIn(self.row.pdf.name, response.data["pdf"])
        self.assertEqual(self.client.post("/api/v1/activities", {}).status_code, 405)

    def test_filters_and_pagination(self):
        for query in ({"q": "징검"}, {"category": self.category.pk}, {"age_years": 5},
                      {"difficulty": "easy"}, {"duration": "5-10"}, {"sort": "title"}):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/v1/activities", query).data["count"], 1)
        for query in ({"q": "없는 제목"}, {"age_years": 4}, {"difficulty": "hard"}, {"price_min": 1}):
            self.assertEqual(self.client.get("/api/v1/activities", query).data["count"], 0)
        self.create()
        response = self.client.get("/api/v1/activities", {"page_size": 1})
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["next"])

    def test_bad_queries(self):
        for query in ({"age_years": "bad"}, {"category": "painting"}, {"difficulty": "medium"},
                      {"page": 0}, {"page_size": 101}, {"duration": "10-5"}, {"sort": "popular"},
                      {"price_min": 2, "price_max": 1}):
            response = self.client.get("/api/v1/activities", query)
            self.assertEqual(response.status_code, 400, query)
            self.assertEqual(response.data["code"], "VALIDATION_ERROR")

    def test_file_and_unpublish_revokes_access(self):
        # Explicit streaming close emits request_finished. Keep TestCase's outer
        # transaction alive across the multiple simulated requests in this test.
        from django.core.signals import request_finished
        from django.db import close_old_connections
        request_finished.disconnect(close_old_connections)
        self.addCleanup(request_finished.connect, close_old_connections)
        for kind in ("pdf", "image"):
            response = self.client.get(f"/api/v1/activities/{self.row.pk}/files/{kind}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Cache-Control"], "private, no-store")
            response.close()
        self.row.is_public = False
        self.row.save()
        self.assertEqual(self.client.get("/api/v1/activities").data["count"], 0)
        for suffix in ("", "/files/pdf", "/files/image"):
            self.assertEqual(self.client.get(f"/api/v1/activities/{self.row.pk}{suffix}").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/activities/999999").status_code, 404)

    def test_admin_registration_update_and_price_tampering(self):
        user = get_user_model().objects.create_superuser("activity-admin@example.com", "StrongPassword!7219")
        self.client.force_login(user)
        response = self.client.get("/admin/activities/activity/add/")
        self.assertEqual(response.status_code, 200)
        values = self.values()
        values.update(categories=[self.category.pk], pdf=pdf(), image=image(), price=999, _save="저장")
        response = self.client.post("/admin/activities/activity/add/", values)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        row = Activity.objects.latest("id")
        self.assertEqual(row.price, 0)
        self.assertEqual(row.categories.count(), 1)
        response = self.client.get(f"/admin/activities/activity/{row.pk}/change/")
        self.assertEqual(response.status_code, 200)
        values = self.values()
        values.update(title="수정", categories=[self.category.pk], price=999, _save="저장")
        values.pop("is_public")
        old_file = row.pdf.name
        response = self.client.post(f"/admin/activities/activity/{row.pk}/change/", values)
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertFalse(row.is_public)
        self.assertEqual(row.title, "수정")
        self.assertEqual(row.price, 0)
        self.assertEqual(row.pdf.name, old_file)
        values.update(pdf=pdf(), image=image())
        response = self.client.post(f"/admin/activities/activity/{row.pk}/change/", values)
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertNotEqual(row.pdf.name, old_file)
        self.assertTrue(row.pdf.storage.exists(old_file))

    def test_admin_denies_member_and_requires_category(self):
        user = get_user_model().objects.create_user("activity-member@example.com", "StrongPassword!7219")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/admin/activities/activity/add/").status_code, 302)
        form = ActivityForm(data=self.values(), files={"pdf": pdf(), "image": image()})
        self.assertFalse(form.is_valid())
        self.assertIn("categories", form.errors)
