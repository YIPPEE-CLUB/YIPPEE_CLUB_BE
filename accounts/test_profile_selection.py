from datetime import date
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from children.models import Child


ISOLATED = getattr(settings, "IS_USER_MODEL_REHEARSAL", False)


@skipUnless(ISOLATED, "Profile selection tests require isolated MySQL.")
class ProfileSelectionTests(TestCase):
    databases = {"default"} if ISOLATED else set()

    def setUp(self):
        self.owner = get_user_model().objects.create_user("profile-owner@example.com", "ProfilePwd!83927")
        self.other = get_user_model().objects.create_user("profile-other@example.com", None)
        self.first = Child.objects.create(user=self.owner, name="First", birth_date=date(2022, 5, 1))
        self.second = Child.objects.create(user=self.owner, name="Second", birth_date=date(2022, 5, 1))
        self.client = APIClient()
        self.authenticate(self.owner)
        self.url = reverse("accounts:profile")

    def authenticate(self, user):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + str(AccessToken.for_user(user)))

    def profile(self, selected):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"id": self.owner.pk, "email": self.owner.email,
                                       "phone": "", "name": "", "active_child_id": selected})

    def select(self, child):
        response = self.client.put(reverse("children:active-child"), {"child_id": child.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"active_child_id": child.pk})

    def test_missing_jwt_is_401(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_unselected_is_null(self):
        self.profile(None)

    def test_selection_switch_and_fresh_client_jwt_persist(self):
        self.select(self.first)
        self.profile(self.first.pk)
        self.select(self.second)
        self.profile(self.second.pk)
        self.client = APIClient()
        self.authenticate(self.owner)
        self.profile(self.second.pk)

    def test_selected_deletion_returns_null(self):
        self.select(self.first)
        self.assertEqual(self.client.delete(reverse("children:detail", args=[self.first.pk])).status_code, 204)
        self.profile(None)

    def test_unselected_deletion_preserves_selection(self):
        self.select(self.first)
        self.assertEqual(self.client.delete(reverse("children:detail", args=[self.second.pk])).status_code, 204)
        self.profile(self.first.pk)

    def test_users_only_see_their_own_selection(self):
        foreign = Child.objects.create(user=self.other, name="Foreign", birth_date=date(2022, 5, 1))
        self.authenticate(self.other)
        self.select(foreign)
        self.authenticate(self.owner)
        self.profile(None)
        self.select(self.first)
        self.profile(self.first.pk)
        self.authenticate(self.other)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.other.pk)
        self.assertEqual(response.data["active_child_id"], foreign.pk)

    def test_login_and_patch_response_contracts_preserved(self):
        self.select(self.first)
        response = self.client.post(reverse("accounts:login"), {
            "email": self.owner.email, "password": "ProfilePwd!83927"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {"access_token", "refresh_token", "user"})
        self.assertEqual(set(response.data["user"]), {"id", "email", "phone", "name"})
        response = self.client.patch(self.url, {"name": "Parent"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, {"id": self.owner.pk, "email": self.owner.email,
                                       "phone": "", "name": "Parent"})
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.active_child_id, self.first.pk)
