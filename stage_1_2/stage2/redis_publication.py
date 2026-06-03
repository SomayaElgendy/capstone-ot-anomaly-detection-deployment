import json
import time
import argparse
from pathlib import Path

import redis


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alerts", default="outputs/stage2/alerts.json")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--stream", default="ai_alerts")
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()

    alerts_path = Path(args.alerts)

    if not alerts_path.exists():
        raise FileNotFoundError(f"Alerts file not found: {alerts_path}")

    alerts = json.loads(alerts_path.read_text(encoding="utf-8"))

    r = redis.Redis(host=args.host, port=args.port, decode_responses=True)
    r.ping()

    print(f"Publishing {len(alerts)} alerts to Redis stream '{args.stream}'...")

    for i, alert in enumerate(alerts, start=1):
        payload = {
            "predicted_attack": str(alert.get("predicted_attack", "unknown")),
            "classifier_confidence": str(alert.get("classifier_confidence", 0.0)),
            "network_anomaly_score": str(alert.get("network_anomaly_score", 0.0)),
            "process_anomaly_score": str(alert.get("process_anomaly_score", 0.0)),
            "window_start_time": str(alert.get("window_start_time", "")),
            "window_end_time": str(alert.get("window_end_time", "")),
            "technique_id": str(alert.get("technique_id", "")),
        }

        msg_id = r.xadd(args.stream, payload)
        print(f"[{i}/{len(alerts)}] Published {payload['predicted_attack']} → {msg_id}")
        time.sleep(args.delay)

    print("Done.")


if __name__ == "__main__":
    main()