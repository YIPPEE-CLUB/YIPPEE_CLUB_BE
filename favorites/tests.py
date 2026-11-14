from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from activities.models import Activity
from activities.serializers import ActivitySerializer
from categories.models import Category
from .models import Favorite

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


def activity(title="공개 활동지", public=True):
    # Favorite tests only need file references, not uploads. No real file is read
    # or changed; DB constraints still apply to this isolated fixture insert.
    Activity.objects.bulk_create([Activity(title=title, description="즐겨찾기 테스트",
        age_min_months=60, age_max_months=65, difficulty="easy", duration_min=5, duration_max=5,
        price=0, is_public=public, pdf="isolated-fixture.pdf", image="isolated-fixture.png")])
    return Activity.objects.get(title=title)


@skipUnless(ISOLATED, "Favorite tests require isolated MySQL.")
class FavoriteAPITests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        self.owner = get_user_model().objects.create_user("favorite-owner@example.com", None)
        self.other = get_user_model().objects.create_user("favorite-other@example.com", None)
        self.row = activity()
        self.hidden = activity("비공개 활동지", False)
        self.category = Category.objects.create(name="즐겨찾기 테스트 카테고리")
        self.row.categories.add(self.category)
        self.client = APIClient()
        self.authenticate(self.owner)
        self.url = reverse("favorites:list")

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(AccessToken.for_user(user)))

    def delete_url(self, pk=None):
        return reverse("favorites:delete", args=[self.row.pk if pk is None else pk])

    def error(self, response, status):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})

    def test_create_contract_and_owner_binding(self):
        response = self.client.post(self.url, {"activity_id": self.row.pk}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {"activity_id": self.row.pk, "message": "처리되었습니다."})
        favorite = Favorite.objects.get()
        self.assertEqual((favorite.user_id, favorite.activity_id), (self.owner.pk, self.row.pk))

    def test_duplicate_is_409_and_unique_database_constraint(self):
        Favorite.objects.create(user=self.owner, activity=self.row)
        self.error(self.client.post(self.url, {"activity_id": self.row.pk}, format="json"), 409)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorite.objects.create(user=self.owner, activity=self.row)
        self.assertEqual(Favorite.objects.count(), 1)
        Favorite.objects.create(user=self.other, activity=self.row)
        self.assertEqual(Favorite.objects.count(), 2)

    def test_delete_contract_repeat_and_other_owner_isolation(self):
        own = Favorite.objects.create(user=self.owner, activity=self.row)
        other = Favorite.objects.create(user=self.other, activity=self.row)
        response = self.client.delete(self.delete_url())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(Favorite.objects.filter(pk=own.pk).exists())
        self.assertTrue(Favorite.objects.filter(pk=other.pk).exists())
        self.error(self.client.delete(self.delete_url()), 404)
        self.error(self.client.delete(self.delete_url(999999999)), 404)
        self.assertTrue(Favorite.objects.filter(pk=other.pk).exists())

    def test_list_contract_uses_existing_activity_serializer_and_no_private_data(self):
        Favorite.objects.create(user=self.other, activity=self.hidden)
        Favorite.objects.create(user=self.owner, activity=self.row)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"results"})
        self.assertEqual(len(response.data["results"]), 1)
        item = response.data["results"][0]
        self.assertEqual(set(item), set(ActivitySerializer.Meta.fields))
        self.assertEqual((item["id"], item["price"], item["categories"]), (self.row.pk, 0, [self.category.pk]))
        for key in ("user_id", "email", "favorite_id", "is_favorite"):
            self.assertNotIn(key, item)
        self.authenticate(self.other)
        self.assertEqual(self.client.get(self.url).data, {"results": []})

    def test_pagination_latest_first_and_empty_page(self):
        second = activity("두 번째 공개 활동지")
        Favorite.objects.create(user=self.owner, activity=self.row)
        Favorite.objects.create(user=self.owner, activity=second)
        for page, expected in ((1, [second.pk]), (2, [self.row.pk]), (3, [])):
            response = self.client.get(self.url, {"page": page, "page_size": 1})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(response.data), {"results"})
            self.assertEqual([r["id"] for r in response.data["results"]], expected)

    def test_unavailable_activity_add_uses_spec_400(self):
        for pk in (self.hidden.pk, 999999999):
            self.error(self.client.post(self.url, {"activity_id": pk}, format="json"), 400)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_unpublished_saved_activity_hidden_but_removable(self):
        Favorite.objects.create(user=self.owner, activity=self.row)
        Activity.objects.filter(pk=self.row.pk).update(is_public=False)
        self.assertEqual(self.client.get(self.url).data, {"results": []})
        self.error(self.client.post(self.url, {"activity_id": self.row.pk}, format="json"), 400)
        self.assertEqual(self.client.delete(self.delete_url()).status_code, 204)

    def test_hidden_relationship_is_preserved_when_republished(self):
        Favorite.objects.create(user=self.owner, activity=self.hidden)
        self.assertEqual(self.client.get(self.url).data, {"results": []})
        Activity.objects.filter(pk=self.hidden.pk).update(is_public=True)
        self.assertEqual([r["id"] for r in self.client.get(self.url).data["results"]], [self.hidden.pk])

    def test_invalid_payloads_and_user_id_injection(self):
        for body in ({}, {"activity_id": None}, {"activity_id": True}, {"activity_id": "1"},
                     {"activity_id": 1.0}, {"activity_id": -1}, {"activity_id": 0},
                     {"activity_id": 9223372036854775808}, [],
                     {"activity_id": self.row.pk, "user_id": self.other.pk}):
            with self.subTest(body=body):
                self.error(self.client.post(self.url, body, format="json"), 400)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_bad_queries_and_path_ids(self):
        for query in ({"page": 0}, {"page": "bad"}, {"page_size": 101}, {"page_size": 0},
                      {"page": 2147483648}, {"user_id": self.other.pk}, {"sort": "popular"}):
            self.error(self.client.get(self.url, query), 400)
        for pk in (0, 9223372036854775808):
            self.error(self.client.delete(self.delete_url(pk)), 400)

    def test_jwt_missing_invalid_expired_wrong_type_and_inactive(self):
        expired = AccessToken.for_user(self.owner)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        tokens = (None, "invalid", str(expired), str(RefreshToken.for_user(self.owner)))
        for token in tokens:
            self.client.credentials(**({"HTTP_AUTHORIZATION": "Bearer " + token} if token else {}))
            for response in (self.client.get(self.url),
                    self.client.post(self.url, {"activity_id": self.row.pk}, format="json"),
                    self.client.delete(self.delete_url())):
                self.error(response, 401)
        self.authenticate(self.owner)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.error(self.client.get(self.url), 401)

    def test_activity_and_user_deletion_cascade_links_only(self):
        Favorite.objects.create(user=self.owner, activity=self.row)
        Favorite.objects.create(user=self.other, activity=self.row)
        self.row.delete()
        self.assertEqual(Favorite.objects.count(), 0)
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        Favorite.objects.create(user=self.owner, activity=self.hidden)
        self.owner.delete()
        self.assertEqual(Favorite.objects.count(), 0)
        self.assertTrue(Activity.objects.filter(pk=self.hidden.pk).exists())

    def test_activity_responses_unchanged_for_authenticated_and_public_callers(self):
        before = self.client.get(f"/api/v1/activities/{self.row.pk}").data
        self.client.post(self.url, {"activity_id": self.row.pk}, format="json")
        self.assertEqual(self.client.get(f"/api/v1/activities/{self.row.pk}").data, before)
        self.assertNotIn("is_favorite", before)
        self.client.credentials()
        self.assertEqual(self.client.get(f"/api/v1/activities/{self.row.pk}").data, before)
        self.assertEqual(self.client.get("/api/v1/activities").data["count"], 1)


@skipUnless(ISOLATED, "Concurrency tests require isolated MySQL.")
class FavoriteConcurrencyTests(TransactionTestCase):
    databases = {"default"} if ISOLATED else set()

    def test_competing_api_requests_create_one_pair(self):
        user = get_user_model().objects.create_user("favorite-concurrent@example.com", None)
        row = activity("동시 요청 테스트")
        token = str(AccessToken.for_user(user))
        barrier = Barrier(2)
        with connection.cursor() as cursor:
            cursor.execute("SELECT @@server_uuid,@@port,@@server_id")
            expected = cursor.fetchone()

        def post():
            from config.user_model_rehearsal import guard_rehearsal_sql
            try:
                # New threads get new wrappers; attach the existing SQL guard explicitly.
                with connection.execute_wrapper(guard_rehearsal_sql):
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT @@server_uuid,@@port,@@server_id")
                        if cursor.fetchone() != expected:
                            raise RuntimeError("Concurrent test server identity mismatch")
                    client = APIClient()
                    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
                    barrier.wait(timeout=10)
                    return client.post("/api/v1/favorites", {"activity_id": row.pk}, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(post) for _ in range(2)]
            statuses = sorted(future.result(timeout=30) for future in futures)
        self.assertEqual(statuses, [201, 409])
        self.assertEqual(Favorite.objects.filter(user=user, activity=row).count(), 1)
