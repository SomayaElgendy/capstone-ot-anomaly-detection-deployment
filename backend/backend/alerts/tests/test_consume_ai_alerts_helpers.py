from django.test import TestCase
from django.utils import timezone

from alerts.management.commands.consume_ai_alerts import to_float, parse_stage2_time


class ConsumeAIAlertsHelperTests(TestCase):
    def test_to_float_valid_number_string(self):
        self.assertEqual(to_float("3.14"), 3.14)

    def test_to_float_invalid_value_returns_default(self):
        self.assertEqual(to_float("not-a-number", default=7.5), 7.5)

    def test_to_float_none_returns_default(self):
        self.assertEqual(to_float(None, default=1.2), 1.2)

    def test_parse_stage2_time_valid_iso_string_returns_aware_datetime(self):
        dt = parse_stage2_time("2026-05-16T01:30:00")

        self.assertTrue(timezone.is_aware(dt))
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 5)
        self.assertEqual(dt.day, 16)

    def test_parse_stage2_time_invalid_value_returns_current_time(self):
        before = timezone.now()
        dt = parse_stage2_time("invalid-time")
        after = timezone.now()

        self.assertTrue(before <= dt <= after)