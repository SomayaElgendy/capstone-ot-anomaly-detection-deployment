from unittest.mock import MagicMock, patch
import json

from django.test import TestCase
from django.urls import reverse

from alerts.models import Alert
from users.models import User
from django.utils import timezone
from datetime import timedelta

class UIReportGenerationIntegrationTests(TestCase):
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

        now = timezone.now()

        self.alert = Alert.objects.create(
            predicted_attack="modify_alarm_settings",
            classifier_confidence=0.954,
            network_anomaly_score=0.542,
            process_anomaly_score=10.788,
            window_start_time=now,
            window_end_time=now + timedelta(seconds=10),
            technique_id="T0838",
            status="Pending",
            extra={
                "source": "unit_test",
                "redis_message_id": "test-redis-id",
            },
        )

    def _login_security(self):
        self.client.login(username="sec1", password="TestPass123!")

    def test_ui_generate_report_requires_login(self):
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("ui:login"), response.url)

    def test_ui_generate_report_blocks_non_security_role(self):
        self.client.login(username="ext1", password="TestPass123!")
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_ui_generate_report_invalid_json_returns_400(self):
        self._login_security()
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "Invalid JSON"})

    def test_ui_generate_report_missing_alert_id_returns_400(self):
        self._login_security()
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {"error": "alert_id is required"})

    def test_ui_generate_report_alert_not_found_returns_404(self):
        self._login_security()
        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": 999999}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertJSONEqual(response.content, {"error": "Alert not found"})

    @patch("ui.views.requests.post")
    def test_ui_generate_report_success_saves_report(self, mock_post):
        self._login_security()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reply": "# Incident Response Report\nGenerated report text",
            "grade": "GOOD",
            "score": 0.82,
            "run_id": "deploy_alert1_ip_scan_20260416_123456",
        }
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("report", data)
        self.assertEqual(data["grade"], "GOOD")
        self.assertEqual(data["score"], 0.82)

        self.alert.refresh_from_db()
        self.assertIn("Incident Response Report", self.alert.full_report)
        self.assertTrue(len(self.alert.llm_response) > 0)

    @patch("ui.views.requests.post")
    def test_ui_generate_report_sends_expected_payload(self, mock_post):
        self._login_security()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reply": "Generated report text"
        }
        mock_post.return_value = mock_response

        self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertTrue(mock_post.called)

        _, kwargs = mock_post.call_args
        sent_payload = kwargs["json"]

        self.assertEqual(sent_payload["predicted_attack"], "modify_alarm_settings")
        self.assertEqual(sent_payload["classifier_confidence"], 0.954)
        self.assertEqual(sent_payload["network_anomaly_score"], 0.542)
        self.assertEqual(sent_payload["process_anomaly_score"], 10.788)
        self.assertIn("window_start_time", sent_payload)
        self.assertIn("window_end_time", sent_payload)

    @patch("ui.views.requests.post")
    def test_ui_generate_report_service_unreachable_returns_502(self, mock_post):
        self._login_security()

        import requests
        mock_post.side_effect = requests.RequestException("connection failed")

        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("Report service unreachable", response.json()["error"])

    @patch("ui.views.requests.post")
    def test_ui_generate_report_non_200_returns_502(self, mock_post):
        self._login_security()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error from IR service"
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        data = response.json()
        self.assertEqual(data["error"], "Report service error")
        self.assertEqual(data["status"], 500)

    @patch("ui.views.requests.post")
    def test_ui_generate_report_invalid_json_from_service_returns_502(self, mock_post):
        self._login_security()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("bad json")
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Invalid JSON from report service")

    @patch("ui.views.requests.post")
    def test_ui_generate_report_empty_reply_returns_502(self, mock_post):
        self._login_security()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "reply": ""
        }
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("ui:ui_generate_report"),
            data=json.dumps({"alert_id": self.alert.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Invalid report response")