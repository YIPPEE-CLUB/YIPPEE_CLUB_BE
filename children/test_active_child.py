from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier, Event
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.signals import post_delete
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from categories.models import Category
from .models import ActivityRecord, Child, ChildInterest

ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


@skipUnless(ISOLATED, "Active child tests require isolated MySQL.")
class ActiveChildAPITests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        self.owner = get_user_model().objects.create_user("selection-owner@example.com", None)
        self.other = get_user_model().objects.create_user("selection-other@example.com", None)
        self.first = self.child(self.owner, "First")
        self.second = self.child(self.owner, "Second")
        self.foreign = self.child(self.other, "Private foreign name")
        self.client = APIClient()
        self.authenticate(self.owner)
        self.url = reverse("children:active-child")

    def child(self, owner, name):
        return Child.objects.create(user=owner, name=name, birth_date=date(2022, 5, 1))

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(AccessToken.for_user(user)))

    def select(self, pk):
        return self.client.put(self.url, {"child_id": pk}, format="json")

    def selected(self, user=None):
        return get_user_model().objects.get(pk=(user or self.owner).pk).active_child_id

    def error(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"code", "message", "details", "request_id"})
        if code:
            self.assertEqual(response.data["code"], code)

    def test_select_switch_repeat_and_server_persistence(self):
        self.assertIsNone(self.selected())
        for child in (self.first, self.second, self.second):
            response = self.select(child.pk)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data, {"active_child_id": child.pk})
            self.assertEqual(self.selected(), child.pk)
        self.assertIsNone(self.selected(self.other))
        # A new client/token sees the same persisted User selection.
        self.client = APIClient()
        self.authenticate(self.owner)
        self.assertEqual(self.select(self.second.pk).status_code, 200)
        self.assertEqual(self.selected(), self.second.pk)

    def test_foreign_and_missing_ids_share_error_without_disclosure(self):
        self.select(self.first.pk)
        responses = [self.select(pk) for pk in (self.foreign.pk, 9223372036854775807)]
        for response in responses:
            self.error(response, 400, "VALIDATION_ERROR")
            self.assertNotIn(self.foreign.name, str(response.data))
            self.assertEqual(self.selected(), self.first.pk)
        for key in ("code", "message", "details"):
            self.assertEqual(responses[0].data[key], responses[1].data[key])
        self.assertIsNone(self.selected(self.other))

    def test_user_without_children_has_null_and_cannot_select_foreign(self):
        empty = get_user_model().objects.create_user("selection-empty@example.com", None)
        self.authenticate(empty)
        self.assertIsNone(self.selected(empty))
        self.error(self.select(self.first.pk), 400)
        self.assertIsNone(self.selected(empty))

    def test_strict_types_required_field_and_ownership_injection(self):
        self.select(self.first.pk)
        bodies = ({}, [], None, {"child_id": None}, {"child_id": True}, {"child_id": False},
                  {"child_id": str(self.first.pk)}, {"child_id": float(self.first.pk)},
                  {"child_id": 0}, {"child_id": -1}, {"child_id": []}, {"child_id": {}},
                  {"child_id": 9223372036854775808},
                  {"child_id": self.first.pk, "user_id": self.other.pk},
                  {"child_id": self.first.pk, "is_staff": True},
                  {"child_id": self.first.pk, "active_child_id": self.foreign.pk})
        for body in bodies:
            with self.subTest(body=body):
                response = self.client.put(self.url, body, format="json")
                self.error(response, 400, "VALIDATION_ERROR")
                self.assertEqual(self.selected(), self.first.pk)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_staff)

    def test_missing_invalid_expired_refresh_and_inactive_jwt(self):
        expired = AccessToken.for_user(self.owner)
        expired.set_exp(lifetime=timedelta(seconds=-1))
        for token in (None, "invalid", str(expired), str(RefreshToken.for_user(self.owner))):
            self.client.credentials(**({"HTTP_AUTHORIZATION": "Bearer " + token} if token else {}))
            self.error(self.select(self.first.pk), 401, "AUTHENTICATION_REQUIRED")
        self.authenticate(self.owner)
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.error(self.select(self.first.pk), 401)
        self.assertIsNone(self.selected())

    def test_selected_child_delete_clears_selection_and_cascades_only_records(self):
        category = Category.objects.create(name="Selection category")
        ChildInterest.objects.create(child=self.first, category=category)
        record = ActivityRecord.objects.create(child=self.first)
        sibling_record = ActivityRecord.objects.create(child=self.second)
        foreign_record = ActivityRecord.objects.create(child=self.foreign)
        get_user_model().objects.filter(pk=self.other.pk).update(active_child=self.foreign)
        self.select(self.first.pk)
        response = self.client.delete(reverse("children:detail", args=[self.first.pk]))
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.selected())
        self.assertFalse(Child.objects.filter(pk=self.first.pk).exists())
        self.assertFalse(ActivityRecord.objects.filter(pk=record.pk).exists())
        self.assertFalse(ChildInterest.objects.filter(child_id=self.first.pk).exists())
        self.assertTrue(ActivityRecord.objects.filter(pk=sibling_record.pk).exists())
        self.assertTrue(ActivityRecord.objects.filter(pk=foreign_record.pk).exists())
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())
        self.assertEqual(self.selected(self.other), self.foreign.pk)
        self.assertEqual(self.select(self.second.pk).status_code, 200)

    def test_unselected_and_foreign_deletion_preserve_current_selection(self):
        self.select(self.first.pk)
        self.error(self.client.delete(reverse("children:detail", args=[self.foreign.pk])), 404)
        self.assertEqual(self.client.delete(reverse("children:detail", args=[self.second.pk])).status_code, 204)
        self.assertEqual(self.selected(), self.first.pk)

    def test_direct_orm_child_deletion_sets_null_and_user_deletion_still_cascades(self):
        self.select(self.first.pk)
        self.first.delete()
        self.assertIsNone(self.selected())
        self.select(self.second.pk)
        owner_id = self.owner.pk
        self.owner.delete()
        self.assertFalse(Child.objects.filter(user_id=owner_id).exists())
        self.assertTrue(Child.objects.filter(pk=self.foreign.pk).exists())

    def test_failed_delete_rolls_back_selection_and_record(self):
        self.select(self.first.pk)
        record = ActivityRecord.objects.create(child=self.first)

        def fail(**kwargs):
            raise RuntimeError("selection-delete-failure-private")

        post_delete.connect(fail, sender=Child, weak=False)
        try:
            response = self.client.delete(reverse("children:detail", args=[self.first.pk]))
        finally:
            post_delete.disconnect(fail, sender=Child)
        self.error(response, 500)
        self.assertNotIn("selection-delete-failure-private", str(response.data))
        self.assertEqual(self.selected(), self.first.pk)
        self.assertTrue(ActivityRecord.objects.filter(pk=record.pk).exists())

    def test_foreign_key_rejects_dangling_child(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.filter(pk=self.owner.pk).update(active_child_id=9223372036854775807)
        self.assertIsNone(self.selected())

    def test_existing_profile_and_child_response_contracts_unchanged(self):
        routes = (reverse("accounts:profile"), reverse("children:list"),
                  reverse("children:detail", args=[self.first.pk]))
        before = [self.client.get(route).data for route in routes]
        self.select(self.first.pk)
        self.assertEqual([self.client.get(route).data for route in routes], before)
        self.assertNotIn("active_child_id", before[0])
        for method in ("get", "post", "patch", "delete"):
            self.error(getattr(self.client, method)(self.url), 405)

    def test_selection_and_deletion_preserve_activity_favorites_cart_and_rights(self):
        from activities.models import Activity
        from favorites.models import Favorite
        from favorites.tests import activity
        from cart.models import CartItem
        from purchases.models import PurchaseEntitlement

        row = activity("Selection preservation fixture")
        favorite = Favorite.objects.create(user=self.owner, activity=row)
        cart = CartItem.objects.create(user=self.owner, activity=row)
        right = PurchaseEntitlement.objects.create(user=self.owner, activity=row)
        self.assertEqual(self.select(self.first.pk).status_code, 200)
        self.assertEqual(self.client.delete(reverse("children:detail", args=[self.first.pk])).status_code, 204)
        self.assertIsNone(self.selected())
        self.assertTrue(Activity.objects.filter(pk=row.pk).exists())
        self.assertTrue(Favorite.objects.filter(pk=favorite.pk).exists())
        self.assertTrue(CartItem.objects.filter(pk=cart.pk).exists())
        self.assertTrue(PurchaseEntitlement.objects.filter(pk=right.pk, status="active").exists())


@skipUnless(ISOLATED, "Concurrency/migration tests require isolated MySQL.")
class ActiveChildConcurrencyTests(TransactionTestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        self.owner = get_user_model().objects.create_user("selection-concurrent@example.com", None)
        self.first = Child.objects.create(user=self.owner, name="First", birth_date=date(2022, 5, 1))
        self.second = Child.objects.create(user=self.owner, name="Second", birth_date=date(2022, 5, 1))
        self.token = str(AccessToken.for_user(self.owner))

    def request(self, method, child_id):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        if method == "select":
            return client.put(reverse("children:active-child"), {"child_id": child_id}, format="json").status_code
        return client.delete(reverse("children:detail", args=[child_id])).status_code

    def worker(self, barrier, method, child_id):
        from config.user_model_rehearsal import guard_rehearsal_sql
        try:
            with connection.execute_wrapper(guard_rehearsal_sql):
                barrier.wait(timeout=10)
                return self.request(method, child_id)
        finally:
            connections.close_all()

    def run_pair(self, left, right):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, barrier, *args) for args in (left, right)]
            return [future.result(timeout=30) for future in futures]

    def test_two_different_selections_serialize_to_one_owned_child(self):
        self.assertEqual(self.run_pair(("select", self.first.pk), ("select", self.second.pk)), [200, 200])
        self.owner.refresh_from_db()
        self.assertIn(self.owner.active_child_id, (self.first.pk, self.second.pk))
        self.assertEqual(self.owner.active_child.user_id, self.owner.pk)

    def test_repeated_concurrent_selection_is_idempotent(self):
        self.assertEqual(self.run_pair(("select", self.first.pk), ("select", self.first.pk)), [200, 200])
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.active_child_id, self.first.pk)

    def test_selection_races_deletion_of_same_child_without_dangling_reference(self):
        statuses = self.run_pair(("select", self.first.pk), ("delete", self.first.pk))
        self.assertIn(statuses[0], (200, 400))
        self.assertEqual(statuses[1], 204)
        self.owner.refresh_from_db()
        self.assertIsNone(self.owner.active_child_id)
        self.assertFalse(Child.objects.filter(pk=self.first.pk).exists())

    def test_switch_races_deletion_of_previous_child_preserves_new_selection(self):
        get_user_model().objects.filter(pk=self.owner.pk).update(active_child=self.first)
        self.assertEqual(self.run_pair(("select", self.second.pk), ("delete", self.first.pk)), [200, 204])
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.active_child_id, self.second.pk)

    def test_selection_waiting_for_delete_commit_rejects_removed_child(self):
        locked, selecting, release = Event(), Event(), Event()
        from config.user_model_rehearsal import guard_rehearsal_sql

        def deleting():
            try:
                with connection.execute_wrapper(guard_rehearsal_sql), transaction.atomic():
                    Child.objects.select_for_update().get(pk=self.first.pk)
                    locked.set()
                    if not release.wait(timeout=10):
                        raise RuntimeError("Delete lock test timed out")
                    return self.request("delete", self.first.pk)
            finally:
                connections.close_all()

        def select_while_locked():
            def observe(execute, sql, params, many, context):
                if "FROM `children`" in sql and "FOR UPDATE" in sql:
                    selecting.set()
                return execute(sql, params, many, context)

            try:
                with connection.execute_wrapper(guard_rehearsal_sql), connection.execute_wrapper(observe):
                    return self.request("select", self.first.pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            delete_future = pool.submit(deleting)
            try:
                self.assertTrue(locked.wait(timeout=10))
                selection = pool.submit(select_while_locked)
                self.assertTrue(selecting.wait(timeout=10))
            finally:
                release.set()
            self.assertEqual(delete_future.result(timeout=30), 204)
            self.assertEqual(selection.result(timeout=30), 400)
        self.owner.refresh_from_db()
        self.assertIsNone(self.owner.active_child_id)


@skipUnless(ISOLATED, "Migration upgrade requires isolated MySQL.")
class ActiveChildMigrationTests(TransactionTestCase):
    databases = {"default"} if ISOLATED else set()

    def test_existing_user_children_and_records_survive_nullable_fk_upgrade(self):
        old = [("accounts", "0003_user_agreements_user_name_user_nickname_user_phone_and_more")]
        new = [("accounts", "0004_user_active_child")]
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.loader.detect_conflicts(), {})
        try:
            executor.migrate(old)
            state = executor.loader.project_state(old + [("children", "0001_initial")]).apps
            User = state.get_model("accounts", "User")
            OldChild = state.get_model("children", "Child")
            OldRecord = state.get_model("children", "ActivityRecord")
            user = User.objects.create(email="selection-upgrade@example.com", password="!", name="Retained")
            child = OldChild.objects.create(user_id=user.pk, name="Retained child", birth_date=date(2022, 5, 1))
            record = OldRecord.objects.create(child_id=child.pk)
            upgrade = MigrationExecutor(connection)
            upgrade_plan = upgrade.migration_plan(new)
            self.assertEqual([(m.app_label, m.name, backwards) for m, backwards in upgrade_plan],
                             [("accounts", "0004_user_active_child", False)])
            sql = "\n".join(upgrade.loader.collect_sql(upgrade_plan))
            self.assertIn("ALTER TABLE `accounts_user` ADD COLUMN `active_child_id`", sql)
            self.assertRegex(sql, r"REFERENCES `children`\s*\(`id`\)")
            self.assertNotIn("DROP TABLE", sql)
            upgrade.migrate(new)
            current = get_user_model().objects.get(pk=user.pk)
            self.assertEqual(current.name, "Retained")
            self.assertIsNone(current.active_child_id)
            self.assertTrue(Child.objects.filter(pk=child.pk, user_id=user.pk).exists())
            self.assertTrue(ActivityRecord.objects.filter(pk=record.pk, child_id=child.pk).exists())
            with connection.cursor() as cursor:
                actual = connection.introspection.get_constraints(cursor, "accounts_user")
            self.assertTrue(any(c.get("columns") == ["active_child_id"] and c.get("foreign_key") == ("children", "id")
                                for c in actual.values()))
        finally:
            MigrationExecutor(connection).migrate(new)
