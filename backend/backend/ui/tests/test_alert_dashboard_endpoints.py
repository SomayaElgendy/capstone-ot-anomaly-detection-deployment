from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from alerts.models import Alert


User = get_user_model()


class AlertDashboardEndpointTests(TestCase):
    def setUp(self):
        self.security_user = User.objects.create_user(
            username="security_user",
            password="testpass123",
            role="security_specialist",
        )

        self.normal_user = User.objects.create_user(
            username="normal_user",
            password="testpass123",
            role="external",
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

    def test_ui_alerts_data_requires_login(self):
        response = self.client.get(reverse("ui:ui_alerts_data"))
        self.assertEqual(response.status_code, 302)

    def test_ui_alerts_data_blocks_non_security_role(self):
        self.client.login(username="normal_user", password="testpass123")
        response = self.client.get(reverse("ui:ui_alerts_data"))
        self.assertEqual(response.status_code, 403)

    def test_ui_alerts_data_returns_latest_alerts_for_security_user(self):
        self.client.login(username="security_user", password="testpass123")

        response = self.client.get(reverse("ui:ui_alerts_data"))

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["predicted_attack"], "modify_alarm_settings")
        self.assertEqual(data[0]["technique_id"], "T0838")
        self.assertEqual(data[0]["status"], "Pending")
        self.assertIn("classifier_confidence", data[0])
        self.assertIn("network_anomaly_score", data[0])
        self.assertIn("process_anomaly_score", data[0])

    def test_ui_alert_detail_data_returns_stage2_style_payload(self):
        self.client.login(username="security_user", password="testpass123")

        response = self.client.get(
            reverse("ui:ui_alert_detail_data", args=[self.alert.id])
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["id"], self.alert.id)
        self.assertEqual(data["predicted_attack"], "modify_alarm_settings")
        self.assertEqual(data["technique_id"], "T0838")
        self.assertIn("stage2_alert_json", data)
        self.assertEqual(
            data["stage2_alert_json"]["predicted_attack"],
            "modify_alarm_settings",
        )

    def test_ui_ack_alert_updates_status_and_acknowledgement_fields(self):
        self.client.login(username="security_user", password="testpass123")

        response = self.client.post(
            reverse("ui:ui_ack_alert", args=[self.alert.id])
        )

        self.assertEqual(response.status_code, 200)

        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "Acknowledged")
        self.assertEqual(self.alert.acknowledged_by, self.security_user)
        self.assertIsNotNone(self.alert.acknowledged_at)

        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "Acknowledged")