from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import RefreshSession
from categories.models import Category

from .models import ActivityRecord, Child, ChildInterest

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False) and settings.AUTH_USER_MODEL == "accounts.User"


@skipUnless(ISOLATED, "Child API tests require the isolated MySQL instance.")
class ChildAPITests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user("child-owner@example.com", "OwnerSecurePwd!72349")
        self.other = User.objects.create_user("child-other@example.com", "OtherSecurePwd!72349")
        self.first = Category.objects.create(name="First test category")
        self.second = Category.objects.create(name="Second test category")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(AccessToken.for_user(self.owner)))
        self.birth_date = "2022-05-01"
        self.url = reverse("children:list")

    def create(self, **overrides):
        return self.client.post(self.url, {"name": "Child", "birth_date": self.birth_date,
                                          "gender": "female", "interests": [self.first.pk], **overrides}, format="json")

    def detail(self, child_id):
        return reverse("children:detail", args=[child_id])

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})

    def test_create_detail_and_contract(self):
        response = self.create(interests=[self.second.pk, self.first.pk])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(set(response.data), {"id", "name", "birth_date", "gender", "interests"})
        self.assertEqual(response.data["birth_date"], self.birth_date)
        self.assertEqual(response.data["interests"], [self.first.pk, self.second.pk])
        child = Child.objects.get(pk=response.data["id"])
        self.assertEqual(child.user_id, self.owner.pk)
        self.assertEqual(self.client.get(self.detail(child.pk)).data, response.data)

    def test_multiple_children_and_list_only_owner(self):
        first = self.create().data["id"]
        second = self.create(name="Second").data["id"]
        Child.objects.create(user=self.other, name="Private", birth_date=self.birth_date)
        response = self.client.get(self.url, {"user_id": self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"results"})
        self.assertEqual([child["id"] for child in response.data["results"]], [first, second])

    def test_empty_list(self):
        self.assertEqual(self.client.get(self.url).data, {"results": []})

    def test_unauthenticated_all_methods_and_categories(self):
        child = Child.objects.create(user=self.owner, name="Private", birth_date=self.birth_date)
        self.client.credentials()
        operations = [self.client.get(self.url), self.create(), self.client.get(self.detail(child.pk)),
                      self.client.patch(self.detail(child.pk), {"name": "Attack"}, format="json"),
                      self.client.delete(self.detail(child.pk)), self.client.get(reverse("categories:list"))]
        for response in operations:
            self.assert_error(response, 401)
        self.assertTrue(Child.objects.filter(pk=child.pk).exists())

    def test_invalid_and_expired_jwt(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assert_error(self.client.get(self.url), 401)
        token = AccessToken.for_user(self.owner)
        token.set_exp(lifetime=timedelta(seconds=-1))
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(token))
        self.assert_error(self.client.get(self.url), 401)

    def test_other_user_detail_patch_delete_all_404(self):
        child = Child.objects.create(user=self.other, name="Private", birth_date=self.birth_date)
        record = ActivityRecord.objects.create(child=child)
        for response in [self.client.get(self.detail(child.pk)),
                         self.client.patch(self.detail(child.pk), {"name": "Attack"}, format="json"),
                         self.client.delete(self.detail(child.pk))]:
            self.assert_error(response, 404)
        child.refresh_from_db()
        self.assertEqual(child.name, "Private")
        self.assertTrue(ActivityRecord.objects.filter(pk=record.pk).exists())

    def test_missing_and_malformed_ids(self):
        for method in (self.client.get, self.client.delete):
            self.assert_error(method(self.detail(999999999)), 404)
        self.assertEqual(self.client.get("/api/v1/children/not-an-id").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/children/-1").status_code, 404)

    def test_readonly_and_ownership_fields_rejected(self):
        for key, value in (("user_id", self.other.pk), ("user", self.other.pk), ("id", 9384), ("activity_records", [])):
            self.assert_error(self.create(**{key: value}), 400)
        self.assertFalse(Child.objects.exists())
        child_id = self.create().data["id"]
        self.assert_error(self.client.patch(self.detail(child_id), {"user_id": self.other.pk}, format="json"), 400)
        self.assertEqual(Child.objects.get(pk=child_id).user_id, self.owner.pk)

    def test_required_fields_and_bad_dates(self):
        for body in ({}, {"name": "Only name"}, {"birth_date": self.birth_date},
                     {"name": None, "birth_date": self.birth_date}, {"name": "", "birth_date": self.birth_date},
                     {"name": 1234, "birth_date": self.birth_date}, {"name": "Child", "birth_date": None},
                     {"name": "Child", "birth_date": "2024-02-30"}):
            self.assert_error(self.client.post(self.url, body, format="json"), 400)
        self.assert_error(self.create(birth_date=(timezone.localdate() + timedelta(days=1)).isoformat()), 400)
        self.assertFalse(Child.objects.exists())

    def test_age_policy_not_invented(self):
        # The 12–72 month boundary is explicitly not finalized in v1.5.
        self.assertEqual(self.create(birth_date=timezone.localdate().isoformat()).status_code, 201)
        self.assertEqual(self.create(birth_date="2000-01-01").status_code, 201)

    def test_optional_fields_omitted_or_null(self):
        response = self.client.post(self.url, {"name": "Minimal", "birth_date": self.birth_date}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["gender"], "")
        self.assertEqual(response.data["interests"], [])
        response = self.create(gender=None, interests=None)
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.data["gender"], response.data["interests"]), ("", []))

    def test_duplicate_unknown_and_mixed_categories_rejected(self):
        for interests in ([self.first.pk, self.first.pk], [999999999], [self.first.pk, 999999999]):
            self.assert_error(self.create(interests=interests), 400)
        self.assertFalse(Child.objects.exists())
        self.assertFalse(ChildInterest.objects.exists())

    def test_category_id_and_list_types_are_strict(self):
        for interests in ("1", {}, [True], [False], [str(self.first.pk)], [1.0], [-1], [0], [None],
                          [{"id": self.first.pk}], [10**30]):
            self.assert_error(self.create(interests=interests), 400)
        self.assert_error(self.create(gender={"value": "female"}), 400)
        self.assertFalse(Child.objects.exists())

    def test_update_scalars_and_replace_interests(self):
        child_id = self.create().data["id"]
        response = self.client.patch(self.detail(child_id), {
            "name": "Updated", "birth_date": "2023-02-28", "gender": "male", "interests": [self.second.pk],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["name"], "Updated")
        self.assertEqual(response.data["birth_date"], "2023-02-28")
        self.assertEqual(response.data["gender"], "male")
        self.assertEqual(response.data["interests"], [self.second.pk])
        self.assertEqual(ChildInterest.objects.filter(child_id=child_id).count(), 1)

    def test_partial_update_keeps_omitted_values(self):
        created = self.create().data
        response = self.client.patch(self.detail(created["id"]), {"name": "Changed"}, format="json")
        self.assertEqual(response.status_code, 200)
        for key in ("birth_date", "gender", "interests"):
            self.assertEqual(response.data[key], created[key])
        self.assertEqual(self.client.patch(self.detail(created["id"]), {}, format="json").status_code, 200)

    def test_update_null_policy(self):
        original = self.create().data
        child_id = original["id"]
        for field in ("name", "birth_date"):
            with self.subTest(field=field):
                response = self.client.patch(self.detail(child_id), {
                    field: None, "gender": None, "interests": None,
                }, format="json")
                self.assert_error(response, 400)
                self.assertIn(field, response.data["details"])
                self.assertEqual(self.client.get(self.detail(child_id)).data, original)
        response = self.client.patch(self.detail(child_id), {
            "gender": None, "interests": None,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["name"], response.data["birth_date"]), ("Child", self.birth_date))
        self.assertEqual((response.data["gender"], response.data["interests"]), ("", []))

    def test_invalid_update_is_atomic(self):
        original = self.create().data
        for interests in ([self.first.pk, self.first.pk], [999999999], [self.first.pk, 999999999]):
            response = self.client.patch(self.detail(original["id"]), {"name": "Do not save", "interests": interests}, format="json")
            self.assert_error(response, 400)
            self.assertEqual(self.client.get(self.detail(original["id"])).data, original)

    def test_database_prevents_duplicate_interest_links(self):
        child_id = self.create().data["id"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChildInterest.objects.create(child_id=child_id, category=self.first)
        self.assertEqual(ChildInterest.objects.count(), 1)

    def test_delete_cascades_only_target_child_records_and_links(self):
        child_id = self.create().data["id"]
        other_child = Child.objects.create(user=self.owner, name="Keep sibling", birth_date=self.birth_date)
        foreign_child = Child.objects.create(user=self.other, name="Keep other owner", birth_date=self.birth_date)
        ActivityRecord.objects.create(child_id=child_id)
        sibling_record = ActivityRecord.objects.create(child=other_child)
        foreign_record = ActivityRecord.objects.create(child=foreign_child)
        session = RefreshSession.objects.create(user=self.owner, token_digest="a" * 64, expires_at=timezone.now() + timedelta(days=1))
        response = self.client.delete(self.detail(child_id))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Child.objects.filter(pk=child_id).exists())
        self.assertFalse(ChildInterest.objects.filter(child_id=child_id).exists())
        self.assertFalse(ActivityRecord.objects.filter(child_id=child_id).exists())
        self.assertTrue(ActivityRecord.objects.filter(pk=sibling_record.pk).exists())
        self.assertTrue(ActivityRecord.objects.filter(pk=foreign_record.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())
        self.assertEqual(Category.objects.count(), 2)
        self.assertTrue(RefreshSession.objects.filter(pk=session.pk).exists())

    def test_failed_delete_rolls_back_child_and_cascaded_records(self):
        child_id = self.create().data["id"]
        record = ActivityRecord.objects.create(child_id=child_id)
        from django.db.models.signals import post_delete

        def fail(sender, **kwargs):
            raise RuntimeError("private-internal-delete-error")

        post_delete.connect(fail, sender=Child, weak=False, dispatch_uid="child-delete-rollback-test")
        try:
            response = self.client.delete(self.detail(child_id))
        finally:
            post_delete.disconnect(sender=Child, dispatch_uid="child-delete-rollback-test")
        self.assert_error(response, 500)
        self.assertNotIn("private-internal-delete-error", str(response.data))
        self.assertTrue(Child.objects.filter(pk=child_id).exists())
        self.assertTrue(ActivityRecord.objects.filter(pk=record.pk).exists())
        self.assertTrue(ChildInterest.objects.filter(child_id=child_id).exists())

    def test_categories_are_shared_catalogue_and_read_only(self):
        child_id = self.create(interests=[self.first.pk, self.second.pk]).data["id"]
        response = self.client.get(reverse("categories:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"results": [{"id": self.first.pk, "name": self.first.name},
                                                     {"id": self.second.pk, "name": self.second.name}]})
        self.assertEqual({item["id"] for item in response.data["results"]}, set(self.client.get(self.detail(child_id)).data["interests"]))
        self.assertEqual(ChildInterest._meta.get_field("category").remote_field.model, Category)
        self.assertEqual(self.client.post(reverse("categories:list"), {"name": "Unauthorized"}, format="json").status_code, 405)

    def test_empty_categories_without_invented_seed_data(self):
        Category.objects.all().delete()
        self.assertEqual(self.client.get(reverse("categories:list")).data, {"results": []})

    def test_url_and_method_scope(self):
        self.assertEqual(self.url, "/api/v1/children")
        self.assertEqual(self.client.get(self.url + "/").status_code, 404)
        self.assertEqual(self.client.put(self.url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.get("/api/v1/activity-categories/1").status_code, 404)
