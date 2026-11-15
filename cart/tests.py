from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from activities.models import Activity
from activities.serializers import ActivitySerializer
from favorites.tests import activity
from purchases.models import PurchaseEntitlement
from .models import CartItem

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


@skipUnless(ISOLATED, "Cart tests require isolated MySQL.")
@override_settings(CART_PURCHASE_ENTITLEMENTS_VERIFIED=False)
class CartAPITests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        self.owner = get_user_model().objects.create_user("cart-owner@example.com", None)
        self.other = get_user_model().objects.create_user("cart-other@example.com", None)
        self.row = activity("장바구니 공개 활동지")
        self.hidden = activity("장바구니 비공개 활동지", False)
        self.client = APIClient()
        self.authenticate(self.owner)

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(AccessToken.for_user(user)))

    def post(self, body=None):
        return self.client.post("/api/v1/cart/items", {"activity_id": self.row.pk} if body is None else body, format="json")

    def delete(self, pk=None):
        return self.client.delete(f"/api/v1/cart/items/{self.row.pk if pk is None else pk}")

    def error(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})
        if code:
            self.assertEqual(response.data["code"], code)

    def test_create_and_duplicate_contract(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data, {"activity_id": self.row.pk, "message": "처리되었습니다."})
        self.assertEqual(CartItem.objects.get().user_id, self.owner.pk)
        self.error(self.post(), 409, "INVALID_STATE")
        self.assertEqual(CartItem.objects.count(), 1)

    def test_list_empty_and_full_contract_and_owner_isolation(self):
        self.assertEqual(self.client.get("/api/v1/cart").data, {"items": [], "total_amount": 0})
        second = activity("두 번째 장바구니 활동지")
        CartItem.objects.create(user=self.other, activity=self.row)
        CartItem.objects.create(user=self.owner, activity=self.row)
        CartItem.objects.create(user=self.owner, activity=second)
        CartItem.objects.create(user=self.owner, activity=self.hidden)
        response = self.client.get("/api/v1/cart")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"items", "total_amount"})
        self.assertEqual([row["id"] for row in response.data["items"]], [second.pk, self.row.pk])
        self.assertEqual(response.data["total_amount"], sum(row["price"] for row in response.data["items"]))
        self.assertEqual(response.data["total_amount"], 0)
        self.assertTrue(all(row["price"] == 0 for row in response.data["items"]))
        self.assertEqual(set(response.data["items"][0]), set(ActivitySerializer.Meta.fields))
        self.authenticate(self.other)
        self.assertEqual([row["id"] for row in self.client.get("/api/v1/cart").data["items"]], [self.row.pk])

    def test_query_injection_and_undefined_pagination_rejected(self):
        for query in ({"user_id": self.other.pk}, {"page": 1}, {"sort": "price"}):
            self.error(self.client.get("/api/v1/cart", query), 400)

    def test_jwt_missing_invalid_expired_and_refresh_all_routes(self):
        expired = AccessToken.for_user(self.owner)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        for token in (None, "invalid", str(expired), str(RefreshToken.for_user(self.owner))):
            self.client.credentials(**({"HTTP_AUTHORIZATION": "Bearer " + token} if token else {}))
            for response in (self.client.get("/api/v1/cart"), self.post(), self.delete()):
                self.error(response, 401, "AUTHENTICATION_REQUIRED")

    def test_invalid_types_missing_and_untrusted_fields(self):
        for body in ({}, [], {"activity_id": None}, {"activity_id": True}, {"activity_id": "1"},
                     {"activity_id": 1.0}, {"activity_id": 0}, {"activity_id": -1},
                     {"activity_id": 9223372036854775808},
                     {"activity_id": self.row.pk, "user_id": self.other.pk},
                     {"activity_id": self.row.pk, "price": 1},
                     {"activity_id": self.row.pk, "total_amount": 1}):
            with self.subTest(body=body):
                self.error(self.post(body), 400, "VALIDATION_ERROR")
        self.assertFalse(CartItem.objects.exists())

    def test_unavailable_activity(self):
        for pk in (self.hidden.pk, 999999999):
            self.error(self.post({"activity_id": pk}), 400)
        self.assertFalse(CartItem.objects.exists())

    def test_active_purchase_does_not_block_free_cart_and_record_is_preserved(self):
        right = PurchaseEntitlement.objects.create(user=self.owner, activity=self.row)
        before = PurchaseEntitlement.objects.values().get(pk=right.pk)
        self.assertEqual(self.post().status_code, 201)
        self.error(self.post(), 409, "INVALID_STATE")
        self.assertEqual(self.client.get("/api/v1/cart").data["total_amount"], 0)
        self.assertEqual(self.delete().status_code, 204)
        self.assertEqual(PurchaseEntitlement.objects.values().get(pk=right.pk), before)

    def test_other_users_purchase_does_not_block(self):
        PurchaseEntitlement.objects.create(user=self.other, activity=self.row)
        self.assertEqual(self.post().status_code, 201)

    def test_revoked_entitlement_is_not_active(self):
        right = PurchaseEntitlement.objects.create(user=self.owner, activity=self.row,
            status=PurchaseEntitlement.Status.REVOKED, revoked_at=timezone.now())
        before = PurchaseEntitlement.objects.values().get(pk=right.pk)
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(PurchaseEntitlement.objects.values().get(pk=right.pk), before)

    @override_settings(CART_PURCHASE_ENTITLEMENTS_VERIFIED=False)
    def test_unverified_permissions_allow_free_add_read_and_delete(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertEqual(self.client.get("/api/v1/cart").status_code, 200)
        self.assertEqual(self.delete().status_code, 204)

    def test_free_cart_does_not_query_purchase_permissions(self):
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(self.post().status_code, 201)
            self.assertEqual(self.client.get("/api/v1/cart").status_code, 200)
            self.assertEqual(self.delete().status_code, 204)
        self.assertFalse(any("purchase_entitlements" in row["sql"].lower() for row in queries))

    def test_delete_uses_activity_id_owner_and_preserves_source_and_rights(self):
        # Distinct item and activity IDs catch accidental deletion by cart PK.
        CartItem.objects.create(user=self.other, activity=self.hidden)
        own = CartItem.objects.create(user=self.owner, activity=self.row)
        other = CartItem.objects.create(user=self.other, activity=self.row)
        right = PurchaseEntitlement.objects.create(user=self.owner, activity=self.row)
        response = self.delete()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(CartItem.objects.filter(pk=own.pk).exists())
        self.assertTrue(CartItem.objects.filter(pk=other.pk).exists())
        self.error(self.delete(), 404, "NOT_FOUND")
        self.error(self.delete(999999999), 404)
        self.assertTrue(Activity.objects.filter(pk=self.row.pk).exists())
        self.assertTrue(PurchaseEntitlement.objects.filter(pk=right.pk).exists())

    def test_unpublished_cart_item_hidden_and_removable(self):
        CartItem.objects.create(user=self.owner, activity=self.row)
        Activity.objects.filter(pk=self.row.pk).update(is_public=False)
        self.assertEqual(self.client.get("/api/v1/cart").data, {"items": [], "total_amount": 0})
        self.error(self.post(), 400)
        self.assertEqual(self.delete().status_code, 204)

    def test_invalid_numeric_delete_ids(self):
        for pk in (0, 9223372036854775808):
            self.error(self.delete(pk), 400)

    def test_database_uniqueness_and_entitlement_state_constraint(self):
        CartItem.objects.create(user=self.owner, activity=self.row)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CartItem.objects.create(user=self.owner, activity=self.row)
        PurchaseEntitlement.objects.create(user=self.owner, activity=self.row)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseEntitlement.objects.create(user=self.owner, activity=self.row)
        for status, revoked in (("invalid", None), ("revoked", None), ("active", timezone.now())):
            with self.assertRaises(IntegrityError), transaction.atomic():
                PurchaseEntitlement.objects.create(user=self.other, activity=self.hidden, status=status, revoked_at=revoked)

    def test_cascade_only_cart_links_and_protect_purchased_sources(self):
        CartItem.objects.create(user=self.owner, activity=self.row)
        self.owner.delete()
        self.assertFalse(CartItem.objects.exists())
        self.assertTrue(Activity.objects.filter(pk=self.row.pk).exists())
        CartItem.objects.create(user=self.other, activity=self.hidden)
        self.hidden.delete()
        self.assertFalse(CartItem.objects.exists())
        PurchaseEntitlement.objects.create(user=self.other, activity=self.row)
        with self.assertRaises(ProtectedError):
            self.row.delete()
        with self.assertRaises(ProtectedError):
            self.other.delete()


@skipUnless(ISOLATED, "Concurrency tests require isolated MySQL.")
@override_settings(CART_PURCHASE_ENTITLEMENTS_VERIFIED=False)
class CartConcurrencyTests(TransactionTestCase):
    databases = {"default"} if ISOLATED else set()

    def test_competing_requests_create_exactly_one_pair(self):
        user = get_user_model().objects.create_user("cart-concurrent@example.com", None)
        row = activity("장바구니 동시 요청")
        token = str(AccessToken.for_user(user))
        barrier = Barrier(2)

        def post():
            from config.user_model_rehearsal import guard_rehearsal_sql
            try:
                with connection.execute_wrapper(guard_rehearsal_sql):
                    client = APIClient()
                    client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
                    barrier.wait(timeout=10)
                    return client.post("/api/v1/cart/items", {"activity_id": row.pk}, format="json").status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(post) for _ in range(2)]
            self.assertEqual(sorted(future.result(timeout=30) for future in futures), [201, 409])
        self.assertEqual(CartItem.objects.filter(user=user, activity=row).count(), 1)
