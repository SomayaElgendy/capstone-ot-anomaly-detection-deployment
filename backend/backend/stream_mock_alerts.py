import os
import json
import time
import django
from datetime import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from alerts.models import Alert


def create_alert(item):
    now = datetime.now()

    alert = Alert.objects.create(
        title=f"Detected {item['predicted_attack']}",
        attack_label=item["predicted_attack"],
        anomaly_score=item["network_anomaly_score"],
        timestamp=now,
        status="Pending",
        extra={
            **item,
            "window_start_time": now.isoformat(),
            "window_end_time": now.isoformat(),
        }
    )

    print(f"Created alert #{alert.id}: {item['predicted_attack']}")


def main():
    with open("mock_alerts.json", "r", encoding="utf-8") as f:
        alerts = json.load(f)

    print(f"Streaming {len(alerts)} mock alerts...")

    for item in alerts:
        create_alert(item)
        time.sleep(5)

    print("Done.")


if __name__ == "__main__":
    main()