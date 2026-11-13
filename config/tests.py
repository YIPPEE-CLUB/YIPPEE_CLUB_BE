from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient


class HealthTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_health_is_public_and_returns_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Content-Type"], "application/json")

    def test_health_does_not_require_valid_credentials(self):
        response = self.client.get(
            reverse("health"), HTTP_AUTHORIZATION="Bearer invalid-token"
        )
        self.assertEqual(response.status_code, 200)

    def test_health_rejects_post(self):
        response = self.client.post(reverse("health"), {}, format="json")
        self.assertEqual(response.status_code, 405)