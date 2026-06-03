import redis

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from alerts.models import Alert


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def parse_stage2_time(value):
    dt = parse_datetime(value or "")

    if dt is None:
        return timezone.now()

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    return dt


class Command(BaseCommand):
    help = "Consume AI alerts from Redis stream and store them in the Alert table."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="localhost")
        parser.add_argument("--port", type=int, default=6379)
        parser.add_argument("--stream", default="ai_alerts")
        parser.add_argument("--block", type=int, default=5000)

    def handle(self, *args, **options):
        r = redis.Redis(
            host=options["host"],
            port=options["port"],
            decode_responses=True,
        )
        r.ping()

        stream = options["stream"]
        last_id = "$"

        self.stdout.write(self.style.SUCCESS(f"Listening to Redis stream: {stream}"))

        while True:
            messages = r.xread({stream: last_id}, block=options["block"], count=10)

            if not messages:
                continue

            for _, entries in messages:
                for msg_id, data in entries:
                    last_id = msg_id

                    alert = Alert.objects.create(
                        predicted_attack=data.get("predicted_attack", "unknown"),
                        classifier_confidence=to_float(data.get("classifier_confidence")),
                        network_anomaly_score=to_float(data.get("network_anomaly_score")),
                        process_anomaly_score=to_float(data.get("process_anomaly_score")),
                        window_start_time=parse_stage2_time(data.get("window_start_time")),
                        window_end_time=parse_stage2_time(data.get("window_end_time")),
                        technique_id=data.get("technique_id", ""),
                        status="Pending",
                        extra={
                            "redis_message_id": msg_id,
                            "source": "stage1_stage2_dataset_demo",
                        },
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Saved alert #{alert.id}: {alert.predicted_attack}"
                        )
                    )