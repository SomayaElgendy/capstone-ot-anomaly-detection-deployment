from django.test import TestCase
from django.urls import reverse
from users.models import User


class UIAuthAndAccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin1",
            password="TestPass123!",
            role="admin",
        )
        self.security = User.objects.create_user(
            username="sec1",
            password="TestPass123!",
            role="security_specialist",
        )
        self.ai = User.objects.create_user(
            username="ai1",
            password="TestPass123!",
            role="ai_engineer",
        )
        self.external = User.objects.create_user(
            username="ext1",
            password="TestPass123!",
            role="external_user",
        )

    def test_home_page_loads(self):
        response = self.client.get(reverse("ui:home"))
        self.assertEqual(response.status_code, 200)

    def test_request_service_get_loads(self):
        response = self.client.get(reverse("ui:request_service"))
        self.assertEqual(response.status_code, 200)

    def test_request_service_post_returns_success_flag(self):
        response = self.client.post(reverse("ui:request_service"), data={"dummy": "value"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "success")

    def test_login_page_loads(self):
        response = self.client.get(reverse("ui:login"))
        self.assertEqual(response.status_code, 200)

    def test_valid_login_security_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("ui:login"),
            data={"username": "sec1", "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("ui:dashboard"))

    def test_valid_login_admin_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("ui:login"),
            data={"username": "admin1", "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("ui:dashboard"))

    def test_valid_login_ai_redirects_to_home(self):
        response = self.client.post(
            reverse("ui:login"),
            data={"username": "ai1", "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("ui:home"))

    def test_valid_login_external_redirects_to_home(self):
        response = self.client.post(
            reverse("ui:login"),
            data={"username": "ext1", "password": "TestPass123!"},
        )
        self.assertRedirects(response, reverse("ui:home"))

    def test_invalid_login_shows_error(self):
        response = self.client.post(
            reverse("ui:login"),
            data={"username": "sec1", "password": "WrongPass"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid credentials")

    def test_logout_redirects_home(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:logout"))
        self.assertRedirects(response, reverse("ui:home"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("ui:login"), response.url)

    def test_dashboard_allows_security_specialist(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_allows_admin(self):
        self.client.login(username="admin1", password="TestPass123!")
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_blocks_ai_engineer(self):
        self.client.login(username="ai1", password="TestPass123!")
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_blocks_external_user(self):
        self.client.login(username="ext1", password="TestPass123!")
        response = self.client.get(reverse("ui:dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_alert_detail_requires_security_role(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:alert_detail", args=[1]))
        self.assertEqual(response.status_code, 200)

    def test_alert_detail_blocks_external_user(self):
        self.client.login(username="ext1", password="TestPass123!")
        response = self.client.get(reverse("ui:alert_detail", args=[1]))
        self.assertEqual(response.status_code, 403)

    def test_ot_overview_allows_security(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:ot_overview"))
        self.assertEqual(response.status_code, 200)

    def test_ot_overview_blocks_ai_engineer(self):
        self.client.login(username="ai1", password="TestPass123!")
        response = self.client.get(reverse("ui:ot_overview"))
        self.assertEqual(response.status_code, 403)

    def test_ot_overview_context_contains_streamlit_url(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:ot_overview"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("streamlit_url", response.context)