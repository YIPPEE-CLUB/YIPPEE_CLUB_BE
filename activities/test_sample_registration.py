"""Synthetic uploads only in isolated MySQL; no supplied sample is replaced."""
from io import StringIO
from tempfile import TemporaryDirectory
from unittest import skipUnless
import secrets
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from categories.models import Category
from scripts.prepare_sample_activities import ensure_categories
from .admin import ActivityForm
from .models import Activity
from .tests import pdf, image

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)
TITLES = ("단비와 보리의 징검다리 모험", "단비와 보리의 숫자 놀이", "단비랑 보리의 콩 놀이", "단비와 보리의 공 놀이")
DESCRIPTIONS = (
    "인형을 집까지 안전하게 이동시키며 차례를 번갈아 가며 놀이하는 활동",
    "종이 길을 따라 숫자 카드를 활용하며 결승점에 도착하는 놀이",
    "숫자 카드에 맞춰 콩을 떠서 컵에 모으며 수 개념과 소근육 조절 능력을 기르는 활동",
    "가까운 거리와 먼 거리에서 공을 바구니에 던지며 신체 조절과 의사소통 능력을 기르는 활동",
)


@skipUnless(ISOLATED, "Sample registration checks require isolated MySQL.")
class SampleRegistrationTests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        override = override_settings(ACTIVITY_PRIVATE_ROOT=temp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client = APIClient()
        self.test_password = secrets.token_urlsafe(32)

    def test_category_preparation_reuses_names_and_database_ids(self):
        first = ensure_categories()
        second = ensure_categories()
        self.assertEqual(Category.objects.count(), 2)
        self.assertEqual([r["id"] for r in first], [r["id"] for r in second])
        self.assertTrue(all(r["created"] for r in first))
        self.assertFalse(any(r["created"] for r in second))

    def test_duplicate_category_names_abort_without_inserts(self):
        Category.objects.create(name="자연탐구")
        Category.objects.create(name="자연탐구")
        with self.assertRaises(CommandError):
            ensure_categories()
        self.assertEqual(Category.objects.count(), 2)
        self.assertFalse(Category.objects.filter(name="신체운동·건강").exists())

    def test_admin_labels_and_range_validation(self):
        form = ActivityForm()
        self.assertEqual(form.fields["age_min_months"].label, "최소 개월 수")
        self.assertEqual(form.fields["age_max_months"].label, "최대 개월 수")
        user = get_user_model().objects.create_superuser("sample-labels@example.com", self.test_password)
        self.assertTrue(self.client.login(email=user.email, password=self.test_password))
        # Django renders list column headers only when the result list has a row.
        Activity.objects.create(title="표시 검사용", description="격리 테스트 자료",
                                age_min_months=60, age_max_months=65, difficulty="easy",
                                duration_min=5, duration_max=5, pdf=pdf(), image=image())
        for url in ("/admin/activities/activity/add/", "/admin/activities/activity/"):
            response = self.client.get(url)
            self.assertContains(response, "최소 개월 수")
            self.assertContains(response, "최대 개월 수")
            self.assertContains(response, "가격(원)")
            self.assertNotContains(response, "월령")
        invalid = Activity(age_min_months=65, age_max_months=60)
        with self.assertRaisesMessage(ValidationError, "최대 개월 수는 최소 개월 수 이상이어야 합니다."):
            invalid.clean()

    def test_no_model_migration_required(self):
        call_command("makemigrations", check=True, dry_run=True, stdout=StringIO())

    def test_four_private_admin_uploads_then_public_api_and_bytes(self):
        categories = ensure_categories()
        category_ids = [row["id"] for row in categories]
        user = get_user_model().objects.create_superuser("sample-flow@example.com", self.test_password)
        self.assertTrue(self.client.login(email=user.email, password=self.test_password))
        rows, originals = [], {}
        for index, (title, minutes) in enumerate(zip(TITLES, (5, 10, 5, 15))):
            pdf_file, image_file = pdf(), image()
            pdf_bytes, image_bytes = pdf_file.read(), image_file.read()
            pdf_file.seek(0)
            image_file.seek(0)
            response = self.client.post("/admin/activities/activity/add/", {
                "title": title, "description": DESCRIPTIONS[index], "age_min_months": 60,
                "age_max_months": 65, "difficulty": "easy" if index == 0 else "hard",
                "duration_min": minutes, "duration_max": minutes, "categories": category_ids,
                "price": 9999, "pdf": pdf_file, "image": image_file, "_save": "저장",
            })
            self.assertEqual(response.status_code, 302)
            row = Activity.objects.get(title=title)
            self.assertFalse(row.is_public)
            self.assertEqual((row.price, row.age_min_months, row.age_max_months), (0, 60, 65))
            self.assertEqual((row.duration_min, row.duration_max), (minutes, minutes))
            self.assertEqual(list(row.categories.values_list("id", flat=True)), category_ids)
            for field, expected in ((row.pdf, pdf_bytes), (row.image, image_bytes)):
                with field.storage.open(field.name, "rb") as stream:
                    self.assertEqual(stream.read(), expected)
            rows.append(row)
            originals[row.pk] = {"pdf": pdf_bytes, "image": image_bytes}
        self.assertEqual(Activity.objects.count(), 4)
        public = APIClient()
        self.assertEqual(public.get("/api/v1/activities").data["count"], 0)
        for row in rows:
            for suffix in ("", "/files/pdf", "/files/image"):
                self.assertEqual(public.get(f"/api/v1/activities/{row.pk}{suffix}").status_code, 404)
            response = self.client.get(f"/admin/activities/activity/{row.pk}/change/")
            self.assertContains(response, "최소 개월 수")
            self.assertNotContains(response, "월령")
        # Only after validating all four private records, publish the test batch.
        Activity.objects.filter(pk__in=[row.pk for row in rows]).update(is_public=True)
        response = public.get("/api/v1/activities")
        self.assertEqual(response.data["count"], 4)
        for row in rows:
            response = public.get(f"/api/v1/activities/{row.pk}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.data["age_min_months"], response.data["age_max_months"]), (60, 65))
            self.assertEqual(response.data["price"], 0)
            for kind in ("pdf", "image"):
                response = public.get(f"/api/v1/activities/{row.pk}/files/{kind}")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b"".join(response.streaming_content), originals[row.pk][kind])
                # The test client's streaming iterator closes the response itself.
        for query, count in (({"q": "콩 놀이"}, 1), ({"category": category_ids[0]}, 4),
                             ({"age_years": 5}, 4), ({"age_years": 4}, 0),
                             ({"difficulty": "easy"}, 1), ({"difficulty": "hard"}, 3)):
            self.assertEqual(public.get("/api/v1/activities", query).data["count"], count)
        self.assertEqual(public.get("/api/v1/activities/999999999").status_code, 404)

    def test_supplied_files_import_private_then_public_and_duplicate_rejection(self):
        from .sample_import import SAMPLES, preflight, register_private, verify_rows
        from scripts.register_sample_activities import verify_api
        root = Path(settings.BASE_DIR) / "sample_activities"
        if not all((root / filename).is_file() for sample in SAMPLES for filename in sample[4:]):
            self.skipTest("Eight user-supplied sample files are not available.")
        ensure_categories()
        originals = preflight(root)
        ids = register_private(root)
        self.assertEqual(len(verify_rows(root, ids, public=False)), 4)
        self.assertEqual(verify_api(root, ids, False)["count"], 0)
        files_before = sorted(str(p) for p in Path(settings.ACTIVITY_PRIVATE_ROOT).rglob("*") if p.is_file())
        with self.assertRaises(CommandError):
            register_private(root)
        self.assertEqual(files_before, sorted(str(p) for p in Path(settings.ACTIVITY_PRIVATE_ROOT).rglob("*") if p.is_file()))
        self.assertEqual(Activity.objects.count(), 4)
        Activity.objects.filter(pk__in=ids).update(is_public=True)
        self.assertEqual(len(verify_rows(root, ids, public=True)), 4)
        self.assertEqual(verify_api(root, ids, True)["count"], 4)
        self.assertEqual(preflight(root), originals)

    def test_import_failure_rolls_back_and_removes_only_new_files(self):
        from .sample_import import SAMPLES, register_private
        root = Path(settings.BASE_DIR) / "sample_activities"
        if not all((root / filename).is_file() for sample in SAMPLES for filename in sample[4:]):
            self.skipTest("Eight user-supplied sample files are not available.")
        ensure_categories()
        existing = Path(settings.ACTIVITY_PRIVATE_ROOT) / "preserve.txt"
        existing.write_bytes(b"existing unrelated file")
        journal = []
        with patch.object(Activity, "save", side_effect=RuntimeError("Injected save failure")):
            with self.assertRaises(RuntimeError):
                register_private(root, journal.append)
        self.assertEqual(Activity.objects.count(), 0)
        self.assertEqual(existing.read_bytes(), b"existing unrelated file")
        self.assertEqual([p for p in Path(settings.ACTIVITY_PRIVATE_ROOT).rglob("*") if p.is_file()], [existing])
        self.assertEqual(sum(e["event"] == "rolled_back_file_removed" for e in journal), 2)
