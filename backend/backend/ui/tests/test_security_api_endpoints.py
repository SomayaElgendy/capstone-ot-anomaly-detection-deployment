import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import User


class UISecurityAPIEndpointTests(TestCase):
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

    def test_ui_chat_requires_login(self):
        response = self.client.post(
            reverse("ui:ui_chat"),
            data=json.dumps({"alert_id": 1, "message": "hello"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("ui:login"), response.url)

    def test_ui_chat_blocks_non_security_role(self):
        self.client.login(username="ai1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_chat"),
            data=json.dumps({"alert_id": 1, "message": "hello"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_ui_chat_invalid_json_returns_400(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_chat"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "Invalid JSON body"})

    def test_ui_chat_missing_fields_returns_400(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_chat"),
            data=json.dumps({"alert_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {"error": "alert_id and message are required"},
        )

    def test_ui_generate_report_requires_login(self):
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("ui:login"), response.url)

    def test_ui_generate_report_blocks_non_security_role(self):
        self.client.login(username="ext1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": 1}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_ui_generate_report_invalid_json_returns_400(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "Invalid JSON"})

    def test_ui_generate_report_missing_alert_id_returns_400(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "alert_id is required"})

    @override_settings(OT_STREAMLIT_URL="http://127.0.0.1:8501")
    def test_ot_overview_uses_streamlit_setting(self):
        self.client.login(username="sec1", password="TestPass123!")
        response = self.client.get(reverse("ui:ot_overview"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["streamlit_url"], "http://127.0.0.1:8501")

