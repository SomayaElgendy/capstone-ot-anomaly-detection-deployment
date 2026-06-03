from unittest.mock import patch, MagicMock

from django.test import TestCase

from alerts.models import Alert
from alerts.management.commands.consume_ai_alerts import Command


class ConsumeAIAlertsCommandTests(TestCase):
    @patch("alerts.management.commands.consume_ai_alerts.redis.Redis")
    def test_consumer_reads_redis_stream_and_creates_alert(self, mock_redis_class):
        mock_redis = MagicMock()
        mock_redis_class.return_value = mock_redis

        mock_redis.ping.return_value = True

        fake_message = [
            (
                "ai_alerts",
                [
                    (
                        "1-0",
                        {
                            "predicted_attack": "modify_alarm_settings",
                            "classifier_confidence": "0.954",
                            "network_anomaly_score": "0.542",
                            "process_anomaly_score": "10.788",
                            "window_start_time": "2026-05-16T01:30:00",
                            "window_end_time": "2026-05-16T01:30:10",
                            "technique_id": "T0838",
                        },
                    )
                ],
            )
        ]

        # First call returns one message.
        # Second call stops the infinite loop safely.
        mock_redis.xread.side_effect = [
            fake_message,
            KeyboardInterrupt,
        ]

        command = Command()

        with self.assertRaises(KeyboardInterrupt):
            command.handle(
                host="localhost",
                port=6379,
                stream="ai_alerts",
                block=1,
            )

        self.assertEqual(Alert.objects.count(), 1)

        alert = Alert.objects.first()
        self.assertEqual(alert.predicted_attack, "modify_alarm_settings")
        self.assertAlmostEqual(float(alert.classifier_confidence), 0.954)
        self.assertAlmostEqual(float(alert.network_anomaly_score), 0.542)
        self.assertAlmostEqual(float(alert.process_anomaly_score), 10.788)
        self.assertEqual(alert.technique_id, "T0838")
        self.assertEqual(alert.status, "Pending")
        self.assertEqual(alert.extra["redis_message_id"], "1-0")
        self.assertEqual(alert.extra["source"], "stage1_stage2_dataset_demo")

        mock_redis_class.assert_called_once_with(
            host="localhost",
            port=6379,
            decode_responses=True,
        )
        mock_redis.ping.assert_called_once()
        mock_redis.xread.assert_called()

    @patch("alerts.management.commands.consume_ai_alerts.redis.Redis")
    def test_consumer_continues_when_no_messages_are_received(self, mock_redis_class):
        mock_redis = MagicMock()
        mock_redis_class.return_value = mock_redis

        mock_redis.ping.return_value = True

        # First call returns no messages.
        # Second call stops the infinite loop safely.
        mock_redis.xread.side_effect = [
            [],
            KeyboardInterrupt,
        ]

        command = Command()

        with self.assertRaises(KeyboardInterrupt):
            command.handle(
                host="localhost",
                port=6379,
                stream="ai_alerts",
                block=1,
            )

        self.assertEqual(Alert.objects.count(), 0)